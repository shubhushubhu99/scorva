"""
Scorva Criterion-Specific Evaluation Framework.

Provides explicit, non-overlapping evaluation specifications and 0-to-10 scoring anchors
for the five standard hackathon criteria, plus dynamic support for organizer-defined criteria.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class CriterionFramework(BaseModel):
    """
    Explicit evaluation specification for a single criterion.
    Prevents cross-criterion bleeding, stack-size bias, and unanchored scores.
    """
    model_config = ConfigDict(extra="forbid")

    criterion_key: str
    display_title: str
    objective: str
    positive_indicators: List[str]
    negative_indicators: List[str]
    irrelevant_factors: List[str]  # Factors strictly forbidden from affecting this criterion
    required_evidence: List[str]
    optional_evidence: List[str]
    scoring_anchors: Dict[int, str]  # Detailed definitions for every integer level 0 through 10
    deduction_relevance_rules: List[str]
    overlap_prevention_rules: List[str]
    insufficient_evidence_behavior: str


# ==============================================================================
# Standard 5 Criteria Frameworks
# ==============================================================================

INNOVATION_CRITERION = CriterionFramework(
    criterion_key="innovation_originality",
    display_title="Innovation & Originality",
    objective=(
        "Assess the uniqueness of the core concept, creative problem-solving approach, "
        "and differentiation from standard boilerplate, tutorials, and common hackathon templates."
    ),
    positive_indicators=[
        "Novel domain modeling or unique synthesis of two previously unconnected workflows.",
        "Custom heuristic, proprietary algorithm, or creative approach beyond generic CRUD.",
        "Clear, demonstrated competitive differentiation against obvious incumbent tools.",
        "Original UX paradigm or workflow design that meaningfully simplifies complex interactions.",
    ],
    negative_indicators=[
        "Unmodified or minimally altered clone of a standard tutorial, starter kit, or boilerplate.",
        "Generic application of an off-the-shelf LLM prompt without custom domain logic.",
        "Trivial CRUD wrapper around a public database or standard API without value-add logic.",
        "Overstated marketing claims with no actual conceptual or mechanical novelty in code.",
    ],
    irrelevant_factors=[
        "Technology stack size or number of frameworks used (a simple stack can be highly innovative).",
        "Code formatting, linting rules, or variable naming conventions (evaluated under Code Quality).",
        "Presence of unit test suites or CI configurations (evaluated under Code Quality).",
        "Production deployment infrastructure, Kubernetes, or Docker orchestration (evaluated under Architecture).",
    ],
    required_evidence=[
        "Core domain algorithms or unique business workflow modules in source code.",
        "Explanations in README or documentation describing the unique problem approach.",
    ],
    optional_evidence=[
        "Comparative benchmark or differentiation matrix in repository docs.",
        "Patent/research citations or creative domain modeling manifests.",
    ],
    scoring_anchors={
        0: "No original contribution. Pure standard template or unaltered boilerplate clone with no added concept.",
        1: "Minimal trivial alterations to a standard template (e.g., changed brand name or colors only).",
        2: "Very weak originality. Standard generic CRUD application with zero differentiated concept.",
        3: "Slight novelty in concept, but technical realization relies entirely on standard tutorial patterns.",
        4: "Partially novel concept, but differentiation from common hackathon templates is vague or minimal.",
        5: "Moderate conceptual innovation. Addresses a specific niche, but mechanical execution uses standard boilerplate patterns.",
        6: "Good innovation. Clear unique angle or creative problem-solving mechanism, with identifiable precedent.",
        7: "Distinct, well-differentiated concept with custom domain logic, clearly separated from standard templates.",
        8: "Strong innovation. Novel algorithmic or workflow synthesis with clear, compelling competitive differentiation.",
        9: "Exceptional creativity. Highly original problem-solving mechanism that pioneers a new workflow or paradigm.",
        10: "Breakthrough innovation. Unprecedented architectural or algorithmic contribution with transformative potential.",
    },
    deduction_relevance_rules=[
        "Deductions apply only if the core approach is derivative, unoriginal, or copied without differentiation.",
        "Do NOT deduct innovation points for software bugs, missing unit tests, or deployment omissions.",
    ],
    overlap_prevention_rules=[
        "Lack of working code is evaluated under Execution & Completeness, NOT under Innovation.",
        "Poor code readability is evaluated under Code Quality, NOT under Innovation.",
    ],
    insufficient_evidence_behavior=(
        "If repository documentation or core logic is truncated, flag uncertainty and assign a baseline "
        "neutral rating (5.0) with an explicit unverified notice, rather than penalizing to zero."
    ),
)


TECHNICAL_COMPLEXITY_CRITERION = CriterionFramework(
    criterion_key="technical_complexity_architecture",
    display_title="Technical Complexity & Architecture",
    objective=(
        "Assess architectural rigor, separation of concerns, data flow modularity, "
        "and the handling of non-trivial engineering challenges (concurrency, state, caching, protocols)."
    ),
    positive_indicators=[
        "Decoupled multi-tier architecture with clean layer boundaries (API, Domain, Data, Workers).",
        "Appropriate handling of asynchronous workflows, state machines, background tasks, or real-time protocols.",
        "Well-structured schema modeling, relational integrity, migrations, and transactional boundaries.",
        "Thoughtful engineering tradeoffs balancing performance, simplicity, and maintainability.",
    ],
    negative_indicators=[
        "Monolithic spaghetti code with frontend, business logic, and raw database queries mixed in one file.",
        "Artificial, unnecessary complexity or over-engineering that degrades reliability without benefit.",
        "Absence of error handling boundaries, unhandled network drops, or lack of state synchronization.",
        "Synchronous blocking of request loops on heavy computational or external network calls.",
    ],
    irrelevant_factors=[
        "Visual design, color choices, or dark-mode styling (evaluated under Usability/Impact).",
        "Novelty or commercial market viability of the idea (evaluated under Innovation/Impact).",
        "Number of third-party libraries installed (stack size != architectural complexity).",
        "Omission of unrequested enterprise infrastructure, Kubernetes manifests, or microservices (Directive 6).",
        "Spelling or typographical errors in comments or documentation (irrelevant).",
    ],
    required_evidence=[
        "Backend/frontend directory layout and module boundary definitions in source code.",
        "Data persistence schemas, migrations, or data flow controllers.",
    ],
    optional_evidence=[
        "Architecture diagrams, sequence diagrams, or formal specification documents.",
        "Queue/worker definitions, Redis/caching configurations, or streaming protocols.",
    ],
    scoring_anchors={
        0: "No architectural structure. Flat chaotic files with completely unseparated responsibilities.",
        1: "Extremely primitive structure. Single script mixing UI, routing, and data with no modularity.",
        2: "Very weak engineering. Rudimentary script structure with severe boundary bleeding and synchronous locks.",
        3: "Basic two-tier separation, but core logic is brittle, unstructured, and lacks error boundaries.",
        4: "Partial modularity with significant design flaws (e.g. tightly coupled layers, missing state management).",
        5: "Standard baseline architecture. Typical MVC/layered structure with basic separation of concerns.",
        6: "Competent architecture with clear module decoupling and sensible data boundaries, but minor leaks.",
        7: "Solid architectural rigor with clean interfaces, proper async/concurrency handling, and robust schemas.",
        8: "High architectural depth. Sophisticated decoupled pipelines, clean domain boundaries, and strong design patterns.",
        9: "Exceptional engineering rigor. Flawless modularity, elegant concurrency/caching, and comprehensive resilience.",
        10: "Masterclass engineering. World-class distributed or modular architecture with state-of-the-art patterns.",
    },
    deduction_relevance_rules=[
        "Deductions must point to concrete architectural flaws: tight coupling, blocking calls, leaky abstractions.",
        "Do NOT deduct complexity points because a project intentionally chose a clean, simple architecture.",
    ],
    overlap_prevention_rules=[
        "Code style and linting are Code Quality issues, NOT Architecture issues.",
        "Incomplete feature implementation is an Execution issue, NOT an Architecture issue.",
    ],
    insufficient_evidence_behavior=(
        "If deep backend directories were unindexed or excluded from the snapshot, clearly state that architectural "
        "depth is partially verified rather than assuming the backend does not exist."
    ),
)


CODE_QUALITY_CRITERION = CriterionFramework(
    criterion_key="code_quality_cleanliness",
    display_title="Code Quality & Cleanliness",
    objective=(
        "Assess code maintainability, readability, type safety, structured exception handling, "
        "defensive input validation, automated test suites, and clean dependency management."
    ),
    positive_indicators=[
        "Consistent static typing (e.g. TypeScript, Pydantic, Python type hints) across boundaries.",
        "Comprehensive automated tests (unit, integration, or e2e) verifying critical functional paths.",
        "Structured, centralized exception handling and defensive boundary input validation.",
        "Clean, self-documenting code with meaningful naming, concise modules, and zero hardcoded secrets.",
    ],
    negative_indicators=[
        "Hardcoded API keys, database credentials, or secret tokens committed into repository source.",
        "Pervasive untyped data structures (`any`, untyped dicts), dead code blocks, or commented-out debris.",
        "Empty `try/except: pass` blocks suppressing critical system errors without logging.",
        "Complete absence of automated tests, reproducible build configs, or linting standards.",
    ],
    irrelevant_factors=[
        "Commercial appeal or business monetization model (evaluated under Potential Impact).",
        "Elegance of UI graphics or animation smoothness (evaluated under Usability).",
        "Technological difficulty of the problem domain (evaluated under Technical Complexity).",
        "Whether optional hackathon tracks were attempted (irrelevant).",
    ],
    required_evidence=[
        "Source code files demonstrating function definitions, type annotations, and error handling.",
        "Package manifest (e.g. `package.json`, `pyproject.toml`, `requirements.txt`).",
    ],
    optional_evidence=[
        "Automated test suites (`tests/`, `pytest`, `jest`) and CI workflow configurations.",
        "Linter/formatter configurations (`eslint`, `ruff`, `prettier`).",
    ],
    scoring_anchors={
        0: "Unreadable, dangerous code. Hardcoded credentials, no formatting, broken syntax, pervasive errors.",
        1: "Extremely poor hygiene. Widespread untyped spaghetti code, silent error suppression, zero structure.",
        2: "Very low quality. Messy naming, zero type safety, pervasive copy-pasted blocks, no error handling.",
        3: "Poor maintainability. Scattered structure, inconsistent styling, minimal error checks, no test suites.",
        4: "Below-average cleanliness. Some modularity, but frequent unhandled exception paths and zero automated tests.",
        5: "Average code quality. Readable code with basic structure, standard formatting, but sparse tests and loose typing.",
        6: "Good code quality. Clear naming, consistent typing, reasonable error handling, and basic automated tests.",
        7: "High quality. Modular structure, strong typing, robust error handling, clean manifests, and solid test coverage.",
        8: "Very clean code. Defensive validation, comprehensive unit tests, clear documentation, and zero credential leakage.",
        9: "Exceptional hygiene. Exemplary typing, extensive test suites with edge cases, and immaculate readability.",
        10: "Flawless code craftsmanship. Production-grade typing, exhaustive automated tests, and beautiful documentation.",
    },
    deduction_relevance_rules=[
        "Deductions must cite specific code cleanliness flaws: exposed secrets, silent exception suppression, untyped boundaries.",
        "Penalize exposed credentials heavily as a severe Code Quality & Security defect.",
    ],
    overlap_prevention_rules=[
        "Do NOT penalize a missing feature under Code Quality; missing features belong exclusively to Execution & Completeness.",
        "Do NOT penalize lack of architectural microservices under Code Quality.",
    ],
    insufficient_evidence_behavior=(
        "If test folders are missing from snapshot, evaluate visible source quality directly and note tests as UNVERIFIED."
    ),
)


EXECUTION_COMPLETENESS_CRITERION = CriterionFramework(
    criterion_key="execution_completeness",
    display_title="Execution & Completeness",
    objective=(
        "Assess whether the project represents a genuine, working, end-to-end implementation "
        "delivering on claimed core capabilities, versus non-functional placeholder mocks or UI stubs."
    ),
    positive_indicators=[
        "Functional end-to-end user workflows running from input trigger through processing to persistent result.",
        "Absence of placeholder mock stubs (`TODO: implement`, dummy hardcoded responses) on core paths.",
        "Verified database persistence, live API integration, and verifiable output generation.",
        "Demonstrated working state verified through live demo evidence, test executions, or runnable code.",
    ],
    negative_indicators=[
        "Preponderance of stubbed endpoints returning static dummy mock JSON.",
        "Frontend with beautiful interactive buttons that trigger dead handlers or dummy console logs.",
        "Core capabilities claimed in README are completely absent from submitted source code.",
        "Broken startup dependencies or fatal syntax errors preventing code execution.",
    ],
    irrelevant_factors=[
        "Whether the team built optional/bonus features that were never claimed (irrelevant).",
        "Novelty or differentiation of the concept (evaluated under Innovation).",
        "Sophistication of visual icons or brand logos (evaluated under Usability/Impact).",
        "Algorithmic complexity (evaluated under Technical Complexity).",
    ],
    required_evidence=[
        "Implemented endpoint handlers, business logic controllers, and database interactions.",
        "Runnable entrypoints (`main.py`, `index.ts`, `server.ts`).",
    ],
    optional_evidence=[
        "Working demo video link, live URL deployment, or verified automated integration test run.",
        "Seed scripts, database migration files, or sample input fixtures.",
    ],
    scoring_anchors={
        0: "Non-functional project. Broken syntax, missing entrypoints, or 100% stubbed placeholders.",
        1: "Essentially non-functional. Entrypoint exists but crashes immediately; core features are entirely absent.",
        2: "Very minimal implementation. Only basic boilerplate boots; virtually all claimed features are stubs.",
        3: "Fragmentary execution. A few disconnected functions exist, but no complete end-to-end workflow runs.",
        4: "Partially working prototype. Core workflow is half-implemented with major paths stubbed or hardcoded.",
        5: "Moderate execution. Primary baseline path functions end-to-end, but secondary paths are mock stubs.",
        6: "Substantially working implementation. Core feature works with live data; minor peripheral features are incomplete.",
        7: "Complete functional prototype. Entire core workflow runs reliably with live persistence and realistic data.",
        8: "High execution completeness. Robust end-to-end implementation with verified data flows and minimal stubs.",
        9: "Exemplary execution. Fully functional, battle-tested implementation with edge-case handling and strong demo viability.",
        10: "Flawless production readiness. Completely realized product with zero stubs, comprehensive flows, and live deployment.",
    },
    deduction_relevance_rules=[
        "Deductions apply when claimed mandatory features are missing, broken, or substituted with static mocks.",
        "Do NOT deduct points for missing optional features that the team never claimed or promised.",
    ],
    overlap_prevention_rules=[
        "Do NOT deduct Execution points because the concept is simple (evaluated under Complexity).",
        "Do NOT deduct Execution points because the code lacks comments (evaluated under Code Quality).",
    ],
    insufficient_evidence_behavior=(
        "If repository files are truncated or incomplete, label completeness as PARTIALLY_VERIFIED rather than "
        "assuming unindexed paths are fake stubs."
    ),
)


POTENTIAL_IMPACT_CRITERION = CriterionFramework(
    criterion_key="potential_impact_usability",
    display_title="Potential Impact & Usability",
    objective=(
        "Assess real-world usefulness, target audience relevance, problem-solution alignment, "
        "user experience clarity, and practical viability beyond the hackathon environment."
    ),
    positive_indicators=[
        "Direct, compelling solution addressing a genuine, well-defined user or enterprise pain point.",
        "Intuitive, accessible user interface with clear affordances, meaningful feedback, and low friction.",
        "Realistic operational model with reasonable assumptions regarding data availability and cost.",
        "Measurable value creation (e.g. saves hours of manual work, prevents fraud, enhances safety).",
    ],
    negative_indicators=[
        "Solution in search of a problem; convoluted workflow that worsens the user experience.",
        "Dangerous security/privacy exposure that renders the tool unsafe for real-world deployment.",
        "Unrealistic operational assumptions (e.g. requires illegal access, massive manual scraping, unviable APIs).",
        "Confusing, inaccessible UI with uninformative error messages and broken user journeys.",
    ],
    irrelevant_factors=[
        "Omission of unrequested cloud deployment manifests or enterprise infrastructure (Directive 6).",
        "Whether the code was written in Python vs TypeScript vs Go (evaluated under Code Quality/Complexity).",
        "Whether the team has incorporated a legal business entity (irrelevant in hackathon scope).",
        "Presence of unit test mocks (evaluated under Code Quality).",
        "Number of lines of code (irrelevant).",
    ],
    required_evidence=[
        "Problem statement definition in README or application context.",
        "User journey flows in code (UI views, API contracts, or CLI interactions).",
    ],
    optional_evidence=[
        "User feedback, demo walkthrough screenshots, or domain impact metrics.",
        "Documentation of target personas and real-world deployment considerations.",
    ],
    scoring_anchors={
        0: "Zero practical utility. Nonsensical application with no discernible real-world purpose or user base.",
        1: "Virtually no value. Extreme friction, counter-productive workflow, or impossible assumptions.",
        2: "Very low impact. Trivial gimmick with negligible usefulness and severe real-world barriers.",
        3: "Marginal utility. Solves an artificial problem with high user friction and poor practical viability.",
        4: "Limited impact. Solves a real problem, but user experience is convoluted and viability assumptions are weak.",
        5: "Moderate utility. Plausible use case for a small niche, but high friction or significant security/legal risks.",
        6: "Good real-world relevance. Solves a genuine pain point with clean UX, though scope remains narrow.",
        7: "Substantial impact. Compelling utility for clear target users, intuitive experience, and practical viability.",
        8: "High impact & polish. Solves a major pain point efficiently with excellent UX and realistic deployment path.",
        9: "Transformative potential. Outstanding practical utility, delightful user experience, and massive value multiplier.",
        10: "Exceptional real-world solution. Immediate production utility, industry-grade UX, and profound societal or business impact.",
    },
    deduction_relevance_rules=[
        "Deductions must cite genuine usability barriers, unrealistic operational assumptions, or severe real-world hazards.",
        "Do NOT deduct impact points because the project was implemented with a simple technology stack.",
    ],
    overlap_prevention_rules=[
        "Security code bugs belong under Code Quality, EXCEPT when they fundamentally invalidate real-world deployment safety.",
        "Missing backend features belong under Execution, NOT under Impact.",
    ],
    insufficient_evidence_behavior=(
        "If target audience or use cases are not documented, assign a neutral baseline score (5.0) and flag lack of problem documentation."
    ),
)


# ==============================================================================
# Framework Registry & Dynamic Resolution
# ==============================================================================

STANDARD_FRAMEWORKS: Dict[str, CriterionFramework] = {
    "innovation_originality": INNOVATION_CRITERION,
    "technical_complexity_architecture": TECHNICAL_COMPLEXITY_CRITERION,
    "code_quality_cleanliness": CODE_QUALITY_CRITERION,
    "execution_completeness": EXECUTION_COMPLETENESS_CRITERION,
    "potential_impact_usability": POTENTIAL_IMPACT_CRITERION,
}


def get_all_standard_criteria_frameworks() -> List[CriterionFramework]:
    """Returns list of all 5 standard criteria frameworks."""
    return list(STANDARD_FRAMEWORKS.values())


def get_criterion_framework(title_or_key: str) -> CriterionFramework:
    """
    Resolves the CriterionFramework for a criterion by title or key.
    If the criterion is organizer-defined and does not match standard 5,
    dynamically constructs a fair, anchored framework based on the title.
    """
    clean = title_or_key.strip().lower()

    if "innovat" in clean or "origin" in clean or "creativ" in clean:
        return INNOVATION_CRITERION
    if "complex" in clean or "architect" in clean or "technical" in clean or "depth" in clean:
        return TECHNICAL_COMPLEXITY_CRITERION
    if "qualit" in clean or "clean" in clean or "test" in clean or "maintain" in clean:
        return CODE_QUALITY_CRITERION
    if "execut" in clean or "complet" in clean or "demo" in clean or "work" in clean:
        return EXECUTION_COMPLETENESS_CRITERION
    if "impact" in clean or "usab" in clean or "viab" in clean or "market" in clean or "ux" in clean:
        return POTENTIAL_IMPACT_CRITERION

    # Organizer-defined custom criterion: construct anchored framework dynamically
    norm_key = clean.replace(" ", "_").replace("-", "_")[:50]
    return CriterionFramework(
        criterion_key=norm_key,
        display_title=title_or_key.strip(),
        objective=f"Evaluate submission performance strictly according to custom criterion '{title_or_key}'.",
        positive_indicators=[
            f"Demonstrated evidence directly satisfying '{title_or_key}' requirements in repository assets.",
            "Clear technical realization aligned with the custom rubric definition.",
        ],
        negative_indicators=[
            f"Failure to demonstrate evidence satisfying '{title_or_key}'.",
            "Superficial or contradictory implementation regarding this criterion.",
        ],
        irrelevant_factors=[
            "Unrelated stylistic or aesthetic preferences not mentioned in the rubric.",
            "Technology stack size unless explicitly mandated by the custom rubric.",
        ],
        required_evidence=[
            "Direct code, documentation, or test evidence satisfying the custom criterion.",
        ],
        optional_evidence=[
            "Supplementary benchmarks, demo artifacts, or configuration manifests.",
        ],
        scoring_anchors={
            0: f"No evidence of satisfying {title_or_key}.",
            1: f"Extremely weak or trivial attempt at {title_or_key}.",
            2: f"Minimal evidence; largely unsatisfactory for {title_or_key}.",
            3: f"Weak demonstration with major gaps for {title_or_key}.",
            4: f"Partial demonstration, but significant shortcomings in {title_or_key}.",
            5: f"Moderate demonstration meeting basic baseline expectations for {title_or_key}.",
            6: f"Competent demonstration with identifiable minor limitations for {title_or_key}.",
            7: f"Good demonstration with solid evidence for {title_or_key}.",
            8: f"Strong demonstration with comprehensive evidence for {title_or_key}.",
            9: f"Outstanding demonstration exceeding standard expectations for {title_or_key}.",
            10: f"Exemplary demonstration with exceptional mastery of {title_or_key}.",
        },
        deduction_relevance_rules=[
            f"Deductions must directly relate to deficits in {title_or_key}.",
        ],
        overlap_prevention_rules=[
            "Issues already penalized under other criteria must not be double-penalized here without independent justification.",
        ],
        insufficient_evidence_behavior=(
            "If evidence is incomplete, assign a neutral rating (5.0) and clearly flag lack of verification."
        ),
    )
