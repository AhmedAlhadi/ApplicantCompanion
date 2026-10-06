"""Entitlements, subscriptions, and the usage ledger.

Revision ID: 0011_entitlements_usage
Revises: 0010_document_ingest_status
Create Date: 2026-09-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011_entitlements_usage"
down_revision: Union[str, None] = "0010_document_ingest_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json_default(value: str) -> sa.TextClause:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return sa.text(f"'{value}'::json")
    return sa.text(f"'{value}'")


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "plans" not in tables:
        op.create_table(
            "plans",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("display_name", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="published"),
            sa.Column("current_version_id", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("code", name="uq_plan_code"),
        )
        op.create_index("ix_plans_code", "plans", ["code"])
        op.create_index("ix_plans_status", "plans", ["status"])

    if "plan_versions" not in tables:
        op.create_table(
            "plan_versions",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("plan_id", sa.String(length=36), sa.ForeignKey("plans.id"), nullable=False),
            sa.Column("version_number", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("limits", sa.JSON(), nullable=False, server_default=_json_default("{}")),
            sa.Column("rollover_caps", sa.JSON(), nullable=False, server_default=_json_default("{}")),
            sa.Column("features", sa.JSON(), nullable=False, server_default=_json_default("{}")),
            sa.Column("template_keys", sa.JSON(), nullable=False, server_default=_json_default("[]")),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("plan_id", "version_number", name="uq_plan_version_number"),
        )
        op.create_index("ix_plan_versions_plan_id", "plan_versions", ["plan_id"])

    if "subscriptions" not in tables:
        op.create_table(
            "subscriptions",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("plan_id", sa.String(length=36), sa.ForeignKey("plans.id"), nullable=False),
            sa.Column("plan_version_id", sa.String(length=36), sa.ForeignKey("plan_versions.id"), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
            sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
            sa.Column("grace_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("assigned_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])
        op.create_index("ix_subscriptions_status", "subscriptions", ["status"])

    if "credit_grants" not in tables:
        op.create_table(
            "credit_grants",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("meter", sa.String(length=64), nullable=False),
            sa.Column("original", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("remaining", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("source", sa.String(length=32), nullable=False, server_default="admin_adjustment"),
            sa.Column("note", sa.Text(), nullable=False, server_default=""),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("granted_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_credit_grants_user_id", "credit_grants", ["user_id"])
        op.create_index("ix_credit_grants_meter", "credit_grants", ["meter"])

    if "entitlement_overrides" not in tables:
        op.create_table(
            "entitlement_overrides",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("feature_key", sa.String(length=64), nullable=True),
            sa.Column("meter", sa.String(length=64), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=True),
            sa.Column("limit_value", sa.BigInteger(), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_by", sa.String(length=36), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_entitlement_overrides_user_id", "entitlement_overrides", ["user_id"])

    if "usage_buckets" not in tables:
        op.create_table(
            "usage_buckets",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("meter", sa.String(length=64), nullable=False),
            sa.Column("period_key", sa.String(length=7), nullable=False),
            sa.Column("included", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("rollover", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("consumed", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("reserved", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("user_id", "meter", "period_key", name="uq_usage_bucket"),
        )
        op.create_index("ix_usage_buckets_user_id", "usage_buckets", ["user_id"])
        op.create_index("ix_usage_buckets_period_key", "usage_buckets", ["period_key"])

    if "usage_reservations" not in tables:
        op.create_table(
            "usage_reservations",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("meter", sa.String(length=64), nullable=False),
            sa.Column("quantity", sa.BigInteger(), nullable=False, server_default="1"),
            sa.Column("state", sa.String(length=16), nullable=False, server_default="reserved"),
            sa.Column("period_key", sa.String(length=7), nullable=False, server_default=""),
            sa.Column("idempotency_key", sa.String(length=255), nullable=False),
            sa.Column("reference_type", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("reference_id", sa.String(length=36), nullable=False, server_default=""),
            sa.Column("allocations", sa.JSON(), nullable=False, server_default=_json_default("{}")),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("idempotency_key", name="uq_usage_reservation_key"),
        )
        op.create_index("ix_usage_reservations_user_id", "usage_reservations", ["user_id"])
        op.create_index("ix_usage_reservations_state", "usage_reservations", ["state"])

    if "usage_events" not in tables:
        op.create_table(
            "usage_events",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("meter", sa.String(length=64), nullable=False),
            sa.Column("quantity", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("state", sa.String(length=16), nullable=False),
            sa.Column("period_key", sa.String(length=7), nullable=False, server_default=""),
            sa.Column("reservation_id", sa.String(length=36), sa.ForeignKey("usage_reservations.id"), nullable=True),
            sa.Column("idempotency_key", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("reference_type", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("reference_id", sa.String(length=36), nullable=False, server_default=""),
            sa.Column("detail", sa.JSON(), nullable=False, server_default=_json_default("{}")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
        op.create_index("ix_usage_events_user_id", "usage_events", ["user_id"])
        op.create_index("ix_usage_events_created_at", "usage_events", ["created_at"])

    if "application_pack_unlocks" not in tables:
        op.create_table(
            "application_pack_unlocks",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("job_id", sa.String(length=36), sa.ForeignKey("jobs.id"), nullable=False),
            sa.Column("content_hash", sa.String(length=64), nullable=False),
            sa.Column("reservation_id", sa.String(length=36), sa.ForeignKey("usage_reservations.id"), nullable=True),
            sa.Column("state", sa.String(length=16), nullable=False, server_default="reserved"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("user_id", "job_id", "content_hash", name="uq_pack_unlock"),
        )
        op.create_index("ix_application_pack_unlocks_user_id", "application_pack_unlocks", ["user_id"])
        op.create_index("ix_application_pack_unlocks_job_id", "application_pack_unlocks", ["job_id"])

    workflow_cols = {column["name"] for column in insp.get_columns("workflow_runs")} if "workflow_runs" in tables else set()
    if workflow_cols and "usage_reservation_id" not in workflow_cols:
        op.add_column("workflow_runs", sa.Column("usage_reservation_id", sa.String(length=36), nullable=True))
    execution_cols = {column["name"] for column in insp.get_columns("agent_executions")} if "agent_executions" in tables else set()
    if execution_cols and "user_id" not in execution_cols:
        op.add_column("agent_executions", sa.Column("user_id", sa.String(length=36), nullable=True))
    if execution_cols and "usage_reservation_id" not in execution_cols:
        op.add_column("agent_executions", sa.Column("usage_reservation_id", sa.String(length=36), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_executions", "usage_reservation_id")
    op.drop_column("agent_executions", "user_id")
    op.drop_column("workflow_runs", "usage_reservation_id")
    op.drop_table("application_pack_unlocks")
    op.drop_table("usage_events")
    op.drop_table("usage_reservations")
    op.drop_table("usage_buckets")
    op.drop_table("entitlement_overrides")
    op.drop_table("credit_grants")
    op.drop_table("subscriptions")
    op.drop_table("plan_versions")
    op.drop_table("plans")
