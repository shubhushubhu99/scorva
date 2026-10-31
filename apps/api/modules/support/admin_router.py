import math
from pathlib import Path
from typing import List, Optional
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import FileResponse

from apps.api.config import settings
from apps.api.core.database import get_db_session
from apps.api.core.exceptions import AppException
from apps.api.dependencies import require_platform_role
from apps.api.modules.users.models import User

router = APIRouter(prefix="/admin/support", tags=["Admin Support"])

VALID_STATUSES = {"open", "in_progress", "waiting_response", "resolved", "closed"}


class AdminSupportTicketItem(BaseModel):
    id: uuid.UUID
    ticket_number: str
    category: str
    team_name: str
    team_number: Optional[str] = None
    block_number: Optional[str] = None
    lab_number: Optional[str] = None
    subject: str
    description: str
    status: str
    hackathon_title: Optional[str] = None
    hackathon_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime
    replies_count: int = 0
    attachment_url: Optional[str] = None
    attachment_name: Optional[str] = None
    participant_id: uuid.UUID
    participant_email: Optional[str] = None
    participant_name: Optional[str] = None


class AdminSupportTicketStats(BaseModel):
    total: int = 0
    open: int = 0
    in_progress: int = 0
    waiting_response: int = 0
    resolved: int = 0
    closed: int = 0


