"""Create durable webhook events and delivery tables."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = "0001_initial_outbox"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())

    # Preserve the original endpoint table shape on a fresh install and upgrade
    # existing endpoint-only installations in place below.
    if "webhook_endpoints" not in tables:
        op.create_table(
            "webhook_endpoints",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("url", sa.String(length=2048), nullable=False),
            sa.Column("secret", sa.String(length=255), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_webhook_endpoints_id", "webhook_endpoints", ["id"])

    columns = {column["name"] for column in inspect(bind).get_columns("webhook_endpoints")}
    if "vendor_id" not in columns:
        op.add_column("webhook_endpoints", sa.Column("vendor_id", sa.String(128), nullable=True))
        bind.execute(text("UPDATE webhook_endpoints SET vendor_id = 'default' WHERE vendor_id IS NULL"))
        with op.batch_alter_table("webhook_endpoints") as batch:
            batch.alter_column("vendor_id", existing_type=sa.String(128), nullable=False)
    if "event_types" not in columns:
        op.add_column("webhook_endpoints", sa.Column("event_types", sa.JSON(), nullable=True))
        bind.execute(text("UPDATE webhook_endpoints SET event_types = '[\"*\"]' WHERE event_types IS NULL"))
        with op.batch_alter_table("webhook_endpoints") as batch:
            batch.alter_column("event_types", existing_type=sa.JSON(), nullable=False)

    tables = set(inspect(bind).get_table_names())
    if "webhook_events" not in tables:
        op.create_table(
            "webhook_events",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("vendor_id", sa.String(length=128), nullable=False),
            sa.Column("event_type", sa.String(length=128), nullable=False),
            sa.Column("order_id", sa.String(length=255), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_event_vendor_type", "webhook_events", ["vendor_id", "event_type"])
        op.create_index("ix_event_created_at", "webhook_events", ["created_at"])

    if "event_deliveries" not in tables:
        op.create_table(
            "event_deliveries",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_id", sa.String(length=36), nullable=False),
            sa.Column("endpoint_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("attempt_count", sa.Integer(), nullable=False),
            sa.Column("next_attempt_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("lease_until", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["event_id"], ["webhook_events.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["endpoint_id"], ["webhook_endpoints.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("event_id", "endpoint_id", name="uq_delivery_event_endpoint"),
        )
        op.create_index("ix_delivery_due", "event_deliveries", ["status", "next_attempt_at", "lease_until"])
        op.create_index("ix_delivery_endpoint_id", "event_deliveries", ["endpoint_id"])

    if "delivery_attempts" not in tables:
        op.create_table(
            "delivery_attempts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("delivery_id", sa.Integer(), nullable=False),
            sa.Column("attempt_number", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("response_status", sa.Integer(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["delivery_id"], ["event_deliveries.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("delivery_id", "attempt_number", name="uq_delivery_attempt_number"),
        )
        op.create_index("ix_delivery_attempts_delivery_id", "delivery_attempts", ["delivery_id"])

    endpoint_indexes = {item["name"] for item in inspect(bind).get_indexes("webhook_endpoints")}
    if "ix_endpoint_vendor_active" not in endpoint_indexes:
        op.create_index("ix_endpoint_vendor_active", "webhook_endpoints", ["vendor_id", "is_active"])


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    for table in ("delivery_attempts", "event_deliveries", "webhook_events"):
        if table in tables:
            op.drop_table(table)

    if "webhook_endpoints" in tables:
        indexes = {item["name"] for item in inspect(bind).get_indexes("webhook_endpoints")}
        columns = {item["name"] for item in inspect(bind).get_columns("webhook_endpoints")}
        with op.batch_alter_table("webhook_endpoints") as batch:
            if "ix_endpoint_vendor_active" in indexes:
                batch.drop_index("ix_endpoint_vendor_active")
            if "event_types" in columns:
                batch.drop_column("event_types")
            if "vendor_id" in columns:
                batch.drop_column("vendor_id")
