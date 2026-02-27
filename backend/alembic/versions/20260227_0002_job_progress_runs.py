"""Add completed and total run counters to forecast jobs.

Revision ID: 20260227_0002
Revises: 20260227_0001
Create Date: 2026-02-27 23:20:00
"""

from __future__ import annotations

from alembic import op


revision = "20260227_0002"
down_revision = "20260227_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE forecast_jobs ADD COLUMN IF NOT EXISTS completed_runs INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE forecast_jobs ADD COLUMN IF NOT EXISTS total_runs INTEGER NOT NULL DEFAULT 0")
    op.execute(
        """
        UPDATE forecast_jobs
        SET total_runs = COALESCE(NULLIF(params_json->>'mc_runs', '')::int, 0),
            completed_runs = CASE WHEN status = 'succeeded'
                                  THEN COALESCE(NULLIF(params_json->>'mc_runs', '')::int, 0)
                                  ELSE 0
                             END
        """
    )
    op.execute("ALTER TABLE forecast_jobs ALTER COLUMN completed_runs DROP DEFAULT")
    op.execute("ALTER TABLE forecast_jobs ALTER COLUMN total_runs DROP DEFAULT")


def downgrade() -> None:
    op.drop_column("forecast_jobs", "total_runs")
    op.drop_column("forecast_jobs", "completed_runs")
