"""
Utility to purge dummy test records and restore the platform database to a pristine, clean state.
Preserves real tenant organizations, real hackathons, real participant registrations, and core admin accounts.
"""
import asyncio
from typing import List
from sqlalchemy import select, delete, text
import redis.asyncio as aioredis
from apps.api.config import settings
from apps.api.core.database import AsyncSessionLocal
from apps.api.modules.organizations.models import Organization
from apps.api.modules.hackathons.models import Hackathon
from apps.api.modules.users.models import User, PlatformRole
from apps.api.core.security import hash_password, encrypt_totp_secret


CORE_ACCOUNTS = [
    {
        "email": "admin@scorva.io",
        "full_name": "Platform Administrator",
        "role": PlatformRole.PLATFORM_OWNER,
        "mfa_enabled": False,
        "mfa_secret": None,
    },
    {
        "email": "owner@scorva.io",
        "full_name": "Platform Owner (Enrolled)",
        "role": PlatformRole.PLATFORM_OWNER,
        "mfa_enabled": True,
        "mfa_secret": "JBSWY3DPEHPK3PXP",
    },
    {
        "email": "security@scorva.io",
        "full_name": "Security Auditor",
        "role": PlatformRole.SECURITY_ADMIN,
        "mfa_enabled": True,
        "mfa_secret": "HXDMVJECJJWSRB3HWIZR4IFUGFTMXBOZ",
    },
]


