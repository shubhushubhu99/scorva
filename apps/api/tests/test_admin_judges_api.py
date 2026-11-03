import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from apps.api.modules.users.models import PlatformRole, User
from apps.api.modules.hackathons.models import Hackathon, HackathonStatus
from apps.api.modules.organizations.models import Organization, OrganizationStatus


@pytest.mark.asyncio
async def test_admin_create_judge_and_judge_code_login(
    client: AsyncClient,
    create_user_helper,
    create_session_helper,
    db_session,
):
    # 1. Create a super admin user and session
    admin = await create_user_helper("superadmin_judge_mgr@scorva.io", platform_role=PlatformRole.PLATFORM_OWNER)
    admin_token = await create_session_helper(admin)
    admin_headers = {"Authorization": f"Bearer {admin_token}", "Origin": "http://localhost:3000"}

    # 2. Create an organization and hackathon for the test
    org = Organization(
        id=uuid.uuid4(),
        name="Global AI Org",
        slug=f"ai-org-{uuid.uuid4().hex[:6]}",
        status=OrganizationStatus.ACTIVE,
        owner_id=admin.id,
    )
    db_session.add(org)

    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    hackathon = Hackathon(
        id=uuid.uuid4(),
        organization_id=org.id,
        title="AI World Cup 2026",
        slug=f"ai-world-cup-{uuid.uuid4().hex[:6]}",
        status=HackathonStatus.PUBLISHED,
        start_date=now - timedelta(days=1),
        end_date=now + timedelta(days=7),
        submission_deadline=now + timedelta(days=5),
        created_by_user_id=admin.id,
    )
    db_session.add(hackathon)
    await db_session.commit()

    # 3. Super Admin creates a judge account for the hackathon
    judge_email = f"judge_{uuid.uuid4().hex[:6]}@scorva.io"
    create_resp = await client.post(
        f"/api/v1/admin/hackathons/{hackathon.id}/judges",
        headers=admin_headers,
        json={
            "full_name": "Dr. Sarah Connor",
            "email": judge_email,
            "password": "JudgeSecret123!",
        },
    )
    assert create_resp.status_code == 201
    judge_data = create_resp.json()
    assert judge_data["email"] == judge_email
    assert judge_data["full_name"] == "Dr. Sarah Connor"
    assert judge_data["hackathon_id"] == str(hackathon.id)
    assert judge_data["hackathon_title"] == "AI World Cup 2026"
    assert judge_data["access_code"].startswith("JDG-")
    access_code = judge_data["access_code"]
    judge_user_id = judge_data["user_id"]

    # 4. Super Admin lists judges for that hackathon
    list_resp = await client.get(
        f"/api/v1/admin/hackathons/{hackathon.id}/judges",
        headers=admin_headers,
    )
    assert list_resp.status_code == 200
    judges_list = list_resp.json()
    assert len(judges_list) >= 1
    matching = next((j for j in judges_list if j["email"] == judge_email), None)
    assert matching is not None
    assert matching["access_code"] == access_code

    # 5. Judge tries to log in with an INVALID judge code -> fails with 401
    bad_code_resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": judge_email,
            "password": "JudgeSecret123!",
            "judge_code": "JDG-INVALID999",
        },
    )
    assert bad_code_resp.status_code == 401
    assert bad_code_resp.json()["code"] == "INVALID_JUDGE_CODE"

    # 6. Another user tries to log in using this judge's code -> fails with 401
    other_user = await create_user_helper(f"other_{uuid.uuid4().hex[:6]}@scorva.io", platform_role=None)
    mismatch_resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": other_user.email,
            "password": "CorrectPassword123!",
            "judge_code": access_code,
        },
    )
    assert mismatch_resp.status_code == 401
    assert mismatch_resp.json()["code"] == "JUDGE_CODE_MISMATCH"

    # 7. Judge logs in with valid email, password, and judge access code -> SUCCESS!
    valid_login_resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": judge_email,
            "password": "JudgeSecret123!",
            "judge_code": access_code,
        },
    )
    assert valid_login_resp.status_code == 200
    auth_data = valid_login_resp.json()
    assert auth_data["user"]["email"] == judge_email
    assert auth_data["default_destination"] == "/judge"

    # 8. Super admin deletes judge assignment (clear judge session cookie so admin headers are used)
    client.cookies.clear()
    del_resp = await client.delete(
        f"/api/v1/admin/hackathons/{hackathon.id}/judges/{judge_data['id']}",
        headers=admin_headers,
    )
    assert del_resp.status_code == 204
