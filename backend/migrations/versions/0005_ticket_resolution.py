"""Store the admin-provided ticket resolution note."""

from alembic import op
import sqlalchemy as sa


revision = "0005_ticket_resolution"
down_revision = "0004_auth_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("resolution", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tickets", "resolution")
