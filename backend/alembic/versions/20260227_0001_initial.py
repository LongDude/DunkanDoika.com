"""Initial schema for datasets, scenarios, and forecast jobs.

Revision ID: 20260227_0001
Revises:
Create Date: 2026-02-27 18:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260227_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("dataset_id", sa.String(length=36), primary_key=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("object_key", sa.String(length=500), nullable=False, unique=True),
        sa.Column("n_rows", sa.Integer(), nullable=False),
        sa.Column("report_date_suggested", sa.Date(), nullable=True),
        sa.Column("status_counts_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_datasets_created_at", "datasets", ["created_at"])

    op.create_table(
        "scenarios",
        sa.Column("scenario_id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), sa.ForeignKey("datasets.dataset_id", ondelete="CASCADE"), nullable=False),
        sa.Column("params_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_scenarios_dataset_created", "scenarios", ["dataset_id", "created_at"])

    op.create_table(
        "forecast_jobs",
        sa.Column("job_id", sa.String(length=36), primary_key=True),
        sa.Column("dataset_id", sa.String(length=36), sa.ForeignKey("datasets.dataset_id", ondelete="CASCADE"), nullable=False),
        sa.Column("scenario_id", sa.String(length=36), sa.ForeignKey("scenarios.scenario_id", ondelete="SET NULL"), nullable=True),
        sa.Column("params_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("progress_pct", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("result_object_key", sa.String(length=500), nullable=True),
        sa.Column("csv_object_key", sa.String(length=500), nullable=True),
        sa.Column("xlsx_object_key", sa.String(length=500), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_forecast_jobs_status_queued", "forecast_jobs", ["status", "queued_at"])


def downgrade() -> None:
    op.drop_index("ix_forecast_jobs_status_queued", table_name="forecast_jobs")
    op.drop_table("forecast_jobs")
    op.drop_index("ix_scenarios_dataset_created", table_name="scenarios")
    op.drop_table("scenarios")
    op.drop_index("ix_datasets_created_at", table_name="datasets")
    op.drop_table("datasets")
