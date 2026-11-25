"""Raw payloads and canonical market interval values (append-only).

Revision ID: 0001
Revises:
Create Date: 2026-11-25
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

APPEND_ONLY_TABLES = ("raw_payload", "market_interval_value")


def upgrade() -> None:
    op.create_table(
        "raw_payload",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("source_name", sa.String(64), nullable=False),
        sa.Column("request_url", sa.Text(), nullable=False),
        sa.Column("request_params", postgresql.JSONB(), nullable=False),
        sa.Column("fetched_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=True),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("license_status", sa.String(96), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
    )
    op.create_index("ix_raw_payload_source_fetched", "raw_payload", ["source_name", "fetched_at_utc"])
    op.create_table(
        "market_interval_value",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("delivery_start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivery_end_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivery_day_local", sa.Date(), nullable=False),
        sa.Column("market_zone", sa.String(8), nullable=False),
        sa.Column("product", sa.String(16), nullable=False),
        sa.Column("quantity", sa.String(32), nullable=False),
        sa.Column("value", sa.Numeric(14, 4), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("source_name", sa.String(64), nullable=False),
        sa.Column("source_record_id", sa.String(64), nullable=True),
        sa.Column("source_mtu_label", sa.Integer(), nullable=True),
        sa.Column("published_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ingested_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision_id", sa.Integer(), nullable=False),
        sa.Column("quality_status", sa.String(8), nullable=False),
        sa.Column("quality_notes", sa.Text(), nullable=True),
        sa.Column("is_simulated", sa.Boolean(), nullable=False),
        sa.Column("source_license_status", sa.String(96), nullable=False),
        sa.Column("raw_payload_id", sa.BigInteger(), sa.ForeignKey("raw_payload.id"), nullable=False),
        sa.CheckConstraint("quality_status IN ('OK','WARN','BAD')", name="ck_quality_status"),
        sa.CheckConstraint("delivery_end_utc > delivery_start_utc", name="ck_positive_duration"),
        sa.CheckConstraint("revision_id >= 1", name="ck_revision_positive"),
        sa.UniqueConstraint(
            "source_name", "market_zone", "product", "quantity", "delivery_start_utc", "revision_id",
            name="uq_market_interval_value_key_revision",
        ),
    )
    op.create_index(
        "ix_miv_lookup",
        "market_interval_value",
        ["market_zone", "product", "quantity", "delivery_start_utc"],
    )
    # Append-only guarantee: raw data and stored values can never be edited or deleted row by row.
    op.execute(
        """
        CREATE FUNCTION powerdesk_forbid_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'table % is append-only (% not allowed)', TG_TABLE_NAME, TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table in APPEND_ONLY_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION powerdesk_forbid_mutation();"
        )


def downgrade() -> None:
    for table in APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON {table};")
    op.execute("DROP FUNCTION IF EXISTS powerdesk_forbid_mutation();")
    op.drop_index("ix_miv_lookup", table_name="market_interval_value")
    op.drop_table("market_interval_value")
    op.drop_index("ix_raw_payload_source_fetched", table_name="raw_payload")
    op.drop_table("raw_payload")
