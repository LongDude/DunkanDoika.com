"""Add owner-scoped history and user presets.

Revision ID: 20260301_0004
Revises: 20260228_0003
Create Date: 2026-03-01 00:00:00
"""

from __future__ import annotations

from alembic import op


revision = "20260301_0004"
down_revision = "20260228_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE forecast_jobs ADD COLUMN IF NOT EXISTS owner_user_id VARCHAR(255)")
    op.execute("ALTER TABLE forecast_jobs ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_forecast_jobs_owner_queued ON forecast_jobs (owner_user_id, queued_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_forecast_jobs_owner_deleted ON forecast_jobs (owner_user_id, deleted_at)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_presets (
            preset_id VARCHAR(36) PRIMARY KEY,
            owner_user_id VARCHAR(255) NOT NULL,
            name VARCHAR(120) NOT NULL,
            params_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            deleted_at TIMESTAMPTZ NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_presets_owner_updated ON user_presets (owner_user_id, updated_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_user_presets_owner_updated")
    op.execute("DROP TABLE IF EXISTS user_presets")
    op.execute("DROP INDEX IF EXISTS ix_forecast_jobs_owner_deleted")
    op.execute("DROP INDEX IF EXISTS ix_forecast_jobs_owner_queued")
    op.execute("ALTER TABLE forecast_jobs DROP COLUMN IF EXISTS deleted_at")
    op.execute("ALTER TABLE forecast_jobs DROP COLUMN IF EXISTS owner_user_id")
