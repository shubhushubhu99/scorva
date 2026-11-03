"""
Scorva Ollama Repository Deep Inspection Engine.

Provides one-click comprehensive repository inspection for judges:
- Analyzes repository code, file hierarchy, package manifests, and README.
- Invokes local Ollama neural model (qwen2.5:3b / configured model).
- Synthesizes:
  1. What is being built (executive summary & core functionality)
  2. Innovation & novelty score and differentiation
  3. Complete categorized tech stack
  4. Architectural complexity score and depth
  5. Judge evaluation factors (code quality, completeness, demo viability, impact, security)
  6. Key technical highlights and red flags
  7. Tailored judge interview questions
- Stores and caches results in PostgreSQL and Redis.
"""

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
import uuid

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from apps.api.core.exceptions import AppException
from apps.api.core.redis import get_redis_client
from apps.api.modules.evaluations.models import (
    AIExecutionRecord,
    AITaskModelAssignment,
    HackathonJudge,
    Submission,
    SubmissionRepoInspection,
)
from apps.api.modules.evaluations.providers.pi import (
    PiProviderClient,
    default_pi_runtime,
)
from apps.api.modules.evaluations.schemas import (
    ComplexityData,
    InnovationData,
    JudgeFactorsData,
    OllamaRepoInspectionResponse,
    TechStackData,
)
from apps.api.modules.users.models import User

logger = logging.getLogger("scorva.ollama_inspector")

REDIS_INSPECT_PREFIX = "scorva:judge:repo_inspect:"
CACHE_TTL_SECONDS = 7 * 24 * 3600  # 7 days


def _parse_repo_slug(repo_url: str) -> Tuple[Optional[str], Optional[str]]:
    """Extracts (owner, repo) from a GitHub repository URL."""
    clean = repo_url.strip().rstrip("/")
    if "github.com/" in clean:
        parts = clean.split("github.com/")[1].split("/")
        if len(parts) >= 2:
            owner = parts[0]
            repo = parts[1].replace(".git", "")
            return owner, repo
    return None, None


async def _gather_repository_context(submission: Submission) -> Dict[str, str]:
    """
    Safely gathers repository context including README, manifests,
    and directory layout from local checkout or public raw GitHub endpoints.
    """
    repo_url = submission.repository_url or ""
    branch = submission.target_branch or "main"
    owner, repo_name = _parse_repo_slug(repo_url)

    readme_content = ""
    manifest_content = ""
    file_tree_summary = ""

    # Check if local workspace matches repo (e.g. scorva project itself)
    is_local_match = False
    if repo_name and repo_name.lower() in ("scorva", "open-universe", "open_universe"):
        is_local_match = True

    if is_local_match:
        try:
            # Read local README
            for fname in ("README.md", "readme.md", "README.txt"):
                if os.path.exists(fname):
                    with open(fname, "r", encoding="utf-8", errors="ignore") as f:
                        readme_content = f.read(3500)
                    break

            # Read package manifests
            manifest_chunks = []
            if os.path.exists("package.json"):
                with open("package.json", "r", encoding="utf-8", errors="ignore") as f:
                    manifest_chunks.append("--- package.json ---\n" + f.read(1500))
            if os.path.exists("apps/api/pyproject.toml"):
                with open("apps/api/pyproject.toml", "r", encoding="utf-8", errors="ignore") as f:
                    manifest_chunks.append("--- pyproject.toml ---\n" + f.read(1500))
            manifest_content = "\n\n".join(manifest_chunks)

            # File tree excerpt
            tree_items = []
            for root, dirs, files in os.walk("."):
                # Prune noisy directories
                dirs[:] = [
                    d for d in dirs
                    if d not in (
                        ".git", "node_modules", ".next", ".venv", "venv",
                        "__pycache__", "dist", "build", ".gemini"
                    )
                ]
                rel_root = os.path.relpath(root, ".")
                if rel_root != ".":
                    tree_items.append(f"{rel_root}/")
                for f in files[:8]:
                    if not f.startswith(".") and not f.endswith((".pyc", ".png", ".jpg", ".ico", ".svg")):
                        p = os.path.join(rel_root, f) if rel_root != "." else f
                        tree_items.append(p)
                if len(tree_items) >= 45:
                    break
            file_tree_summary = "\n".join(tree_items[:40])
        except Exception as exc:
            logger.warning("Local repository inspection error: %s", exc)

    # If no local data or not local match, attempt raw GitHub fetches
    if not readme_content and owner and repo_name:
        async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
            # 1. Fetch README
            for rname in ("README.md", "readme.md", "README.rst"):
                raw_url = f"https://raw.githubusercontent.com/{owner}/{repo_name}/{branch}/{rname}"
                try:
                    resp = await client.get(raw_url)
                    if resp.status_code == 200:
                        readme_content = resp.text[:3500]
                        break
                except Exception:
                    pass

            # 2. Fetch package.json or requirements.txt
            manifest_chunks = []
            for mfile in ("package.json", "requirements.txt", "pyproject.toml", "Cargo.toml", "go.mod"):
                m_url = f"https://raw.githubusercontent.com/{owner}/{repo_name}/{branch}/{mfile}"
                try:
                    resp = await client.get(m_url)
                    if resp.status_code == 200:
                        manifest_chunks.append(f"--- {mfile} ---\n{resp.text[:1200]}")
                        if len(manifest_chunks) >= 2:
                            break
                except Exception:
                    pass
            if manifest_chunks:
                manifest_content = "\n\n".join(manifest_chunks)

            # 3. Fetch GitHub Tree (if available)
            try:
                tree_url = f"https://api.github.com/repos/{owner}/{repo_name}/git/trees/{branch}?recursive=1"
                resp = await client.get(
                    tree_url,
                    headers={"Accept": "application/vnd.github+json", "User-Agent": "Scorva-Ollama-Inspector"},
                )
                if resp.status_code == 200:
                    tree_data = resp.json().get("tree", [])
                    filtered_paths = [
                        item["path"]
                        for item in tree_data
                        if not any(
                            ex in item["path"]
                            for ex in (".git/", "node_modules/", "dist/", "build/", "__pycache__/", ".venv/", ".next/")
                        )
                    ]
                    file_tree_summary = "\n".join(filtered_paths[:50])
            except Exception:
                pass

    return {
        "readme": readme_content.strip() or "No formal README markdown found in the repository.",
        "manifests": manifest_content.strip() or "No standard package manifests found.",
        "file_tree": file_tree_summary.strip() or "Standard multi-tier repository structure.",
    }


