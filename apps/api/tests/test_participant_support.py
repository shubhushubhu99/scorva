import uuid
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from apps.api.core.database import AsyncSessionLocal


@pytest.mark.asyncio
async def test_participant_support_tickets_and_replies_schema_and_constraints(create_user_helper):
    user = await create_user_helper("participant_support_tester@scorva.io")

    async with AsyncSessionLocal() as session:
        # 1. Insert a Venue / Seating Query ticket (requires team_number, block & lab must be NULL)
        ticket_id = uuid.uuid4()
        ticket_number = f"TICK-{uuid.uuid4().hex[:8].upper()}"

        insert_venue_stmt = text("""
            INSERT INTO participant_support_tickets (
                id, user_id, hackathon_id, ticket_number, category, team_name,
                team_number, block_number, lab_number, subject, description,
                status, created_at, updated_at
            ) VALUES (
                :id, :uid, NULL, :tnum, 'Venue / Seating Query', 'Alpha Squad',
                'TEAM-101', NULL, NULL, 'Seating Query', 'Need desk clarification',
                'open', NOW(), NOW()
            ) RETURNING id, ticket_number, category, team_number
        """)
        res = (await session.execute(insert_venue_stmt, {
            "id": ticket_id,
            "uid": user.id,
            "tnum": ticket_number,
        })).fetchone()
        assert res[0] == ticket_id
        assert res[1] == ticket_number
        assert res[2] == "Venue / Seating Query"
        assert res[3] == "TEAM-101"

        # 2. Insert a Technical Issue ticket (requires block_number & lab_number, team_number must be NULL)
        tech_ticket_id = uuid.uuid4()
        tech_ticket_number = f"TICK-{uuid.uuid4().hex[:8].upper()}"

        insert_tech_stmt = text("""
            INSERT INTO participant_support_tickets (
                id, user_id, hackathon_id, ticket_number, category, team_name,
                team_number, block_number, lab_number, subject, description,
                attachment_url, attachment_name, attachment_content_type,
                status, created_at, updated_at
            ) VALUES (
                :id, :uid, NULL, :tnum, 'Technical Issue', 'Beta Squad',
                NULL, 'Block 1', 'Lab 204', 'Network down', 'Ethernet port has no link',
                'https://uploads.scorva.io/logs.txt', 'logs.txt', 'text/plain',
                'open', NOW(), NOW()
            ) RETURNING id, block_number, lab_number, attachment_name
        """)
        res2 = (await session.execute(insert_tech_stmt, {
            "id": tech_ticket_id,
            "uid": user.id,
            "tnum": tech_ticket_number,
        })).fetchone()
        assert res2[0] == tech_ticket_id
        assert res2[1] == "Block 1"
        assert res2[2] == "Lab 204"
        assert res2[3] == "logs.txt"

        # 3. Add replies to the ticket
        reply_id = uuid.uuid4()
        reply_stmt = text("""
            INSERT INTO participant_support_replies (
                id, ticket_id, user_id, author_name, is_staff, message, created_at
            ) VALUES (
                :id, :tid, :uid, 'Support Bot', TRUE, 'Investigating network issue', NOW()
            ) RETURNING id
        """)
        reply_res = (await session.execute(reply_stmt, {
            "id": reply_id,
            "tid": tech_ticket_id,
            "uid": user.id,
        })).fetchone()
        assert reply_res[0] == reply_id

        # 4. Query tickets with replies count (exact query pattern from participant_router.py)
        query_stmt = text("""
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
                t.created_at,
                t.updated_at,
                (SELECT COUNT(*) FROM participant_support_replies r WHERE r.ticket_id = t.id) as replies_count,
                t.attachment_url,
                t.attachment_name
            FROM participant_support_tickets t
            WHERE t.user_id = :uid
            ORDER BY t.created_at DESC
        """)
        rows = (await session.execute(query_stmt, {"uid": user.id})).fetchall()
        assert len(rows) == 2
        
        tech_row = next(r for r in rows if r[0] == tech_ticket_id)
        assert tech_row[12] == 1  # replies_count == 1
        assert tech_row[14] == "logs.txt"

        # 5. Verify conditional constraint rejects invalid Venue Query (e.g., has block_number)
        with pytest.raises(IntegrityError):
            await session.execute(text("""
                INSERT INTO participant_support_tickets (
                    id, user_id, hackathon_id, ticket_number, category, team_name,
                    team_number, block_number, lab_number, subject, description,
                    status, created_at, updated_at
                ) VALUES (
                    :id, :uid, NULL, :tnum, 'Venue / Seating Query', 'Alpha Squad',
                    'TEAM-101', 'Block 1', NULL, 'Invalid', 'Should fail constraint',
                    'open', NOW(), NOW()
                )
            """), {
                "id": uuid.uuid4(),
                "uid": user.id,
                "tnum": f"TICK-{uuid.uuid4().hex[:8].upper()}",
            })

        await session.rollback()