async def run_cleanup():
    async with AsyncSessionLocal() as db:
        # 1. Identify real organizations and hackathons to preserve
        real_org_rows = (await db.execute(text("SELECT id FROM organizations WHERE slug = 'd4-community'"))).fetchall()
        keep_org_ids = [str(r[0]) for r in real_org_rows]

        real_hack_rows = (await db.execute(text("SELECT id FROM hackathons WHERE slug = 'graviton'"))).fetchall()
        keep_hack_ids = [str(r[0]) for r in real_hack_rows]

        # Explicit user emails to keep
        keep_emails = [
            "admin@scorva.io",
            "owner@scorva.io",
            "security@scorva.io",
            "rahul@gmail.com",
            "mayank@scorva.ai",
            "organizer@scorva.io",
            "judge@scorva.io",
        ]

        real_user_rows = (await db.execute(
            select(User.id).where(User.email.in_(keep_emails))
        )).scalars().all()
        keep_user_ids = [str(uid) for uid in real_user_rows]

        print(f"[i] Keeping {len(keep_org_ids)} org(s), {len(keep_hack_ids)} hackathon(s), {len(keep_user_ids)} user(s).")

        hids_in = ", ".join(f"'{h}'" for h in keep_hack_ids) or "'00000000-0000-0000-0000-000000000000'"
        oids_in = ", ".join(f"'{o}'" for o in keep_org_ids) or "'00000000-0000-0000-0000-000000000000'"
        uids_in = ", ".join(f"'{u}'" for u in keep_user_ids) or "'00000000-0000-0000-0000-000000000000'"

        # 2. Delete test evaluation jobs, scores, results, references
        await db.execute(text(f"""
            UPDATE evaluation_jobs SET current_result_id = NULL 
            WHERE hackathon_id NOT IN ({hids_in}) OR hackathon_id IS NULL
        """))
        await db.execute(text(f"""
            DELETE FROM evidence_references WHERE criterion_score_id IN (
                SELECT id FROM evaluation_criterion_scores WHERE evaluation_result_id IN (
                    SELECT id FROM evaluation_results WHERE hackathon_id NOT IN ({hids_in}) OR hackathon_id IS NULL
                )
            )
        """))
        await db.execute(text(f"""
            DELETE FROM evaluation_criterion_scores WHERE evaluation_result_id IN (
                SELECT id FROM evaluation_results WHERE hackathon_id NOT IN ({hids_in}) OR hackathon_id IS NULL
            )
        """))
        await db.execute(text(f"""
            DELETE FROM evaluation_results WHERE hackathon_id NOT IN ({hids_in}) OR hackathon_id IS NULL
        """))
        await db.execute(text(f"""
            DELETE FROM evaluation_jobs WHERE hackathon_id NOT IN ({hids_in}) OR hackathon_id IS NULL
        """))
        await db.execute(text("DELETE FROM evaluation_job_outbox"))

        # 3. Delete dummy judge reviews and criterion scores
        await db.execute(text(f"""
            DELETE FROM judge_criterion_scores WHERE judge_review_id IN (
                SELECT id FROM judge_reviews WHERE hackathon_id NOT IN ({hids_in}) OR hackathon_id IS NULL
            )
        """))
        await db.execute(text(f"""
            DELETE FROM judge_reviews WHERE hackathon_id NOT IN ({hids_in}) OR hackathon_id IS NULL
        """))

        # 4. Delete dummy submissions and snapshots
        await db.execute(text(f"""
            DELETE FROM submission_snapshots WHERE submission_id IN (
                SELECT id FROM submissions WHERE hackathon_id NOT IN ({hids_in}) OR hackathon_id IS NULL
            )
        """))
        await db.execute(text(f"""
            DELETE FROM submissions WHERE hackathon_id NOT IN ({hids_in}) OR hackathon_id IS NULL
        """))

        # 5. Delete dummy support tickets and replies
        await db.execute(text(f"""
            DELETE FROM participant_support_replies WHERE ticket_id IN (
                SELECT id FROM participant_support_tickets WHERE user_id NOT IN ({uids_in})
            )
        """))
        await db.execute(text(f"""
            DELETE FROM participant_support_tickets WHERE user_id NOT IN ({uids_in})
        """))

        # Delete dummy project registrations
        await db.execute(text(f"""
            DELETE FROM participant_project_registrations WHERE user_id NOT IN ({uids_in})
        """))

        # Delete dummy tokens, notifications, tasks
        await db.execute(text(f"DELETE FROM participant_pat_tokens WHERE user_id NOT IN ({uids_in})"))
        await db.execute(text(f"DELETE FROM participant_notification_states WHERE user_id NOT IN ({uids_in})"))
        await db.execute(text(f"DELETE FROM participant_task_records WHERE user_id NOT IN ({uids_in})"))

        # 6. Delete dummy teams and members
        await db.execute(text(f"""
            DELETE FROM team_members WHERE team_id IN (
                SELECT id FROM teams WHERE organization_id NOT IN ({oids_in}) OR hackathon_id NOT IN ({hids_in})
            ) OR user_id NOT IN ({uids_in})
        """))
        await db.execute(text(f"""
            DELETE FROM teams WHERE organization_id NOT IN ({oids_in}) OR hackathon_id NOT IN ({hids_in})
        """))

        # 7. Delete dummy rubrics & criteria
        await db.execute(text("ALTER TABLE rubric_criteria DISABLE TRIGGER trg_rubric_criteria_immutable"))
        await db.execute(text("ALTER TABLE rubric_versions DISABLE TRIGGER trg_rubric_versions_protect"))
        try:
            await db.execute(text(f"""
                DELETE FROM rubric_criteria WHERE rubric_version_id IN (
                    SELECT rv.id FROM rubric_versions rv JOIN rubrics r ON r.id = rv.rubric_id WHERE r.hackathon_id NOT IN ({hids_in})
                )
            """))
            await db.execute(text(f"""
                DELETE FROM rubric_versions WHERE rubric_id IN (
                    SELECT id FROM rubrics WHERE hackathon_id NOT IN ({hids_in})
                )
            """))
            await db.execute(text(f"""
                DELETE FROM rubrics WHERE hackathon_id NOT IN ({hids_in})
            """))
        finally:
            await db.execute(text("ALTER TABLE rubric_criteria ENABLE TRIGGER trg_rubric_criteria_immutable"))
            await db.execute(text("ALTER TABLE rubric_versions ENABLE TRIGGER trg_rubric_versions_protect"))
        await db.execute(text(f"DELETE FROM hackathon_judges WHERE hackathon_id NOT IN ({hids_in})"))
        await db.execute(text(f"DELETE FROM hackathons WHERE id NOT IN ({hids_in})"))

        # 8. Delete dummy organization memberships & integrations & orgs
        await db.execute(text(f"""
            DELETE FROM organization_memberships WHERE organization_id NOT IN ({oids_in}) OR user_id NOT IN ({uids_in})
        """))
        await db.execute(text(f"DELETE FROM organization_integrations WHERE organization_id NOT IN ({oids_in})"))
        await db.execute(text(f"DELETE FROM organizations WHERE id NOT IN ({oids_in})"))

        # 9. Delete dummy user sessions, roles, and dummy users
        await db.execute(text(f"DELETE FROM user_sessions WHERE user_id NOT IN ({uids_in})"))
        await db.execute(text(f"DELETE FROM user_role_assignments WHERE user_id NOT IN ({uids_in})"))
        await db.execute(text(f"DELETE FROM users WHERE id NOT IN ({uids_in})"))

        # 10. Clean test audit events & queues
        await db.execute(text("ALTER TABLE audit_events DISABLE TRIGGER trg_audit_events_immutable"))
        try:
            await db.execute(text("""
                DELETE FROM audit_events 
                WHERE actor_email NOT IN ('admin@scorva.io', 'owner@scorva.io', 'security@scorva.io', 'rahul@gmail.com', 'mayank@scorva.ai', 'organizer@scorva.io', 'judge@scorva.io')
                OR actor_email IS NULL
            """))
        finally:
            await db.execute(text("ALTER TABLE audit_events ENABLE TRIGGER trg_audit_events_immutable"))
        await db.execute(text("DELETE FROM authz_invalidation_outbox"))
        await db.execute(text("DELETE FROM github_events"))

        # Ensure the 3 standard admin accounts are present and healthy
        for acc in CORE_ACCOUNTS:
            stmt = select(User).where(User.email == acc["email"])
            existing = (await db.execute(stmt)).scalar_one_or_none()
            hashed = hash_password("Password123!")
            enc_sec = encrypt_totp_secret(acc["mfa_secret"], settings.ENCRYPTION_MASTER_KEY) if acc["mfa_secret"] else None

            if existing:
                existing.full_name = acc["full_name"]
                existing.platform_role = acc["role"]
                existing.hashed_password = hashed
                existing.mfa_enabled = acc["mfa_enabled"]
                existing.encrypted_mfa_secret = enc_sec
                existing.is_active = True
                existing.is_verified = True
            else:
                new_u = User(
                    email=acc["email"],
                    full_name=acc["full_name"],
                    hashed_password=hashed,
                    platform_role=acc["role"],
                    mfa_enabled=acc["mfa_enabled"],
                    encrypted_mfa_secret=enc_sec,
                    is_active=True,
                    is_verified=True,
                )
                db.add(new_u)

        await db.commit()
        print("[+] Database cleaned successfully: all dummy data removed.")

    # 11. Flush Redis
    try:
        r = aioredis.from_url(settings.REDIS_URL)
        await r.flushdb()
        await r.close()
        print("[+] Redis cache flushed.")
    except Exception as e:
        print(f"[!] Redis flush warning: {e}")


if __name__ == "__main__":
    asyncio.run(run_cleanup())