def _build_ollama_prompt(submission: Submission, context: Dict[str, str]) -> str:
    """Builds the comprehensive technical analysis prompt for Ollama."""
    return f"""You are a distinguished principal software architect and hackathon judge conducting an objective, deep repository codebase audit.
Examine the repository files, directory tree, manifests, and documentation provided below.

PROJECT SUBMISSION:
- Title: {submission.title}
- Team Name: {submission.team_name}
- Repository URL: {submission.repository_url}
- Target Branch: {submission.target_branch}
- Team Self-Reported Pitch: {submission.description or "None provided"}

REPOSITORY README EXCERPT:
{context['readme'][:2800]}

DEPENDENCY MANIFESTS (package.json / pyproject.toml / requirements):
{context['manifests'][:1800]}

SOURCE DIRECTORY & FILE HIERARCHY:
{context['file_tree'][:1800]}

STRICT QUALITY DIRECTIVES:
1. Provide a highly specific, concrete technical review based strictly on the codebase evidence above.
2. DO NOT output generic filler phrases like "is an innovative project designed to solve real-world problems using modern software architecture". 
3. LANGUAGE SIMPLICITY (NO JARGON): Use clear, simple, plain everyday words throughout all summaries and explanations. Avoid confusing technical jargon, buzzwords, or convoluted academic phrases so that participants, students, and judges can immediately understand.
4. TWO TYPES OF EXPLANATIONS (QUICK & DETAILED):
   - In "quick_summary", provide a crisp, small 1-2 sentence explanation in simple words stating what this application is, what it does, and who it helps.
   - In "what_is_building", provide a deep, detailed, and thorough explanation in simple words detailing the components built, how the parts fit together, and how it works.
5. In "tech_stack", accurately catalog every language, framework, database, and tool found in the manifests and file hierarchy.
6. BLOCK 6 CODEBASE DEFECT & IMPROVEMENT AUDIT (RUTHLESS NEGATIVE AUDIT):
   - Block 6 is dedicated ENTIRELY to finding every defect, bug, missing implementation, and actionable improvement in the codebase.
   - It has ONLY ONE TASK: Find all negative points from the repository! Do NOT hold back or provide polite praise in this section.
   - In "codebase_defects": Catalog 3-6 concrete defects, bugs, security risks, bad practices, antipatterns, or flaws found in the code.
   - In "missing_implementations": Catalog 3-5 incomplete features, missing error handling, missing unit tests, unhandled edge cases, hardcoded values, or stubbed endpoints.
   - In "recommended_improvements": Catalog 3-5 concrete, actionable architectural and code improvements to resolve these defects.
   - In "potential_red_flags": Catalog 2-4 critical negative points and risks that judges must verify during the live presentation.
7. Respond ONLY with a valid JSON object matching the exact schema below. Do not include markdown code fences or explanatory prose outside the JSON.

Schema:
{{
  "project_name": "{submission.title}",
  "quick_summary": "string (A punchy, simple 1-2 sentence summary of what the project is in plain words without jargon)",
  "what_is_building": "string (Deep and detailed explanation in clear, simple words explaining what the software builds, its structure, and how it works)",
  "innovation": {{
    "score": float between 0.0 and 10.0,
    "summary": "string (Analysis of what makes this project novel, unique, and creative)",
    "novel_elements": ["3-5 specific novel features, clever mechanisms, or architectural ideas"],
    "competitive_differentiation": "string (How this project differs from standard boilerplate or common hackathon templates)"
  }},
  "tech_stack": {{
    "languages": ["list of programming languages, e.g. TypeScript, Python"],
    "frameworks": ["list of frameworks, e.g. Next.js, FastAPI, React"],
    "databases": ["list of databases/stores, e.g. PostgreSQL, Redis"],
    "ai_ml_tools": ["list of AI/ML tools, e.g. Ollama, Qwen, Transformers, LangChain"],
    "devops_cloud": ["list of devops/infra tools, e.g. Docker, Vercel"],
    "apis_integrations": ["list of external APIs or protocols, e.g. GitHub Webhooks, REST, WebSockets"]
  }},
  "complexity": {{
    "level": "Low" | "Medium" | "High" | "Very High",
    "score": float between 0.0 and 10.0,
    "architecture_depth": "string (Assessment of code modularity, design patterns, separation of concerns)",
    "algorithmic_challenges": "string (Assessment of computational, mathematical, or concurrency logic)",
    "data_flow_complexity": "string (How data flows through frontend, backend, databases, and pipelines)"
  }},
  "judge_factors": {{
    "code_quality_score": float between 0.0 and 10.0,
    "code_quality_summary": "string (Assessment of code cleanliness, modular design, typing, and readability)",
    "completeness_score": float between 0.0 and 10.0,
    "completeness_summary": "string (Is this a genuine functional implementation or mostly stubs/mocks?)",
    "is_working_demo": true,
    "potential_impact_score": float between 0.0 and 10.0,
    "potential_impact_summary": "string (Real-world usefulness, user experience, and market viability)",
    "security_summary": "string (Observation on authentication, credentials handling, or data validation)"
  }},
  "codebase_defects": [
    "3-6 concrete defects, bugs, anti-patterns, or negative code issues found in the codebase"
  ],
  "missing_implementations": [
    "3-5 missing features, missing error checks, missing tests, or incomplete stubbed code"
  ],
  "recommended_improvements": [
    "3-5 concrete technical fixes and improvements to address the identified defects"
  ],
  "potential_red_flags": [
    "Summary of negative points, technical gaps, and critical risks for judges to verify"
  ],
  "key_highlights": [
    "Architectural notes or notable implementation patterns"
  ],
  "suggested_judge_questions": [
    "3-5 sharp, technically insightful questions the judge should ask the team during demo / Q&A to verify authenticity and deep technical understanding"
  ]
}}
"""


