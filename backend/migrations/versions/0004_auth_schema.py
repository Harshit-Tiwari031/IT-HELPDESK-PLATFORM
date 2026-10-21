"""Add user accounts, revocable sessions, and nullable record ownership links."""

from alembic import op
import sqlalchemy as sa

revision = "0004_auth_schema"
down_revision = "0003_ticket_resolved_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("login_identity", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), server_default="user", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("length(trim(login_identity)) > 0", name="ck_users_login_identity_not_empty"),
        sa.CheckConstraint("login_identity = lower(trim(login_identity))", name="ck_users_login_identity_normalized"),
        sa.CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("login_identity", name="uq_users_login_identity"),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_sessions_user_id_users", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])

    op.add_column("tickets", sa.Column("user_id", sa.String(length=36), nullable=True))
    op.create_foreign_key("fk_tickets_user_id_users", "tickets", "users", ["user_id"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_tickets_user_id", "tickets", ["user_id"])

    op.add_column("workflow_runs", sa.Column("user_id", sa.String(length=36), nullable=True))
    op.create_foreign_key("fk_workflow_runs_user_id_users", "workflow_runs", "users", ["user_id"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_workflow_runs_user_id", "workflow_runs", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_workflow_runs_user_id", table_name="workflow_runs")
    op.drop_constraint("fk_workflow_runs_user_id_users", "workflow_runs", type_="foreignkey")
    op.drop_column("workflow_runs", "user_id")

    op.drop_index("ix_tickets_user_id", table_name="tickets")
    op.drop_constraint("fk_tickets_user_id_users", "tickets", type_="foreignkey")
    op.drop_column("tickets", "user_id")

    op.drop_index("ix_sessions_expires_at", table_name="sessions")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("users")
