from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta, timezone
import secrets

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse
from sqlalchemy import String, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.auth import get_admin_user, get_current_user, require_allowed_origin, require_csrf
from app.auth_security import DUMMY_PASSWORD_HASH, hash_session_token, new_session_token, normalize_login_identity, verify_password
from app.database import get_db
from app.ai_service import AIConfigurationError, AIProviderError, AIProviderTimeout, GroqHelpdeskService
from app.models import AuthSession, Ticket, TicketCategory, TicketPriority, TicketStatus, User, WorkflowEvent, WorkflowRun
from app.schemas import AIChatRequest, AIChatResponse, AnalyticsRead, AuthLoginRequest, AuthLoginResponse, AuthUserRead, CSRFTokenResponse, DashboardRead, TicketCreate, TicketRead, TicketUpdate, WorkflowConfirm, WorkflowCreate, WorkflowRead
from app.workflow_service import WorkflowTicketNotFound, confirm_workflow, serialize_workflow, start_workflow


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Schema changes are applied explicitly with Alembic; startup never seeds or
    # creates tables behind the operator's back.
    yield


settings = get_settings()
app = FastAPI(
    title="IT Helpdesk API",
    version="0.2.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)


def get_groq_service() -> GroqHelpdeskService:
    return GroqHelpdeskService(get_settings())


def ai_http_error(exc: AIProviderError | AIProviderTimeout) -> HTTPException:
    return HTTPException(
        status_code=exc.http_status,
        detail={"code": exc.code, "message": exc.safe_message},
    )


@app.get("/openapi.json", include_in_schema=False)
def openapi_schema(_user: User = Depends(get_current_user)) -> dict:
    return app.openapi()


@app.get("/docs", include_in_schema=False)
def swagger_docs(_user: User = Depends(get_current_user)) -> HTMLResponse:
    return get_swagger_ui_html(openapi_url="/openapi.json", title=f"{app.title} - Swagger UI")


@app.get("/redoc", include_in_schema=False)
def redoc_docs(_user: User = Depends(get_current_user)) -> HTMLResponse:
    return get_redoc_html(openapi_url="/openapi.json", title=f"{app.title} - ReDoc")


def _secure_cookie(request: Request) -> bool:
    return request.url.scheme == "https" or get_settings().app_env.casefold() in {"production", "prod"}


def _set_csrf_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        key=get_settings().csrf_cookie_name,
        value=token,
        max_age=get_settings().auth_session_hours * 60 * 60,
        httponly=True,
        secure=_secure_cookie(request),
        samesite="lax",
        path="/",
    )


@app.get("/api/auth/csrf", response_model=CSRFTokenResponse, dependencies=[Depends(require_allowed_origin)])
def issue_csrf_token(request: Request, response: Response) -> CSRFTokenResponse:
    """Issue a same-origin double-submit token before login or logout."""
    token = secrets.token_urlsafe(32)
    _set_csrf_cookie(response, request, token)
    response.headers["Cache-Control"] = "no-store"
    return CSRFTokenResponse(csrf_token=token)