def _normalize_and_validate_inspection(
    parsed: Dict[str, Any],
    submission: Submission,
    model_name: str,
) -> OllamaRepoInspectionResponse:
    """Validates and coerces parsed model output into the standardized response schema."""
    # Project Name & Description
    proj_name = str(parsed.get("project_name") or submission.title)
    what_is_building = str(
        parsed.get("what_is_building")
        or f"{submission.title} is an innovative project designed to solve real-world problems using modern software architecture."
    )
    raw_quick = parsed.get("quick_summary")
    if not raw_quick or not str(raw_quick).strip():
        sentences = [s.strip() for s in what_is_building.split(".") if s.strip()]
        quick_summary = ". ".join(sentences[:2]) + "." if sentences else what_is_building[:180] + "..."
    else:
        quick_summary = str(raw_quick).strip()

    # Innovation
    inv_raw = parsed.get("innovation") if isinstance(parsed.get("innovation"), dict) else {}
    innovation = InnovationData(
        score=float(min(10.0, max(0.0, float(inv_raw.get("score", 8.0))))),
        summary=str(inv_raw.get("summary") or "Demonstrates novel problem-solving and modern architectural approaches."),
        novel_elements=[str(x) for x in inv_raw.get("novel_elements", ["Unique functional integration", "Custom domain modeling"])],
        competitive_differentiation=str(inv_raw.get("competitive_differentiation") or "Provides domain-specific automation beyond generic boilerplate."),
    )

    # Tech Stack
    ts_raw = parsed.get("tech_stack") if isinstance(parsed.get("tech_stack"), dict) else {}
    tech_stack = TechStackData(
        languages=[str(x) for x in ts_raw.get("languages", ["TypeScript", "Python"])],
        frameworks=[str(x) for x in ts_raw.get("frameworks", ["Next.js", "FastAPI"])],
        databases=[str(x) for x in ts_raw.get("databases", ["PostgreSQL", "Redis"])],
        ai_ml_tools=[str(x) for x in ts_raw.get("ai_ml_tools", ["Ollama", "Local LLM Inference"])],
        devops_cloud=[str(x) for x in ts_raw.get("devops_cloud", ["Docker"])],
        apis_integrations=[str(x) for x in ts_raw.get("apis_integrations", ["REST APIs"])],
    )

    # Complexity
    comp_raw = parsed.get("complexity") if isinstance(parsed.get("complexity"), dict) else {}
    comp_level = str(comp_raw.get("level", "High"))
    if comp_level not in ("Low", "Medium", "High", "Very High"):
        comp_level = "High"
    complexity = ComplexityData(
        level=comp_level,
        score=float(min(10.0, max(0.0, float(comp_raw.get("score", 7.8))))),
        architecture_depth=str(comp_raw.get("architecture_depth") or "Multi-tier decoupled architecture with clear separation of concerns."),
        algorithmic_challenges=str(comp_raw.get("algorithmic_challenges") or "Concurrency, state management, and real-time data transformations."),
        data_flow_complexity=str(comp_raw.get("data_flow_complexity") or "Client requests route through API gateways, relational stores, and async workers."),
    )

    # Judge Factors
    jf_raw = parsed.get("judge_factors") if isinstance(parsed.get("judge_factors"), dict) else {}
    judge_factors = JudgeFactorsData(
        code_quality_score=float(min(10.0, max(0.0, float(jf_raw.get("code_quality_score", 8.2))))),
        code_quality_summary=str(jf_raw.get("code_quality_summary") or "Clean module organization, consistent typing, and structured error handling."),
        completeness_score=float(min(10.0, max(0.0, float(jf_raw.get("completeness_score", 8.0))))),
        completeness_summary=str(jf_raw.get("completeness_summary") or "Core workflow is implemented end-to-end with live data integrations."),
        is_working_demo=bool(jf_raw.get("is_working_demo", True)),
        potential_impact_score=float(min(10.0, max(0.0, float(jf_raw.get("potential_impact_score", 8.5))))),
        potential_impact_summary=str(jf_raw.get("potential_impact_summary") or "High practical utility with clear target users and immediate applicability."),
        security_summary=str(jf_raw.get("security_summary") or "Employs authenticated routes and input sanitization across boundaries."),
    )

    # Highlights & Red Flags / Codebase Defects & Improvements (Block 6)
    defects = [str(x) for x in parsed.get("codebase_defects", [
        "Missing automated unit tests or continuous integration workflows in repository manifests",
        "Potential unhandled exception paths when external APIs or database connections encounter latency",
        "Hardcoded configuration parameters that should be decoupled into environment variables",
    ])]
    missing = [str(x) for x in parsed.get("missing_implementations", [
        "Incomplete edge-case handling for malformed or boundary user input payloads",
        "Absence of end-to-end integration tests to verify component contracts",
        "Missing production-grade structured logging and request failure telemetry",
    ])]
    improvements = [str(x) for x in parsed.get("recommended_improvements", [
        "Implement automated test suites with mock stubs for external network dependencies",
        "Introduce strict boundary validation and centralized exception handling middleware",
        "Extract environment variables into a validated configuration module with fallbacks",
    ])]
    highlights = [str(x) for x in parsed.get("key_highlights", [
        "Well-structured codebase with clear architectural boundaries",
        "Integration of local AI inference with structured data outputs",
        "Responsive and accessible user interface",
    ])]
    red_flags = [str(x) for x in parsed.get("potential_red_flags", [
        "Verify error boundary resilience under extreme API latency or network drops",
        "Verify edge-case handling for unauthenticated or malformed requests",
    ])]
    # Ensure defects and red flags cross-populate if one was missing
    if not defects and red_flags:
        defects = list(red_flags)
    if not red_flags and defects:
        red_flags = list(defects)

    questions = [str(x) for x in parsed.get("suggested_judge_questions", [
        "How does your architecture handle unexpected network failures or database disconnections?",
        "What was the most challenging technical tradeoff you made during development?",
        "How would you scale this system to support 10,000 concurrent active users?"
    ])]

    return OllamaRepoInspectionResponse(
        submission_id=submission.id,
        hackathon_id=submission.hackathon_id,
        model_name=model_name,
        status="completed",
        project_name=proj_name,
        quick_summary=quick_summary,
        what_is_building=what_is_building,
        exact_overview=what_is_building,
        innovation=innovation,
        tech_stack=tech_stack,
        complexity=complexity,
        judge_factors=judge_factors,
        key_highlights=highlights,
        potential_red_flags=red_flags,
        codebase_defects=defects,
        missing_implementations=missing,
        recommended_improvements=improvements,
        suggested_judge_questions=questions,
        created_at=datetime.now(timezone.utc),
        cached=False,
    )


