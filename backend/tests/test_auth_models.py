from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Base
from app.models import AuthSession, Ticket, TicketCategory, TicketPriority, TicketStatus, User, WorkflowEvent, WorkflowRun


def test_auth_schema_is_additive_and_links_are_nullable_and_restrictive():
    assert {"tickets", "workflow_runs", "workflow_events", "users", "sessions"}.issubset(Base.metadata.tables)
    assert Ticket.__table__.c.owner.nullable is False
    assert Ticket.__table__.c.user_id.nullable is True
    assert WorkflowRun.__table__.c.user_id.nullable is True
    assert next(iter(Ticket.__table__.c.user_id.foreign_keys)).ondelete == "RESTRICT"
    assert next(iter(WorkflowRun.__table__.c.user_id.foreign_keys)).ondelete == "RESTRICT"
    assert next(iter(AuthSession.__table__.c.user_id.foreign_keys)).ondelete == "RESTRICT"
    assert User.__table__.c.password_hash.type.length == 255
    assert AuthSession.__table__.c.token_hash.type.length == 64
    assert {constraint.name for constraint in User.__table__.constraints} >= {
        "uq_users_login_identity",
        "ck_users_login_identity_not_empty",
        "ck_users_login_identity_normalized",
        "ck_users_role",
    }


def test_auth_migration_follows_current_head():
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    revision = script.get_revision("0004_auth_schema")
    assert revision is not None
    assert revision.down_revision == "0003_ticket_resolved_at"
    assert script.get_current_head() == "0005_ticket_resolution"
    resolution_revision = script.get_revision("0005_ticket_resolution")
    assert resolution_revision is not None
    assert resolution_revision.down_revision == "0004_auth_schema"
    assert Ticket.__table__.c.resolution.nullable is True


def test_account_delete_is_restricted_and_role_and_identity_constraints_are_enforced():
    engine = create_engine("sqlite+pysqlite://")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        user = User(login_identity="admin@example.edu", password_hash="$argon2id$test-hash", role="admin")
        db.add(user)
        db.flush()
        ticket = Ticket(
            id="HD-AUTH0001", title="Existing issue", description="Historical issue details",
            category=TicketCategory.network, priority=TicketPriority.high, status=TicketStatus.open,
            owner="Historical owner text", user_id=user.id,
        )
        run = WorkflowRun(
            id="run-auth-test", issue="Historical workflow issue", status="needs_escalation",
            current_stage="escalation_recommended", diagnosis={}, sources=[], tool_name="network_check",
            tool_input={}, tool_output={}, verification={}, proposed_resolution="", next_action="",
            ticket_id=ticket.id, user_id=user.id,
        )
        db.add_all([ticket, run])
        db.flush()
        db.add(WorkflowEvent(workflow_id=run.id, stage="issue_received", status="complete", detail="Persisted audit event", evidence={}))
        db.add(AuthSession(user_id=user.id, token_hash="a" * 64, expires_at=now + timedelta(hours=1)))
        db.commit()

        user_id = user.id
        db.delete(user)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        assert db.scalar(select(User.id).where(User.id == user_id)) == user_id
        assert db.scalar(select(Ticket.id).where(Ticket.id == ticket.id)) == ticket.id
        assert db.scalar(select(WorkflowRun.id).where(WorkflowRun.id == run.id)) == run.id
        assert len(db.scalars(select(WorkflowEvent)).all()) == 1

        db.add(User(login_identity="Admin@Example.edu", password_hash="$argon2id$test-hash", role="admin"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(User(login_identity="another@example.edu", password_hash="$argon2id$test-hash", role="superadmin"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    assert inspect(engine).has_table("tickets")
    assert inspect(engine).has_table("workflow_runs")
    assert inspect(engine).has_table("workflow_events")
    engine.dispose()
