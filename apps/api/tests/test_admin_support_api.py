import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import text
from apps.api.core.database import AsyncSessionLocal
from apps.api.modules.users.models import PlatformRole


@pytest.mark.asyncio
async def test_admin_support_api_lifecycle(client: AsyncClient, create_user_helper, create_session_helper):
    # 1. Create a super admin user and session
    admin = await create_user_helper("superadmin_support@scorva.io", platform_role=PlatformRole.PLATFORM_OWNER)
    admin_token = await create_session_helper(admin)
    admin_headers = {"Authorization": f"Bearer {admin_token}", "Origin": "http://localhost:3000"}

    # 2. Create a regular participant user (platform_role=None)
    participant = await create_user_helper("participant_asker@scorva.io", platform_role=None)

    # 3. Insert a support ticket from the participant directly in DB
    ticket_id = uuid.uuid4()
    ticket_number = f"TICK-{uuid.uuid4().hex[:8].upper()}"

    async with AsyncSessionLocal() as session:
        insert_ticket = text("""
            INSERT INTO participant_support_tickets (
                id, user_id, hackathon_id, ticket_number, category, team_name,
                team_number, block_number, lab_number, subject, description,
                status, created_at, updated_at
            ) VALUES (
                :id, :uid, NULL, :tnum, 'Technical Issue', 'Code Masters',
                NULL, 'Block 3', 'Lab 101', 'Need extra power strip', 'Desks 4-6 have no power outlets',
                'open', NOW(), NOW()
            )
        """)
        await session.execute(insert_ticket, {
            "id": ticket_id,
            "uid": participant.id,
            "tnum": ticket_number,
        })
        # Add initial acknowledgment
        await session.execute(text("""
            INSERT INTO participant_support_replies (
                id, ticket_id, user_id, author_name, is_staff, message, created_at
            ) VALUES (
                :id, :tid, :uid, 'Support Bot', TRUE, 'Ticket received', NOW()
            )
        """), {
            "id": uuid.uuid4(),
            "tid": ticket_id,
            "uid": participant.id,
        })
        await session.commit()

    # 4. Super Admin lists support tickets
    resp = await client.get("/api/v1/admin/support/tickets", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "stats" in data
    assert data["stats"]["total"] >= 1
    assert data["stats"]["open"] >= 1

    matching = next((item for item in data["items"] if item["id"] == str(ticket_id)), None)
    assert matching is not None
    assert matching["ticket_number"] == ticket_number
    assert matching["participant_email"] == "participant_asker@scorva.io"
    assert matching["team_name"] == "Code Masters"
    assert matching["block_number"] == "Block 3"
    assert matching["lab_number"] == "Lab 101"
    assert matching["replies_count"] == 1

    # 5. Search filter
    search_resp = await client.get(f"/api/v1/admin/support/tickets?search={ticket_number}", headers=admin_headers)
    assert search_resp.status_code == 200
    search_data = search_resp.json()
    assert len(search_data["items"]) == 1
    assert search_data["items"][0]["id"] == str(ticket_id)

    # 6. Detail endpoint
    detail_resp = await client.get(f"/api/v1/admin/support/tickets/{ticket_id}", headers=admin_headers)
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()
    assert detail_data["ticket"]["id"] == str(ticket_id)
    assert len(detail_data["replies"]) == 1
    assert detail_data["replies"][0]["author_name"] == "Support Bot"

    # 7. Admin posts a reply
    reply_resp = await client.post(
        f"/api/v1/admin/support/tickets/{ticket_id}/replies",
        headers=admin_headers,
        json={"message": "Staff has delivered an extension board to Lab 101.", "status": "resolved"},
    )
    assert reply_resp.status_code == 200
    reply_data = reply_resp.json()
    assert reply_data["is_staff"] is True
    assert "Admin" in reply_data["author_name"]

    # Verify status updated to resolved
    detail_resp2 = await client.get(f"/api/v1/admin/support/tickets/{ticket_id}", headers=admin_headers)
    assert detail_resp2.status_code == 200
    assert detail_resp2.json()["ticket"]["status"] == "resolved"
    assert len(detail_resp2.json()["replies"]) == 2

    # 8. Admin updates status directly
    status_resp = await client.patch(
        f"/api/v1/admin/support/tickets/{ticket_id}/status",
        headers=admin_headers,
        json={"status": "closed"},
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "closed"

    # 9. Non-admin is rejected
    participant_token = await create_session_helper(participant)
    part_headers = {"Authorization": f"Bearer {participant_token}", "Origin": "http://localhost:3000"}
    forbidden_resp = await client.get("/api/v1/admin/support/tickets", headers=part_headers)
    assert forbidden_resp.status_code == 403
