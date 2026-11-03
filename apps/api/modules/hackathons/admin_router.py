from typing import Optional, List
import uuid
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.core.database import get_db_session
from apps.api.dependencies import require_super_admin
from apps.api.modules.hackathons.models import HackathonStatus
from apps.api.modules.hackathons.schemas import (
    AdminUpdateHackathonStatusRequest,
    HackathonDetailResponse,
    PaginatedHackathonsResponse,
)
from apps.api.modules.hackathons.service import (
    get_admin_hackathon_detail,
    list_admin_hackathons,
    override_admin_hackathon_status,
)
from apps.api.modules.users.models import User

router = APIRouter(prefix="/admin/hackathons", tags=["Admin - Hackathons"])


def _extract_telemetry(request: Request):
    ip_address = getattr(request.state, "client_ip", request.client.host if request.client else "127.0.0.1")
    user_agent = request.headers.get("user-agent", "Unknown")
    correlation_id = getattr(request.state, "correlation_id", None)
    return ip_address, user_agent, correlation_id


@router.get("", response_model=PaginatedHackathonsResponse)
@router.get("/", response_model=PaginatedHackathonsResponse, include_in_schema=False)
async def get_admin_hackathons(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search term for title or slug"),
    status: Optional[HackathonStatus] = Query(None, description="Filter by status"),
    organization_id: Optional[uuid.UUID] = Query(None, description="Filter by owning organization UUID"),
    sort_by: str = Query("created_at", description="Sort field ('created_at', 'start_date', 'title')"),
    sort_order: str = Query("desc", description="Sort direction ('asc', 'desc')"),
    current_admin: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Cross-tenant hackathon directory with search and filtering for platform administrators (§8.1)."""
    items, total, total_pages = await list_admin_hackathons(
        db=db,
        page=page,
        limit=limit,
        search=search,
        hackathon_status=status,
        org_id=organization_id,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return PaginatedHackathonsResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@router.get("/{hackathon_id}", response_model=HackathonDetailResponse)
async def get_admin_hackathon(
    hackathon_id: uuid.UUID,
    current_admin: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Retrieves full hackathon details across tenants for authorized platform administrators (§8.1)."""
    return await get_admin_hackathon_detail(
        db=db,
        hackathon_id=hackathon_id,
    )


@router.post("/{hackathon_id}/status", response_model=HackathonDetailResponse)
async def post_admin_override_hackathon_status(
    hackathon_id: uuid.UUID,
    data: AdminUpdateHackathonStatusRequest,
    request: Request,
    current_admin: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Overrides hackathon status with mandatory justification and audit logging (§8.1)."""
    ip, ua, corr_id = _extract_telemetry(request)
    return await override_admin_hackathon_status(
        db=db,
        hackathon_id=hackathon_id,
        data=data,
        actor=current_admin,
        ip_address=ip,
        user_agent=ua,
        correlation_id=corr_id,
    )


# ============================================================================
# Super Admin Judge Provisioning & Management
# ============================================================================

from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, or_, select
from apps.api.core.exceptions import AppException
from apps.api.core.security import hash_password
from apps.api.modules.audit.models import AuditOutcome
from apps.api.modules.audit.service import record_audit_event
from apps.api.modules.evaluations.models import HackathonJudge
from apps.api.modules.hackathons.models import Hackathon
from apps.api.modules.organizations.models import Organization
from fastapi import status


class AdminJudgeItem(BaseModel):
    id: uuid.UUID
    hackathon_id: uuid.UUID
    hackathon_title: str
    organization_name: Optional[str] = None
    user_id: uuid.UUID
    email: str
    full_name: str
    access_code: str
    created_at: datetime
    temporary_password: Optional[str] = None


class AdminCreateJudgeRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=150)
    email: EmailStr
    password: Optional[str] = Field(None, min_length=6, max_length=100)
    access_code: Optional[str] = Field(None, min_length=4, max_length=32)


@router.get("/judges/all", response_model=List[AdminJudgeItem])
@router.get("/judges", response_model=List[AdminJudgeItem])
async def list_admin_judges(
    hackathon_id: Optional[uuid.UUID] = Query(None, description="Optional filter by hackathon UUID"),
    search: Optional[str] = Query(None, description="Search by name, email, or access code"),
    current_admin: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> List[AdminJudgeItem]:
    """Lists all judges assigned across hackathons for Super Admin."""
    stmt = (
        select(HackathonJudge, User, Hackathon, Organization)
        .join(User, HackathonJudge.user_id == User.id)
        .join(Hackathon, HackathonJudge.hackathon_id == Hackathon.id)
        .outerjoin(Organization, Hackathon.organization_id == Organization.id)
        .where(User.deleted_at.is_(None), Hackathon.deleted_at.is_(None))
    )

    if hackathon_id:
        stmt = stmt.where(HackathonJudge.hackathon_id == hackathon_id)

    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(User.email).like(term),
                func.lower(User.full_name).like(term),
                func.lower(HackathonJudge.access_code).like(term),
                func.lower(Hackathon.title).like(term),
            )
        )

    stmt = stmt.order_by(HackathonJudge.created_at.desc())
    rows = (await db.execute(stmt)).all()

    return [
        AdminJudgeItem(
            id=judge.id,
            hackathon_id=judge.hackathon_id,
            hackathon_title=hack.title,
            organization_name=org.name if org else None,
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            access_code=judge.access_code or f"JDG-{judge.id.hex[:8].upper()}",
            created_at=judge.created_at,
        )
        for judge, user, hack, org in rows
    ]


@router.get("/{hackathon_id}/judges", response_model=List[AdminJudgeItem])
async def list_hackathon_judges_admin(
    hackathon_id: uuid.UUID,
    current_admin: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> List[AdminJudgeItem]:
    """Lists judges assigned to a specific hackathon."""
    return await list_admin_judges(
        hackathon_id=hackathon_id,
        search=None,
        current_admin=current_admin,
        db=db,
    )


@router.post("/{hackathon_id}/judges", response_model=AdminJudgeItem, status_code=status.HTTP_201_CREATED)
async def create_judge_for_hackathon(
    hackathon_id: uuid.UUID,
    payload: AdminCreateJudgeRequest,
    request: Request,
    current_admin: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
) -> AdminJudgeItem:
    """Creates a judge account and generates their login access code for a hackathon."""
    ip, ua, corr_id = _extract_telemetry(request)

    # 1. Verify hackathon exists
    hack_stmt = (
        select(Hackathon, Organization)
        .outerjoin(Organization, Hackathon.organization_id == Organization.id)
        .where(Hackathon.id == hackathon_id, Hackathon.deleted_at.is_(None))
    )
    res = (await db.execute(hack_stmt)).first()
    if not res:
        raise AppException(
            code="HACKATHON_NOT_FOUND",
            message="Hackathon event not found.",
            status_code=status.HTTP_404_NOT_FOUND,
            title="Hackathon Not Found",
        )
    hack, org = res

    # 2. Find or create user
    email_clean = payload.email.lower().strip()
    user_stmt = select(User).where(User.email == email_clean, User.deleted_at.is_(None))
    target_user = (await db.execute(user_stmt)).scalar_one_or_none()

    raw_password = payload.password.strip() if payload.password and payload.password.strip() else "JudgePass123!"

    if not target_user:
        target_user = User(
            id=uuid.uuid4(),
            email=email_clean,
            full_name=payload.full_name.strip(),
            hashed_password=hash_password(raw_password),
            platform_role=None,
            is_active=True,
            is_verified=True,
            mfa_enabled=False,
        )
        db.add(target_user)
        await db.flush()

    # 3. Check existing assignment
    exist_stmt = select(HackathonJudge).where(
        HackathonJudge.hackathon_id == hackathon_id,
        HackathonJudge.user_id == target_user.id,
    )
    if (await db.execute(exist_stmt)).scalar_one_or_none():
        raise AppException(
            code="JUDGE_ALREADY_ASSIGNED",
            message=f"User '{email_clean}' is already assigned as a judge for this hackathon.",
            status_code=status.HTTP_409_CONFLICT,
            title="Judge Already Assigned",
        )

    # 4. Generate access code
    code = (
        payload.access_code.strip().upper()
        if payload.access_code and payload.access_code.strip()
        else f"JDG-{uuid.uuid4().hex[:8].upper()}"
    )

    judge = HackathonJudge(
        id=uuid.uuid4(),
        hackathon_id=hackathon_id,
        user_id=target_user.id,
        assigned_by_user_id=current_admin.id,
        access_code=code,
    )
    db.add(judge)

    # 5. Audit log
    await record_audit_event(
        db=db,
        action="judge_account_created",
        resource_type="hackathon_judge",
        resource_id=str(judge.id),
        outcome=AuditOutcome.SUCCESS,
        actor_user_id=current_admin.id,
        actor_email=current_admin.email,
        actor_role=current_admin.platform_role.value if current_admin.platform_role else "platform_owner",
        organization_id=hack.organization_id,
        reason=f"Created judge account {email_clean} for hackathon '{hack.title}' with access code {code}",
        diff_payload={"email": email_clean, "hackathon_id": str(hackathon_id), "access_code": code},
        ip_address=ip,
        user_agent=ua,
        correlation_id=corr_id,
    )

    await db.commit()
    await db.refresh(judge)

    return AdminJudgeItem(
        id=judge.id,
        hackathon_id=judge.hackathon_id,
        hackathon_title=hack.title,
        organization_name=org.name if org else None,
        user_id=target_user.id,
        email=target_user.email,
        full_name=target_user.full_name,
        access_code=judge.access_code,
        created_at=judge.created_at,
        temporary_password=raw_password,
    )


@router.delete("/{hackathon_id}/judges/{judge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_judge_from_hackathon(
    hackathon_id: uuid.UUID,
    judge_id: uuid.UUID,
    request: Request,
    current_admin: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db_session),
):
    """Removes a judge assignment from a hackathon."""
    ip, ua, corr_id = _extract_telemetry(request)

    stmt = select(HackathonJudge).where(
        HackathonJudge.hackathon_id == hackathon_id,
        or_(HackathonJudge.id == judge_id, HackathonJudge.user_id == judge_id),
    )
    judge = (await db.execute(stmt)).scalar_one_or_none()
    if not judge:
        raise AppException(
            code="JUDGE_NOT_FOUND",
            message="Judge assignment not found for this hackathon.",
            status_code=status.HTTP_404_NOT_FOUND,
            title="Judge Assignment Not Found",
        )

    await db.delete(judge)

    await record_audit_event(
        db=db,
        action="judge_removed",
        resource_type="hackathon_judge",
        resource_id=str(judge.id),
        outcome=AuditOutcome.SUCCESS,
        actor_user_id=current_admin.id,
        actor_email=current_admin.email,
        actor_role=current_admin.platform_role.value if current_admin.platform_role else "platform_owner",
        reason=f"Removed judge assignment {judge.id} from hackathon {hackathon_id}",
        diff_payload={"judge_id": str(judge.id), "user_id": str(judge.user_id)},
        ip_address=ip,
        user_agent=ua,
        correlation_id=corr_id,
    )

    await db.commit()

