from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


Category = Literal[
    "job", "school", "bill", "event", "promotion", "newsletter", "personal", "other"
]


class UserProfile(BaseModel):
    role: list[str] = Field(default_factory=list)
    graduating_soon: bool = False
    priorities: list[str] = Field(default_factory=list)
    important_senders: list[str] = Field(default_factory=list)
    deprioritize: list[str] = Field(default_factory=list)
    highlight_deadlines: bool = True


class EmailIngestItem(BaseModel):
    external_id: str
    from_email: str
    from_name: str | None = None
    subject: str
    body: str
    received_at: datetime
    unread: bool = True


class ExtractedMetadata(BaseModel):
    category: Category = "other"
    importance: float = 1.0
    reason: str = ""
    action_required: bool = False
    deadline: datetime | None = None
    event_date: datetime | None = None
    company: str | None = None
    summary: str = ""
    scoring_breakdown: dict[str, float] = Field(default_factory=dict)


class ProcessedEmail(BaseModel):
    id: int
    external_id: str
    from_email: str
    from_name: str | None = None
    subject: str
    body: str
    cleaned_body: str
    received_at: datetime
    unread: bool
    metadata: ExtractedMetadata


class IngestRequest(BaseModel):
    emails: list[EmailIngestItem]


class IngestResponse(BaseModel):
    ingested: int


class DashboardResponse(BaseModel):
    top_important_emails: list[ProcessedEmail]
    upcoming_deadlines: list[ProcessedEmail]
    upcoming_events: list[ProcessedEmail]
    job_updates: list[ProcessedEmail]
    action_required: list[ProcessedEmail]


class QARequest(BaseModel):
    query: str
    limit: int = 8


class QAResponse(BaseModel):
    answer: str
    supporting_emails: list[ProcessedEmail]


class AlertItem(BaseModel):
    message: str
    severity: Literal["info", "warning", "high"] = "info"


class AlertsResponse(BaseModel):
    alerts: list[AlertItem]


class GoogleConnectResponse(BaseModel):
    auth_url: str


class GoogleConnectionStatus(BaseModel):
    configured: bool
    connected: bool
    email: str | None = None
    scopes: list[str] = Field(default_factory=list)
    connected_at: datetime | None = None
    token_encrypted: bool = False
    insecure_storage: bool = False


class GmailMessageSummary(BaseModel):
    id: str
    thread_id: str
    subject: str | None = None
    from_email: str | None = None
    from_name: str | None = None
    received_at: datetime | None = None
    snippet: str = ""
    label_ids: list[str] = Field(default_factory=list)
    is_unread: bool = False


class GmailMessageListResponse(BaseModel):
    messages: list[GmailMessageSummary]
    next_page_token: str | None = None
    result_size_estimate: int | None = None


class GmailMessageDetail(BaseModel):
    id: str
    thread_id: str
    subject: str | None = None
    from_email: str | None = None
    from_name: str | None = None
    to_email: str | None = None
    received_at: datetime | None = None
    snippet: str = ""
    body_text: str = ""
    label_ids: list[str] = Field(default_factory=list)
    is_unread: bool = False

