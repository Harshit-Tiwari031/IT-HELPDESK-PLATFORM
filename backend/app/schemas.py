from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import TicketCategory, TicketPriority, TicketStatus


class AuthLoginRequest(BaseModel):
    login_identity: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=1024)

    model_config = ConfigDict(extra="forbid")

    @field_validator("login_identity")
    @classmethod
    def normalize_identity(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not normalized:
            raise ValueError("Login identity cannot be blank.")
        return normalized


class AuthUserRead(BaseModel):
    id: str
    login_identity: str
    role: Literal["user", "admin"]

    model_config = ConfigDict(from_attributes=True)


class AuthLoginResponse(BaseModel):
    user: AuthUserRead
    csrf_token: str


class CSRFTokenResponse(BaseModel):
    csrf_token: str


class AIChatRequest(BaseModel):
    issue: str = Field(min_length=5, max_length=2000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("issue")
    @classmethod
    def strip_issue(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 5:
            raise ValueError("Describe the issue in at least 5 characters.")
        return cleaned


class KnowledgeSourceRead(BaseModel):
    title: str
    category: str


class AIChatResponse(BaseModel):
    reply: str
    source_articles: list[KnowledgeSourceRead]


class WorkflowCreate(BaseModel):
    issue: str = Field(min_length=5, max_length=2000)
    ticket_id: str | None = Field(default=None, pattern=r"^HD-[A-F0-9]{8}$")

    model_config = ConfigDict(extra="forbid")

    @field_validator("issue")
    @classmethod
    def strip_workflow_issue(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 5:
            raise ValueError("Describe the issue in at least 5 characters.")
        return cleaned


class WorkflowConfirm(BaseModel):
    fixed: bool
    model_config = ConfigDict(extra="forbid")


class WorkflowDiagnosis(BaseModel):
    summary: str = Field(min_length=8, max_length=500)
    category: TicketCategory
    suggested_priority: TicketPriority
    likely_causes: list[str] = Field(min_length=1, max_length=5)
    troubleshooting_steps: list[str] = Field(min_length=1, max_length=7)


class WorkflowEventRead(BaseModel):
    stage: str
    status: str
    detail: str
    evidence: dict
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkflowRead(BaseModel):
    id: str
    issue: str
    status: str
    current_stage: str
    diagnosis: WorkflowDiagnosis
    sources: list[KnowledgeSourceRead]
    tool_name: str
    tool_input: dict
    tool_output: dict
    verification: dict
    proposed_resolution: str
    next_action: str
    ticket_id: str | None
    created_at: datetime
    updated_at: datetime
    events: list[WorkflowEventRead]

    model_config = ConfigDict(from_attributes=True)


class TicketCreate(BaseModel):
    title: str = Field(min_length=5, max_length=90)
    description: str = Field(min_length=10, max_length=5000)
    category: TicketCategory
    priority: TicketPriority = TicketPriority.medium
    owner: str = Field(default="IT Support Requester", min_length=1, max_length=100)

    model_config = ConfigDict(extra="forbid")

    @field_validator("title", "description", "owner")
    @classmethod
    def strip_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("This field cannot be blank.")
        return cleaned


class TicketUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=5, max_length=90)
    description: str | None = Field(default=None, min_length=10, max_length=5000)
    category: TicketCategory | None = None
    priority: TicketPriority | None = None
    status: TicketStatus | None = None
    resolution: str | None = Field(default=None, min_length=10, max_length=2000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("title", "description", "resolution")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("This field cannot be blank.")
        return cleaned


class TicketRead(BaseModel):
    id: str
    title: str
    description: str
    category: TicketCategory
    priority: TicketPriority
    status: TicketStatus
    owner: str
    resolution: str | None = None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class DashboardDayVolume(BaseModel):
    date: date
    created: int
    resolved: int


class DashboardActivityRead(BaseModel):
    workflow_id: str
    ticket_id: str | None
    stage: str
    status: str
    detail: str
    created_at: datetime
    simulated: bool


class DashboardRead(BaseModel):
    open_tickets: int
    in_progress_tickets: int
    resolved_tickets: int
    ai_verified_resolutions: int | None
    priority_distribution: dict[str, int]
    daily_volume: list[DashboardDayVolume]
    recent_tickets: list[TicketRead]
    ai_activity: list[DashboardActivityRead]


class AnalyticsDayVolume(BaseModel):
    date: date
    created: int
    resolved: int


class AnalyticsCategoryCount(BaseModel):
    category: str
    count: int


class AnalyticsRead(BaseModel):
    days: int
    total_tickets: int
    resolved_tickets: int
    resolution_rate_percent: float | None
    average_first_response_minutes: float | None
    tickets_with_workflow: int
    daily_volume: list[AnalyticsDayVolume]
    category_distribution: list[AnalyticsCategoryCount]
