"""Add quality issues JSON column to datasets.

Revision ID: 20260228_0003
Revises: 20260227_0002
Create Date: 2026-02-28 12:00:00
"""

from __future__ import annotations

from alembic import op


revision = "20260228_0003"
down_revision = "20260227_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE datasets ADD COLUMN IF NOT EXISTS quality_issues_json JSONB NOT NULL DEFAULT '[]'::jsonb")
    op.execute("ALTER TABLE datasets ALTER COLUMN quality_issues_json DROP DEFAULT")


def downgrade() -> None:
    op.execute("ALTER TABLE datasets DROP COLUMN IF EXISTS quality_issues_json")