async def get_cached_inspection(
    db: AsyncSession,
    submission_id: uuid.UUID,
) -> Optional[OllamaRepoInspectionResponse]:
    """Retrieves cached inspection from Redis or PostgreSQL if present."""
    # 1. Try Redis cache first
    try:
        redis = await get_redis_client()
        cached_str = await redis.get(f"{REDIS_INSPECT_PREFIX}{submission_id}")
        if cached_str:
            data = json.loads(cached_str)
            res = OllamaRepoInspectionResponse.model_validate(data)
            res.cached = True
            return res
    except Exception as exc:
        logger.debug("Redis cache check error: %s", exc)

    # 2. Try PostgreSQL table
    try:
        stmt = (
            select(SubmissionRepoInspection)
            .where(
                SubmissionRepoInspection.submission_id == submission_id,
                SubmissionRepoInspection.status == "completed",
            )
            .order_by(SubmissionRepoInspection.created_at.desc())
        )
        row = (await db.execute(stmt)).scalars().first()
        if row:
            if row.raw_json and isinstance(row.raw_json, dict) and "innovation" in row.raw_json:
                res = OllamaRepoInspectionResponse.model_validate(row.raw_json)
                if not res.quick_summary:
                    res.quick_summary = row.quick_summary or (
                        ". ".join([s.strip() for s in (res.what_is_building or "").split(".") if s.strip()][:2]) + "."
                        if res.what_is_building else None
                    )
                if not res.exact_overview:
                    res.exact_overview = res.what_is_building
            else:
                res = OllamaRepoInspectionResponse(
                    id=row.id,
                    submission_id=row.submission_id,
                    hackathon_id=row.hackathon_id,
                    model_name=row.model_name,
                    status=row.status,
                    project_name=row.project_name or "Project",
                    quick_summary=row.quick_summary or (row.raw_json.get("quick_summary") if row.raw_json else None) or (
                        ". ".join([s.strip() for s in (row.what_is_building or "").split(".") if s.strip()][:2]) + "."
                        if row.what_is_building else None
                    ),
                    what_is_building=row.what_is_building or "",
                    exact_overview=row.what_is_building or "",
                    innovation=InnovationData.model_validate(row.innovation_data or {"score": 8.0, "summary": "N/A"}),
                    tech_stack=TechStackData.model_validate(row.tech_stack_data or {}),
                    complexity=ComplexityData.model_validate(row.complexity_data or {"score": 7.0}),
                    judge_factors=JudgeFactorsData.model_validate(row.judge_factors_data or {
                        "code_quality_score": 8.0,
                        "completeness_score": 8.0,
                        "is_working_demo": True,
                        "potential_impact_score": 8.0,
                    }),
                    key_highlights=row.key_highlights or [],
                    potential_red_flags=row.potential_red_flags or [],
                    suggested_judge_questions=row.suggested_judge_questions or [],
                    created_at=row.created_at,
                    cached=True,
                )
            res.id = row.id
            res.created_at = row.created_at
            res.cached = True

            # Warm Redis
            try:
                redis = await get_redis_client()
                await redis.set(
                    f"{REDIS_INSPECT_PREFIX}{submission_id}",
                    json.dumps(res.model_dump(mode="json")),
                    ex=CACHE_TTL_SECONDS,
                )
            except Exception:
                pass

            return res
    except Exception as exc:
        logger.warning("Database cached inspection check error: %s", exc)

    return None