@app.post("/api/auth/login", response_model=AuthLoginResponse)
def login(
    payload: AuthLoginRequest,
    request: Request,
    response: Response,
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> AuthLoginResponse:
    identity = normalize_login_identity(payload.login_identity)
    user = db.scalar(select(User).where(User.login_identity == identity))
    password_ok = verify_password(payload.password, user.password_hash if user else DUMMY_PASSWORD_HASH)
    if user is None or not user.is_active or not password_ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid login identity or password.")

    now = datetime.now(timezone.utc)
    raw_token = new_session_token()
    session = AuthSession(
        user_id=user.id,
        token_hash=hash_session_token(raw_token),
        created_at=now,
        expires_at=now + timedelta(hours=get_settings().auth_session_hours),
    )
    db.add(session)
    db.commit()

    response.set_cookie(
        key=get_settings().auth_cookie_name,
        value=raw_token,
        max_age=get_settings().auth_session_hours * 60 * 60,
        httponly=True,
        secure=_secure_cookie(request),
        samesite="lax",
        path="/",
    )
    csrf_token = secrets.token_urlsafe(32)
    _set_csrf_cookie(response, request, csrf_token)
    response.headers["Cache-Control"] = "no-store"
    return AuthLoginResponse(user=AuthUserRead.model_validate(user), csrf_token=csrf_token)


@app.get("/api/auth/me", response_model=AuthUserRead)
def auth_me(user: User = Depends(get_current_user)) -> AuthUserRead:
    return AuthUserRead.model_validate(user)


@app.post("/api/auth/logout", dependencies=[Depends(require_csrf)])
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> dict[str, str]:
    raw_token = request.cookies.get(get_settings().auth_cookie_name)
    if raw_token:
        session = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_session_token(raw_token)))
        if session is not None and session.revoked_at is None:
            session.revoked_at = datetime.now(timezone.utc)
            db.commit()
    secure = _secure_cookie(request)
    response.delete_cookie(key=get_settings().auth_cookie_name, path="/", secure=secure, httponly=True, samesite="lax")
    response.delete_cookie(key=get_settings().csrf_cookie_name, path="/", secure=secure, httponly=True, samesite="lax")
    response.headers["Cache-Control"] = "no-store"
    return {"status": "logged_out"}


@app.post("/api/ai/chat", response_model=AIChatResponse, dependencies=[Depends(require_csrf)])
def ai_chat(
    payload: AIChatRequest,
    _user: User = Depends(get_current_user),
    service: GroqHelpdeskService = Depends(get_groq_service),
) -> AIChatResponse:
    try:
        result = service.answer(payload.issue)
    except AIConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": "GROQ_NOT_CONFIGURED", "message": str(exc)}) from None
    except (AIProviderTimeout, AIProviderError) as exc:
        raise ai_http_error(exc) from None
    return AIChatResponse(
        reply=result.text,
        source_articles=[{"title": article.title, "category": article.category} for article in result.sources],
    )


@app.post("/api/workflows", response_model=WorkflowRead, status_code=status.HTTP_201_CREATED)
def create_workflow(
    payload: WorkflowCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
    service: GroqHelpdeskService = Depends(get_groq_service),
) -> dict:
    if payload.ticket_id:
        linked_ticket = _accessible_ticket(db, payload.ticket_id, user)
        if linked_ticket is None:
            raise HTTPException(status_code=404, detail="The linked ticket was not found.")
    try:
        run = start_workflow(db, payload.issue, payload.ticket_id, service, user.id)
    except WorkflowTicketNotFound:
        raise HTTPException(status_code=404, detail="The linked ticket was not found.") from None
    except AIConfigurationError as exc:
        raise HTTPException(status_code=503, detail={"code": "GROQ_NOT_CONFIGURED", "message": f"{exc} No workflow tool was run."}) from None
    except (AIProviderTimeout, AIProviderError) as exc:
        safe_message = exc.safe_message
        if isinstance(exc, AIProviderTimeout):
            safe_message = "Groq timed out while preparing the diagnosis. No workflow tool was run; please retry."
        elif exc.code not in {"GROQ_AUTH_FAILED", "GROQ_RATE_LIMITED", "GROQ_MODEL_UNAVAILABLE", "GROQ_REQUEST_REJECTED", "GROQ_CONNECTION_ERROR", "GROQ_INVALID_DIAGNOSIS", "GROQ_EMPTY_RESPONSE", "GROQ_INCOMPLETE_RESPONSE", "GROQ_UNSAFE_RESPONSE", "GROQ_UNGROUNDED_RESPONSE"}:
            safe_message = "Groq could not prepare a diagnosis. No workflow tool was run; please retry."
        raise HTTPException(status_code=exc.http_status, detail={"code": exc.code, "message": safe_message}) from None
    return serialize_workflow(db, run)