class AdminSupportTicketListResponse(BaseModel):
    items: List[AdminSupportTicketItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    limit: int = 20
    total_pages: int = 1
    stats: AdminSupportTicketStats = Field(default_factory=AdminSupportTicketStats)


class AdminSupportReplyItem(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    user_id: uuid.UUID
    author_name: str
    is_staff: bool
    message: str
    created_at: datetime


class AdminSupportTicketDetailResponse(BaseModel):
    ticket: AdminSupportTicketItem
    replies: List[AdminSupportReplyItem] = Field(default_factory=list)


class AdminCreateReplyRequest(BaseModel):
    message: str = Field(..., min_length=2, max_length=5000)
    status: Optional[str] = Field(default=None)


class AdminUpdateStatusRequest(BaseModel):
    status: str = Field(...)


@router.get("/tickets", response_model=AdminSupportTicketListResponse)
async def list_admin_support_tickets(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by ticket status"),
    category: Optional[str] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Search query across ticket number, subject, team name, participant email"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    admin_user: User = Depends(require_platform_role()),
    db: AsyncSession = Depends(get_db_session),
) -> AdminSupportTicketListResponse:
    """
    Lists support requests across all participants with aggregated status statistics.
    Accessible to authorized super administrators and platform operations staff.
    """
    offset = (page - 1) * limit

    # 1. Fetch platform-wide counts / stats
    stats_stmt = text("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE status = 'open') as open_cnt,
            COUNT(*) FILTER (WHERE status = 'in_progress') as in_progress_cnt,
            COUNT(*) FILTER (WHERE status = 'waiting_response') as waiting_response_cnt,
            COUNT(*) FILTER (WHERE status = 'resolved') as resolved_cnt,
            COUNT(*) FILTER (WHERE status = 'closed') as closed_cnt
        FROM participant_support_tickets
    """)
    stats_row = (await db.execute(stats_stmt)).fetchone()
    stats = AdminSupportTicketStats(
        total=stats_row[0] or 0,
        open=stats_row[1] or 0,
        in_progress=stats_row[2] or 0,
        waiting_response=stats_row[3] or 0,
        resolved=stats_row[4] or 0,
        closed=stats_row[5] or 0,
    )

    # 2. Build filtered queries
    where_clauses = ["1=1"]
    params = {"limit": limit, "offset": offset}

    if status_filter and status_filter.lower() != "all":
        where_clauses.append("t.status = :status_filter")
        params["status_filter"] = status_filter.lower()

    if category and category.lower() != "all":
        where_clauses.append("t.category = :category")
        params["category"] = category

    if search and search.strip():
        search_pattern = f"%{search.strip().lower()}%"
        where_clauses.append("""(
            LOWER(t.ticket_number) LIKE :search_pattern OR
            LOWER(t.subject) LIKE :search_pattern OR
            LOWER(t.team_name) LIKE :search_pattern OR
            LOWER(u.email) LIKE :search_pattern OR
            LOWER(COALESCE(u.full_name, '')) LIKE :search_pattern
        )""")
        params["search_pattern"] = search_pattern

    where_sql = " AND ".join(where_clauses)

    count_stmt = text(f"""
        SELECT COUNT(*)
        FROM participant_support_tickets t
        LEFT JOIN users u ON t.user_id = u.id
        WHERE {where_sql}
    """)
    filtered_total = (await db.execute(count_stmt, params)).scalar() or 0

    tickets_stmt = text(f"""
        SELECT 
            t.id,
            t.ticket_number,
            t.category,
            t.team_name,
            t.team_number,
            t.block_number,
            t.lab_number,
            t.subject,
            t.description,
            t.status,
            h.title as hackathon_title,
            t.hackathon_id,
            t.created_at,
            t.updated_at,
            (SELECT COUNT(*) FROM participant_support_replies r WHERE r.ticket_id = t.id) as replies_count,
            t.attachment_url,
            t.attachment_name,
            u.id as participant_id,
            u.email as participant_email,
            u.full_name as participant_name
        FROM participant_support_tickets t
        LEFT JOIN hackathons h ON t.hackathon_id = h.id
        LEFT JOIN users u ON t.user_id = u.id
        WHERE {where_sql}
        ORDER BY t.created_at DESC
        LIMIT :limit OFFSET :offset
    """)
    rows = (await db.execute(tickets_stmt, params)).fetchall()

    items = [
        AdminSupportTicketItem(
            id=row[0],
            ticket_number=row[1],
            category=row[2],
            team_name=row[3],
            team_number=row[4],
            block_number=row[5],
            lab_number=row[6],
            subject=row[7],
            description=row[8],
            status=row[9],
            hackathon_title=row[10],
            hackathon_id=row[11],
            created_at=row[12],
            updated_at=row[13],
            replies_count=row[14],
            attachment_url=row[15],
            attachment_name=row[16],
            participant_id=row[17],
            participant_email=row[18],
            participant_name=row[19],
        )
        for row in rows
    ]

    total_pages = max(1, math.ceil(filtered_total / limit)) if filtered_total > 0 else 1

    return AdminSupportTicketListResponse(
        items=items,
        total=filtered_total,
        page=page,
        limit=limit,
        total_pages=total_pages,
        stats=stats,
    )


@router.get("/tickets/{ticket_id}", response_model=AdminSupportTicketDetailResponse)
async def get_admin_support_ticket_detail(
    ticket_id: uuid.UUID,
    admin_user: User = Depends(require_platform_role()),
    db: AsyncSession = Depends(get_db_session),
) -> AdminSupportTicketDetailResponse:
    """
    Retrieves full details and conversation thread of a participant support request.
    """
    stmt = text("""
        SELECT 
            t.id,
            t.ticket_number,
            t.category,
            t.team_name,
            t.team_number,
            t.block_number,
            t.lab_number,
            t.subject,
            t.description,
            t.status,
            h.title as hackathon_title,
            t.hackathon_id,
            t.created_at,
            t.updated_at,
            (SELECT COUNT(*) FROM participant_support_replies r WHERE r.ticket_id = t.id) as replies_count,
            t.attachment_url,
            t.attachment_name,
            u.id as participant_id,
            u.email as participant_email,
            u.full_name as participant_name
        FROM participant_support_tickets t
        LEFT JOIN hackathons h ON t.hackathon_id = h.id
        LEFT JOIN users u ON t.user_id = u.id
        WHERE t.id = :tid
    """)
    row = (await db.execute(stmt, {"tid": ticket_id})).fetchone()
    if not row:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="TICKET_NOT_FOUND",
            message="Support ticket not found.",
        )

    ticket = AdminSupportTicketItem(
        id=row[0],
        ticket_number=row[1],
        category=row[2],
        team_name=row[3],
        team_number=row[4],
        block_number=row[5],
        lab_number=row[6],
        subject=row[7],
        description=row[8],
        status=row[9],
        hackathon_title=row[10],
        hackathon_id=row[11],
        created_at=row[12],
        updated_at=row[13],
        replies_count=row[14],
        attachment_url=row[15],
        attachment_name=row[16],
        participant_id=row[17],
        participant_email=row[18],
        participant_name=row[19],
    )

    replies_stmt = text("""
        SELECT id, ticket_id, user_id, author_name, is_staff, message, created_at
        FROM participant_support_replies
        WHERE ticket_id = :tid
        ORDER BY created_at ASC
    """)
    r_rows = (await db.execute(replies_stmt, {"tid": ticket_id})).fetchall()
    replies = [
        AdminSupportReplyItem(
            id=r[0],
            ticket_id=r[1],
            user_id=r[2],
            author_name=r[3],
            is_staff=r[4],
            message=r[5],
            created_at=r[6],
        )
        for r in r_rows
    ]

    return AdminSupportTicketDetailResponse(ticket=ticket, replies=replies)


@router.post("/tickets/{ticket_id}/replies", response_model=AdminSupportReplyItem)
async def submit_admin_support_reply(
    ticket_id: uuid.UUID,
    payload: AdminCreateReplyRequest,
    admin_user: User = Depends(require_platform_role()),
    db: AsyncSession = Depends(get_db_session),
) -> AdminSupportReplyItem:
    """
    Submits an official administrator/staff reply to a participant's support ticket.
    """
    check_stmt = text("""
        SELECT id, status FROM participant_support_tickets WHERE id = :tid
    """)
    ticket = (await db.execute(check_stmt, {"tid": ticket_id})).fetchone()
    if not ticket:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="TICKET_NOT_FOUND",
            message="Support ticket not found.",
        )

    reply_id = uuid.uuid4()
    author_name = f"{admin_user.full_name or admin_user.email.split('@')[0]} (Admin)"

    reply_stmt = text("""
        INSERT INTO participant_support_replies (
            id, ticket_id, user_id, author_name, is_staff, message, created_at
        ) VALUES (
            :id, :tid, :uid, :author, TRUE, :msg, NOW()
        ) RETURNING id, ticket_id, user_id, author_name, is_staff, message, created_at
    """)
    res = (await db.execute(reply_stmt, {
        "id": reply_id,
        "tid": ticket_id,
        "uid": admin_user.id,
        "author": author_name,
        "msg": payload.message.strip(),
    })).fetchone()

    # Determine status transition
    new_status = payload.status if payload.status and payload.status in VALID_STATUSES else "waiting_response"

    await db.execute(text("""
        UPDATE participant_support_tickets
        SET updated_at = NOW(), status = :st
        WHERE id = :tid
    """), {"tid": ticket_id, "st": new_status})

    await db.commit()

    return AdminSupportReplyItem(
        id=res[0],
        ticket_id=res[1],
        user_id=res[2],
        author_name=res[3],
        is_staff=res[4],
        message=res[5],
        created_at=res[6],
    )


@router.patch("/tickets/{ticket_id}/status")
async def update_admin_support_ticket_status(
    ticket_id: uuid.UUID,
    payload: AdminUpdateStatusRequest,
    admin_user: User = Depends(require_platform_role()),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """
    Updates the lifecycle status of a support ticket ('open', 'in_progress', 'waiting_response', 'resolved', 'closed').
    """
    if payload.status not in VALID_STATUSES:
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_STATUS",
            message=f"Invalid status '{payload.status}'. Permitted: {', '.join(sorted(VALID_STATUSES))}.",
        )

    stmt = text("""
        UPDATE participant_support_tickets
        SET status = :st, updated_at = NOW()
        WHERE id = :tid
        RETURNING id, status
    """)
    row = (await db.execute(stmt, {"tid": ticket_id, "st": payload.status})).fetchone()
    if not row:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="TICKET_NOT_FOUND",
            message="Support ticket not found.",
        )

    await db.commit()
    return {"id": str(row[0]), "status": row[1]}


@router.get("/tickets/{ticket_id}/attachment")
async def download_admin_support_ticket_attachment(
    ticket_id: uuid.UUID,
    admin_user: User = Depends(require_platform_role()),
    db: AsyncSession = Depends(get_db_session),
) -> FileResponse:
    """
    Downloads or previews the diagnostic attachment associated with a participant support ticket.
    """
    stmt = text("""
        SELECT ticket_number, attachment_name, attachment_content_type
        FROM participant_support_tickets
        WHERE id = :tid AND attachment_url IS NOT NULL
    """)
    row = (await db.execute(stmt, {"tid": ticket_id})).fetchone()
    if not row:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="ATTACHMENT_NOT_FOUND",
            message="Attachment not found.",
        )

    attachment_dir = Path(settings.SUPPORT_ATTACHMENT_DIR)
    if not attachment_dir.is_absolute():
        attachment_dir = Path(__file__).resolve().parents[4] / attachment_dir
    attachment_path = attachment_dir / str(ticket_id)
    if not attachment_path.is_file():
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            code="ATTACHMENT_FILE_NOT_FOUND",
            message="The support request attachment is no longer available on disk.",
        )

    return FileResponse(
        path=attachment_path,
        media_type=row[2] or "application/octet-stream",
        filename=row[1] or "attachment",
    )