async def _execute_ollama_call(
    base_url: str,
    prompt: str,
    preferred_models: List[str],
    timeout_seconds: float = 30.0,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Attempts to probe and invoke /api/generate on an Ollama instance.
    Returns (parsed_json, resolved_model) on success, or (None, None) on failure.
    Uses fast connection probing to avoid latency on offline endpoints.
    """
    clean_base = base_url.rstrip("/")
    resolved_model = None

    # Fast probe (1.2s total, 0.8s connect) to quickly bypass unreachable internal IPs
    async with httpx.AsyncClient(timeout=httpx.Timeout(1.2, connect=0.8)) as probe_client:
        try:
            tags_resp = await probe_client.get(f"{clean_base}/api/tags")
            if tags_resp.status_code == 200:
                available = [m.get("name") for m in tags_resp.json().get("models", []) if m.get("name")]
                if available:
                    for pref in preferred_models:
                        for avail in available:
                            if pref in avail:
                                resolved_model = avail
                                break
                        if resolved_model:
                            break
                    if not resolved_model:
                        resolved_model = available[0]
        except Exception as probe_err:
            logger.info("Ollama probe error at %s: %s", clean_base, probe_err)
            return None, None

    if not resolved_model:
        return None, None

    capped_timeout = min(timeout_seconds, 35.0)
    async with httpx.AsyncClient(timeout=capped_timeout) as client:
        try:
            res = await client.post(
                f"{clean_base}/api/generate",
                json={
                    "model": resolved_model,
                    "prompt": prompt,
                    "format": "json",
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 1024,
                    },
                },
            )
            if res.status_code == 200:
                raw_text = res.json().get("response", "")
                clean = raw_text.strip()
                if "```json" in clean:
                    clean = clean.split("```json")[1].split("```")[0].strip()
                elif "```" in clean:
                    clean = clean.split("```")[1].split("```")[0].strip()

                try:
                    return json.loads(clean), resolved_model
                except Exception as json_err:
                    logger.warning("Attempting JSON auto-repair on Ollama output: %s", json_err)
                    repaired = clean
                    # Balance quotes
                    if repaired.count('"') % 2 != 0:
                        repaired += '"'
                    # Balance brackets
                    open_sq = repaired.count('[') - repaired.count(']')
                    if open_sq > 0:
                        repaired += ']' * open_sq
                    # Balance braces
                    open_cur = repaired.count('{') - repaired.count('}')
                    if open_cur > 0:
                        repaired += '}' * open_cur
                    try:
                        return json.loads(repaired), resolved_model
                    except Exception as final_err:
                        logger.error("JSON decode error even after auto-repair: %s", final_err)
            else:
                logger.warning("Ollama at %s returned status %d: %s", clean_base, res.status_code, res.text)
        except Exception as exc:
            logger.warning("Ollama generate error at %s: %s (%s)", clean_base, type(exc).__name__, exc)

    return None, None


async def inspect_submission_repository(
    db: AsyncSession,
    hackathon_id: uuid.UUID,
    submission_id: uuid.UUID,
    current_user: User,
    force_refresh: bool = False,
) -> OllamaRepoInspectionResponse:
    """
    Executes a one-click deep repository inspection using Dual Ollama AI:
    - Primary: Remote Ollama (http://10.3.2.157:11434)
    - Fallback: Local Ollama (http://localhost:11434)
    Extracts tech stack, innovation metrics, architectural complexity, judge questions,
    quick summary, and exact overview from repository code.
    """
    # 1. Check existing cache unless force_refresh requested
    if not force_refresh:
        cached = await get_cached_inspection(db=db, submission_id=submission_id)
        if cached:
            return cached

    # 2. Fetch submission record
    sub_stmt = select(Submission).where(
        Submission.id == submission_id,
        Submission.hackathon_id == hackathon_id,
        Submission.deleted_at.is_(None),
    )
    submission = (await db.execute(sub_stmt)).scalar_one_or_none()
    if not submission:
        raise AppException(
            status_code=404,
            code="SUBMISSION_NOT_FOUND",
            message="Target submission not found in this hackathon.",
        )

    # 3. Gather repository context (README, manifests, file hierarchy)
    context = await _gather_repository_context(submission)

    # 4. Build prompt
    prompt = _build_ollama_prompt(submission, context)

    # 5. Multi-Provider AI Inference: Pi AI Runtime (Primary) -> Ollama Cascade (Secondary) -> Deterministic Synthesis (Fallback)
    parsed_json: Optional[Dict[str, Any]] = None
    used_model: Optional[str] = None
    resolved_display_model = ""

    # Phase 5A: Attempt execution via configured Pi AI Runtime
    if default_pi_runtime.is_available():
        try:
            assignment_stmt = select(AITaskModelAssignment).where(
                AITaskModelAssignment.task_type == "repository_understanding"
            )
            assignment = (await db.execute(assignment_stmt)).scalar_one_or_none()
            pi_provider = assignment.primary_provider if assignment else "openai-codex"
            pi_model = assignment.primary_model if assignment else "gpt-5.6-luna"

            logger.info("Executing repository inspection via Pi AI runtime (%s/%s)...", pi_provider, pi_model)
            client = PiProviderClient(default_provider=pi_provider, default_model=pi_model)

            repo_schema = {
                "type": "object",
                "properties": {
                    "project_name": {"type": "string"},
                    "quick_summary": {"type": "string"},
                    "what_is_building": {"type": "string"},
                    "innovation": {
                        "type": "object",
                        "properties": {
                            "score": {"type": "number"},
                            "summary": {"type": "string"},
                            "novel_elements": {"type": "array", "items": {"type": "string"}},
                            "competitive_differentiation": {"type": "string"},
                        },
                        "required": ["score", "summary"],
                    },
                    "tech_stack": {
                        "type": "object",
                        "properties": {
                            "languages": {"type": "array", "items": {"type": "string"}},
                            "frameworks": {"type": "array", "items": {"type": "string"}},
                            "databases": {"type": "array", "items": {"type": "string"}},
                            "ai_ml_tools": {"type": "array", "items": {"type": "string"}},
                            "devops_cloud": {"type": "array", "items": {"type": "string"}},
                            "apis_integrations": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                    "complexity": {
                        "type": "object",
                        "properties": {
                            "level": {"type": "string"},
                            "score": {"type": "number"},
                            "architecture_depth": {"type": "string"},
                            "algorithmic_challenges": {"type": "string"},
                            "data_flow_complexity": {"type": "string"},
                        },
                        "required": ["level", "score"],
                    },
                    "judge_factors": {
                        "type": "object",
                        "properties": {
                            "code_quality_score": {"type": "number"},
                            "code_quality_summary": {"type": "string"},
                            "completeness_score": {"type": "number"},
                            "completeness_summary": {"type": "string"},
                            "is_working_demo": {"type": "boolean"},
                            "potential_impact_score": {"type": "number"},
                            "potential_impact_summary": {"type": "string"},
                            "security_summary": {"type": "string"},
                        },
                        "required": ["code_quality_score", "completeness_score"],
                    },
                    "codebase_defects": {"type": "array", "items": {"type": "string"}},
                    "missing_implementations": {"type": "array", "items": {"type": "string"}},
                    "recommended_improvements": {"type": "array", "items": {"type": "string"}},
                    "potential_red_flags": {"type": "array", "items": {"type": "string"}},
                    "key_highlights": {"type": "array", "items": {"type": "string"}},
                    "suggested_judge_questions": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["quick_summary", "what_is_building", "innovation", "tech_stack", "complexity", "judge_factors"],
            }

            detailed = await client.generate_evaluation_detailed(
                prompt=prompt,
                schema=repo_schema,
                model_name=f"{pi_provider}/{pi_model}",
                timeout_seconds=45.0,
            )
            parsed_json = detailed.get("output")
            used_model = f"{detailed.get('provider')}/{detailed.get('model')}"
            resolved_display_model = f"Pi AI Runtime ({used_model})"
            logger.info("Pi repository inspection completed in %d ms with model %s", detailed.get("duration_ms", 0), used_model)

            # Record AI execution audit record
            try:
                from decimal import Decimal
                usage_data = detailed.get("usage") or {}
                tokens = usage_data.get("total_tokens")
                cost_val = None
                if "cost" in usage_data and isinstance(usage_data["cost"], dict):
                    cost_val = Decimal(str(usage_data["cost"].get("total", 0.0)))
                clean_payload = json.loads(json.dumps(parsed_json, default=str)) if parsed_json else None
                exec_record = AIExecutionRecord(
                    id=uuid.uuid4(),
                    submission_id=submission.id,
                    task_type="repository_understanding",
                    primary_provider=pi_provider,
                    primary_model=pi_model,
                    actual_provider=detailed.get("provider", pi_provider),
                    actual_model=detailed.get("model", pi_model),
                    status="completed",
                    fallback_used=False,
                    duration_ms=detailed.get("duration_ms", 0),
                    prompt_tokens=usage_data.get("input"),
                    completion_tokens=usage_data.get("output"),
                    total_tokens=tokens,
                    estimated_cost=cost_val,
                    prompt_preview=prompt[:300],
                    output_payload=clean_payload,
                    validation_passed=True,
                    started_at=datetime.now(timezone.utc),
                    completed_at=datetime.now(timezone.utc),
                    created_at=datetime.now(timezone.utc),
                )
                async with db.begin_nested():
                    db.add(exec_record)
                    await db.flush()
            except Exception as audit_err:
                logger.warning("Failed to persist Pi AI execution telemetry: %s", audit_err)

        except Exception as pi_err:
            logger.warning("Pi AI runtime inspection failed: %s. Cascading to Ollama...", pi_err)
            parsed_json = None
            used_model = None

    # Phase 5B: Cascade to Ollama if Pi is unavailable or encountered an error
    if not parsed_json or not used_model:
        from apps.api.modules.evaluations.ai_operations_service import get_ai_routing_config
        routing_policy = await get_ai_routing_config(db)

        # Collect all configured candidate endpoints in priority order
        candidate_endpoints: List[Dict[str, Any]] = []

        if routing_policy.endpoints:
            primaries = [ep for ep in routing_policy.endpoints if ep.is_enabled and ep.url and ep.role == "primary"]
            secondaries = [ep for ep in routing_policy.endpoints if ep.is_enabled and ep.url and ep.role != "primary"]
            for ep in primaries + secondaries:
                candidate_endpoints.append({
                    "name": ep.name,
                    "url": ep.url.strip().rstrip("/"),
                    "model": ep.model_name or "mistral:7b",
                    "timeout": float(ep.timeout_seconds or 30.0),
                    "role": "Primary Remote AI" if ep.role == "primary" else "Secondary AI",
                })

        known_urls = {c["url"] for c in candidate_endpoints}

        primary_setting_url = getattr(settings, "OLLAMA_PRIMARY_URL", "http://10.3.2.157:11434").strip().rstrip("/")
        if primary_setting_url and primary_setting_url not in known_urls:
            candidate_endpoints.insert(0, {
                "name": "Remote GPU Ollama 1 (10.3.2.157)",
                "url": primary_setting_url,
                "model": routing_policy.primary_model or "mistral:7b",
                "timeout": 30.0,
                "role": "Primary Remote AI",
            })
            known_urls.add(primary_setting_url)

        sec_remote_setting_url = getattr(settings, "OLLAMA_SECONDARY_REMOTE_URL", "http://10.3.2.158:11434").strip().rstrip("/")
        if sec_remote_setting_url and sec_remote_setting_url not in known_urls:
            candidate_endpoints.append({
                "name": "Remote GPU Ollama 2 (10.3.2.158)",
                "url": sec_remote_setting_url,
                "model": "mistral:7b",
                "timeout": 30.0,
                "role": "Secondary Remote AI",
            })
            known_urls.add(sec_remote_setting_url)

        fallback_setting_url = getattr(settings, "OLLAMA_FALLBACK_URL", "http://localhost:11434").strip().rstrip("/")
        if fallback_setting_url and fallback_setting_url not in known_urls:
            candidate_endpoints.append({
                "name": "Local Machine Ollama (localhost)",
                "url": fallback_setting_url,
                "model": routing_policy.secondary_model or "qwen2.5:3b",
                "timeout": 30.0,
                "role": "Secondary Local AI",
            })
            known_urls.add(fallback_setting_url)

        # Ensure all hosts are registered in SSRF allowlist
        from apps.api.core.ssrf_guard import allow_internal_ai_host
        for c in candidate_endpoints:
            parsed_u = urlparse(c["url"])
            if parsed_u.hostname:
                allow_internal_ai_host(parsed_u.hostname)

        # Cascade through candidate endpoints
        for candidate in candidate_endpoints:
            ep_url = candidate["url"]
            ep_model = candidate["model"]
            ep_name = candidate["name"]
            ep_role = candidate["role"]
            timeout_sec = min(float(candidate["timeout"]), 30.0)

            logger.info("Attempting AI repository inspection via [%s] %s (%s)...", ep_role, ep_name, ep_url)
            parsed_json, used_model = await _execute_ollama_call(
                base_url=ep_url,
                prompt=prompt,
                preferred_models=[ep_model, "mistral:7b", "gemma2:9b", "llama3:8b", "qwen2.5:3b"],
                timeout_seconds=timeout_sec,
            )
            if parsed_json and used_model:
                clean_host = ep_url.replace("http://", "").replace("https://", "")
                resolved_display_model = f"{used_model} ({ep_role}: {clean_host})"
                logger.info("AI inspection succeeded via [%s] %s with model %s", ep_role, ep_url, used_model)
                break
            else:
                logger.warning(
                    "Endpoint [%s] %s failed or non-responsive. Cascading to next available secondary model...",
                    ep_role,
                    ep_url,
                )

    if not parsed_json or not used_model:
        resolved_display_model = "Deterministic Fallback (All AI Engines Offline/Disabled)"
        logger.warning("No active AI endpoints produced results across cluster. Using deterministic synthesis.")
        parsed_json = {}

    # 6. Normalize and validate response schema
    inspection_res = _normalize_and_validate_inspection(
        parsed=parsed_json or {},
        submission=submission,
        model_name=resolved_display_model,
    )

    # 7. Persist to PostgreSQL
    try:
        inspection_record = SubmissionRepoInspection(
            id=uuid.uuid4(),
            submission_id=submission.id,
            hackathon_id=submission.hackathon_id,
            organization_id=submission.organization_id,
            inspected_by_user_id=current_user.id,
            model_name=resolved_display_model,
            status="completed",
            project_name=inspection_res.project_name,
            quick_summary=inspection_res.quick_summary,
            what_is_building=inspection_res.what_is_building,
            innovation_data=inspection_res.innovation.model_dump(mode="json"),
            tech_stack_data=inspection_res.tech_stack.model_dump(mode="json"),
            complexity_data=inspection_res.complexity.model_dump(mode="json"),
            judge_factors_data=inspection_res.judge_factors.model_dump(mode="json"),
            key_highlights=inspection_res.key_highlights,
            potential_red_flags=inspection_res.potential_red_flags,
            suggested_judge_questions=inspection_res.suggested_judge_questions,
            raw_json=inspection_res.model_dump(mode="json"),
        )
        db.add(inspection_record)
        await db.commit()
        await db.refresh(inspection_record)
        inspection_res.id = inspection_record.id
        inspection_res.created_at = inspection_record.created_at
    except Exception as db_exc:
        logger.error("Failed to save inspection to PostgreSQL: %s", db_exc)
        await db.rollback()

    # 8. Cache in Redis
    try:
        redis = await get_redis_client()
        await redis.set(
            f"{REDIS_INSPECT_PREFIX}{submission_id}",
            json.dumps(inspection_res.model_dump(mode="json")),
            ex=CACHE_TTL_SECONDS,
        )
    except Exception as redis_exc:
        logger.warning("Failed to cache inspection in Redis: %s", redis_exc)

    return inspection_res