@app.get("/api/workflows", response_model=list[WorkflowRead])
def list_workflows(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    statement = select(WorkflowRun)
    if user.role != "admin":
        statement = statement.where(
            WorkflowRun.user_id == user.id,
            or_(WorkflowRun.ticket_id.is_(None), WorkflowRun.ticket_id.in_(select(Ticket.id).where(Ticket.user_id == user.id))),
        )
    statement = statement.order_by(WorkflowRun.created_at.desc())
    if user.role != "admin":
        statement = statement.limit(50)
    runs = db.scalars(statement).all()
    return [serialize_workflow(db, run) for run in runs]


@app.get("/api/workflows/{workflow_id}", response_model=WorkflowRead)
def get_workflow(workflow_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    run = _accessible_workflow(db, workflow_id, user)
    return serialize_workflow(db, run)


@app.post("/api/workflows/{workflow_id}/confirm", response_model=WorkflowRead)
def workflow_confirm(
    workflow_id: str,
    payload: WorkflowConfirm,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _csrf: None = Depends(require_csrf),
) -> dict:
    run = _accessible_workflow(db, workflow_id, user)
    try:
        confirm_workflow(db, run, payload.fixed)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return serialize_workflow(db, run)


@app.get("/api/health")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(select(1))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database is unavailable.") from exc
    return {"status": "ok", "database": "connected"}


@app.get("/api/dashboard", response_model=DashboardRead)
def dashboard(
    days: int = Query(default=7, ge=7, le=90),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Return ticket metrics and persisted activity for the selected UTC date range."""
    ticket_scope = select(Ticket)
    workflow_scope = select(WorkflowRun)
    if user.role != "admin":
        ticket_scope = ticket_scope.where(Ticket.user_id == user.id)
        workflow_scope = workflow_scope.where(
            WorkflowRun.user_id == user.id,
            or_(WorkflowRun.ticket_id.is_(None), WorkflowRun.ticket_id.in_(select(Ticket.id).where(Ticket.user_id == user.id))),
        )
    ticket_ids = ticket_scope.with_only_columns(Ticket.id).subquery()
    workflow_ids = workflow_scope.with_only_columns(WorkflowRun.id).subquery()
    status_counts = dict(db.execute(
        select(Ticket.status, func.count()).where(Ticket.id.in_(select(ticket_ids.c.id))).group_by(Ticket.status)
    ).all())
    priority_counts = dict(db.execute(
        select(Ticket.priority, func.count())
        .where(Ticket.id.in_(select(ticket_ids.c.id)), Ticket.status == TicketStatus.open)
        .group_by(Ticket.priority)
    ).all())

    today = datetime.now(timezone.utc).date()
    first_day = today - timedelta(days=days - 1)
    range_start = datetime.combine(first_day, time.min, tzinfo=timezone.utc)
    range_end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=timezone.utc)
    timestamp_rows = db.execute(
        select(Ticket.created_at, Ticket.resolved_at).where(
            Ticket.id.in_(select(ticket_ids.c.id)),
            or_(
                (Ticket.created_at >= range_start) & (Ticket.created_at < range_end),
                (Ticket.resolved_at >= range_start) & (Ticket.resolved_at < range_end),
            )
        )
    ).all()
    daily = {first_day + timedelta(days=offset): {"created": 0, "resolved": 0} for offset in range(days)}

    def as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    for created_at, resolved_at in timestamp_rows:
        created_utc = as_utc(created_at)
        resolved_utc = as_utc(resolved_at)
        if created_utc and first_day <= created_utc.date() <= today:
            daily[created_utc.date()]["created"] += 1
        if resolved_utc and first_day <= resolved_utc.date() <= today:
            daily[resolved_utc.date()]["resolved"] += 1

    recent_tickets = db.scalars(
        select(Ticket).where(Ticket.id.in_(select(ticket_ids.c.id))).order_by(Ticket.created_at.desc(), Ticket.id.desc()).limit(4)
    ).all()
    activity_rows = db.execute(
        select(WorkflowEvent, WorkflowRun.ticket_id)
        .join(WorkflowRun, WorkflowEvent.workflow_id == WorkflowRun.id)
        .where(WorkflowRun.id.in_(select(workflow_ids.c.id)))
        .order_by(WorkflowEvent.created_at.desc(), WorkflowEvent.id.desc())
        .limit(5)
    ).all()
    # Existing workflow verifications are deterministic simulations, and user confirmation
    # is not an independently verified environment outcome. Report unavailable until such
    # outcomes are represented by a trustworthy persisted record.
    return {
        "open_tickets": status_counts.get(TicketStatus.open, 0),
        "in_progress_tickets": status_counts.get(TicketStatus.in_progress, 0),
        "resolved_tickets": status_counts.get(TicketStatus.resolved, 0),
        "ai_verified_resolutions": None,
        "priority_distribution": {priority.value: priority_counts.get(priority, 0) for priority in TicketPriority},
        "daily_volume": [{"date": day, **counts} for day, counts in daily.items()],
        "recent_tickets": recent_tickets,
        "ai_activity": [
            {
                "workflow_id": event.workflow_id,
                "ticket_id": ticket_id,
                "stage": event.stage,
                "status": event.status,
                "detail": event.detail,
                "created_at": event.created_at,
                "simulated": event.stage == "simulated_tool",
            }
            for event, ticket_id in activity_rows
        ],
    }


@app.get("/api/analytics", response_model=AnalyticsRead)
def analytics(
    days: int = Query(default=30, ge=7, le=90),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Return organization-wide analytics from persisted records for admins only."""
    get_admin_user(user)
    today = datetime.now(timezone.utc).date()
    first_day = today - timedelta(days=days - 1)
    range_start = datetime.combine(first_day, time.min, tzinfo=timezone.utc)
    range_end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=timezone.utc)
    created_range = (Ticket.created_at >= range_start) & (Ticket.created_at < range_end)

    total_tickets = db.scalar(select(func.count(Ticket.id)).where(created_range)) or 0
    resolved_tickets = db.scalar(
        select(func.count(Ticket.id)).where(
            created_range,
            Ticket.status == TicketStatus.resolved,
            Ticket.resolved_at.is_not(None),
        )
    ) or 0
    category_rows = db.execute(
        select(Ticket.category, func.count(Ticket.id))
        .where(created_range)
        .group_by(Ticket.category)
        .order_by(Ticket.category)
    ).all()
    tickets_with_workflow = db.scalar(
        select(func.count(func.distinct(WorkflowRun.ticket_id)))
        .join(Ticket, Ticket.id == WorkflowRun.ticket_id)
        .where(created_range)
    ) or 0

    timestamp_rows = db.execute(
        select(Ticket.created_at, Ticket.resolved_at).where(
            (created_range)
            | ((Ticket.resolved_at >= range_start) & (Ticket.resolved_at < range_end))
        )
    ).all()
    daily = {first_day + timedelta(days=offset): {"created": 0, "resolved": 0} for offset in range(days)}

    def as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    for created_at, resolved_at in timestamp_rows:
        created_utc = as_utc(created_at)
        resolved_utc = as_utc(resolved_at)
        if created_utc and range_start <= created_utc < range_end:
            daily[created_utc.date()]["created"] += 1
        if resolved_utc and range_start <= resolved_utc < range_end:
            daily[resolved_utc.date()]["resolved"] += 1

    return {
        "days": days,
        "total_tickets": total_tickets,
        "resolved_tickets": resolved_tickets,
        "resolution_rate_percent": round(resolved_tickets / total_tickets * 100, 1) if total_tickets else None,
        # The database has no first-response timestamp, so this metric is intentionally unavailable.
        "average_first_response_minutes": None,
        "tickets_with_workflow": tickets_with_workflow,
        "daily_volume": [{"date": day, **counts} for day, counts in daily.items()],
        "category_distribution": [
            {"category": category.value if isinstance(category, TicketCategory) else str(category), "count": count}
            for category, count in category_rows
        ],
    }


@app.get("/api/tickets", response_model=list[TicketRead])
def list_tickets(
    search: str | None = Query(default=None, max_length=100),
    status_filter: TicketStatus | None = Query(default=None, alias="status"),
    priority: TicketPriority | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[Ticket]:
    statement = select(Ticket).order_by(Ticket.created_at.desc(), Ticket.id.desc())
    if user.role != "admin":
        statement = statement.where(Ticket.user_id == user.id)
    if search and search.strip():
        needle = f"%{search.strip()}%"
        statement = statement.where(
            Ticket.title.ilike(needle)
            | Ticket.description.ilike(needle)
            | Ticket.category.cast(String).ilike(needle)
            | Ticket.id.ilike(needle)
        )
    if status_filter is not None:
        statement = statement.where(Ticket.status == status_filter)
    if priority is not None:
        statement = statement.where(Ticket.priority == priority)
    return list(db.scalars(statement).all())


@app.get("/api/tickets/{ticket_id}", response_model=TicketRead)
def get_ticket(ticket_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Ticket:
    ticket = _accessible_ticket(db, ticket_id, user)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket was not found.")
    return ticket


@app.post("/api/tickets", response_model=TicketRead, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)])
def create_ticket(payload: TicketCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Ticket:
    ticket_values = payload.model_dump(exclude={"owner"})
    ticket = Ticket(**ticket_values, owner=user.login_identity, user_id=user.id)
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


@app.patch("/api/tickets/{ticket_id}", response_model=TicketRead, dependencies=[Depends(require_csrf)])
def update_ticket(
    ticket_id: str,
    payload: TicketUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Ticket:
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Provide at least one ticket field to update.")
    if any(value is None for value in changes.values()):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Ticket fields cannot be set to null.")
    ticket = _accessible_ticket(db, ticket_id, user)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket was not found.")
    privileged_fields = {"category", "priority", "status", "resolution"}
    if privileged_fields.intersection(changes):
        get_admin_user(user)
    previous_status = ticket.status
    if changes.get("status") == TicketStatus.resolved and previous_status != TicketStatus.resolved and not changes.get("resolution"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Add a resolution note describing the fix before resolving this ticket.",
        )
    for field, value in changes.items():
        setattr(ticket, field, value)
    if "status" in changes and changes["status"] != previous_status:
        ticket.resolved_at = datetime.now(timezone.utc) if changes["status"] == TicketStatus.resolved else None
    db.commit()
    db.refresh(ticket)
    return ticket


def _accessible_ticket(db: Session, ticket_id: str, user: User) -> Ticket | None:
    statement = select(Ticket).where(Ticket.id == ticket_id.upper())
    if user.role != "admin":
        statement = statement.where(Ticket.user_id == user.id)
    return db.scalar(statement)


def _accessible_workflow(db: Session, workflow_id: str, user: User) -> WorkflowRun:
    statement = select(WorkflowRun).where(WorkflowRun.id == workflow_id)
    if user.role != "admin":
        statement = statement.where(WorkflowRun.user_id == user.id)
    run = db.scalar(statement)
    if run is None:
        raise HTTPException(status_code=404, detail="Workflow run was not found.")
    if user.role != "admin" and run.ticket_id is not None:
        linked_ticket = db.get(Ticket, run.ticket_id)
        if linked_ticket is None or linked_ticket.user_id != user.id:
            raise HTTPException(status_code=404, detail="Workflow run was not found.")
    return run
