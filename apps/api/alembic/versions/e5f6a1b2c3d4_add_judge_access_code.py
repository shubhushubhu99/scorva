"""add judge access code

Revision ID: e5f6a1b2c3d4
Revises: d4e5f6a1b2c3
"""

from alembic import op
import sqlalchemy as sa


revision = "e5f6a1b2c3d4"
down_revision = "d4e5f6a1b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = [c["name"] for c in inspector.get_columns("hackathon_judges")]

    if "access_code" not in existing_columns:
        op.add_column("hackathon_judges", sa.Column("access_code", sa.String(length=32), nullable=True))
        op.create_index("ix_hackathon_judges_access_code", "hackathon_judges", ["access_code"], unique=False)

    # Populate access code for any existing rows where access_code is null
    op.execute("""
        UPDATE hackathon_judges
        SET access_code = 'JDG-' || UPPER(SUBSTR(MD5(id::text), 1, 8))
        WHERE access_code IS NULL
    """)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = [c["name"] for c in inspector.get_columns("hackathon_judges")]

    if "access_code" in existing_columns:
        op.drop_index("ix_hackathon_judges_access_code", table_name="hackathon_judges")
        op.drop_column("hackathon_judges", "access_code")
