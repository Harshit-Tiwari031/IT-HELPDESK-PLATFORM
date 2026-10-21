"""Create the tickets table."""

from alembic import op
import sqlalchemy as sa

revision = "0001_create_tickets"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tickets",
        sa.Column("id", sa.String(length=15), nullable=False),
        sa.Column("title", sa.String(length=90), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.Enum("Network", "Account", "Hardware", "Software", "Access", "Other", name="ticketcategory", native_enum=False, create_constraint=True), nullable=False),
        sa.Column("priority", sa.Enum("High", "Medium", "Low", name="ticketpriority", native_enum=False, create_constraint=True), nullable=False),
        sa.Column("status", sa.Enum("Open", "In Progress", "Resolved", name="ticketstatus", native_enum=False, create_constraint=True), nullable=False),
        sa.Column("owner", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tickets_title", "tickets", ["title"])
    op.create_index("ix_tickets_category", "tickets", ["category"])
    op.create_index("ix_tickets_priority", "tickets", ["priority"])
    op.create_index("ix_tickets_status", "tickets", ["status"])


def downgrade() -> None:
    op.drop_index("ix_tickets_status", table_name="tickets")
    op.drop_index("ix_tickets_priority", table_name="tickets")
    op.drop_index("ix_tickets_category", table_name="tickets")
    op.drop_index("ix_tickets_title", table_name="tickets")
    op.drop_table("tickets")
