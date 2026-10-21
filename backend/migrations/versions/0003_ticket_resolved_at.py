"""Add factual ticket resolution timestamps."""

from alembic import op
import sqlalchemy as sa

revision = "0003_ticket_resolved_at"
down_revision = "0002_workflow_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("tickets", "resolved_at")
