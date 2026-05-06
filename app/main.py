from __future__ import annotations

from contextlib import asynccontextmanager
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app import db, service
from app.ai_runtime import AIProcessingError, AIRuntimeError
from app.alerts import generate_alerts
from app.capabilities import get_capabilities
from app.config import settings
from app.gmail_integration import (
    GmailNotConnectedError,
    GoogleOAuthConfigError,
    GoogleOAuthFlowError,
    build_google_auth_url,
    disconnect_google_account,
    get_gmail_message_detail,
    get_google_connection_status,
    handle_google_callback,
    list_gmail_messages,
)
from app.session_logs import initialize_session_logs, log_ask_inbox_interaction
from app.schemas import (
    AlertsResponse,
    CapabilitiesResponse,
    GmailMessageDetail,
    GmailMessageListResponse,
    GoogleConnectionStatus,
    GoogleConnectResponse,
    IngestRequest,
    IngestResponse,
    ProcessedEmail,
    QARequest,
    QAResponse,
    UserProfile,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    initialize_session_logs()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.frontend_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_ai_capability() -> None:
    capabilities = get_capabilities()
    if capabilities.can_rank_inbox:
        return
    raise HTTPException(status_code=503, detail=capabilities.openai.message)


def _raise_ai_http_error(exc: Exception) -> None:
    if isinstance(exc, AIRuntimeError):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if isinstance(exc, AIProcessingError):
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail="Unexpected AI processing failure.") from exc


@app.get("/")
def root() -> dict[str, str]:
    return {"service": settings.app_name, "status": "ok"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/capabilities", response_model=CapabilitiesResponse)
def capabilities() -> CapabilitiesResponse:
    return get_capabilities()


@app.put("/profile", response_model=UserProfile)
@app.post("/profile", response_model=UserProfile)
def upsert_profile(profile: UserProfile) -> UserProfile:
    return db.save_profile(profile)


@app.get("/profile", response_model=UserProfile)
def get_profile() -> UserProfile:
    return db.get_profile()


@app.post("/emails/ingest", response_model=IngestResponse)
def ingest_emails(request: IngestRequest) -> IngestResponse:
    _require_ai_capability()
    profile = db.get_profile()
    try:
        for email in request.emails:
            service.process_email(email, profile)
        return IngestResponse(ingested=len(request.emails))
    except (AIRuntimeError, AIProcessingError) as exc:
        _raise_ai_http_error(exc)


@app.get("/emails", response_model=list[ProcessedEmail])
def list_emails(limit: int = Query(default=50, ge=1, le=5000)) -> list[ProcessedEmail]:
    return service.list_recent_emails(limit=limit)


@app.get("/dashboard")
def dashboard(top_n: int = Query(default=5, ge=1, le=200)):
    _require_ai_capability()
    try:
        return service.build_dashboard(top_n=top_n)
    except (AIRuntimeError, AIProcessingError) as exc:
        _raise_ai_http_error(exc)


@app.post("/qa", response_model=QAResponse)
def qa(request: QARequest) -> QAResponse:
    _require_ai_capability()
    try:
        response = service.qa_over_inbox(request.query, request.limit)
        log_ask_inbox_interaction(request.query, response.answer)
        return response
    except (AIRuntimeError, AIProcessingError) as exc:
        _raise_ai_http_error(exc)


@app.get("/alerts", response_model=AlertsResponse)
def alerts() -> AlertsResponse:
    _require_ai_capability()
    profile = db.get_profile()
    try:
        if db.get_google_oauth_token() is not None:
            db.delete_sample_emails()
        service.refresh_profile_scores(profile, limit=200)
        deadline_items = [
            email for email in db.list_with_deadlines(limit=40) if not email.external_id.startswith("smoke-")
        ]
        action_items = [
            email for email in db.list_action_required(limit=40) if not email.external_id.startswith("smoke-")
        ]
        top_important = [
            email for email in db.list_top_important(limit=60) if not email.external_id.startswith("smoke-")
        ]
        unread_important_count = db.count_unread_important(min_importance=7.0)
        return AlertsResponse(
            alerts=generate_alerts(
                profile=profile,
                deadlines=deadline_items,
                action_required=action_items,
                top_important=top_important,
                unread_important_count=unread_important_count,
            )
        )
    except (AIRuntimeError, AIProcessingError) as exc:
        _raise_ai_http_error(exc)


@app.get("/gmail/connection", response_model=GoogleConnectionStatus)
def gmail_connection_status() -> GoogleConnectionStatus:
    return get_google_connection_status()


@app.get("/auth/google/connect", response_model=GoogleConnectResponse)
def google_connect() -> GoogleConnectResponse:
    try:
        return GoogleConnectResponse(auth_url=build_google_auth_url())
    except GoogleOAuthConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/auth/google/callback")
def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    base = settings.frontend_app_url.rstrip("/")
    if not base:
        base = "http://127.0.0.1:5173"

    if error:
        query = urlencode({"gmail": "error", "reason": error})
        return RedirectResponse(url=f"{base}/?{query}", status_code=302)

    if not code or not state:
        query = urlencode({"gmail": "error", "reason": "missing_code_or_state"})
        return RedirectResponse(url=f"{base}/?{query}", status_code=302)

    try:
        email = handle_google_callback(code=code, state=state)
        params = {"gmail": "connected"}
        if email:
            params["email"] = email
        query = urlencode(params)
        return RedirectResponse(url=f"{base}/?{query}", status_code=302)
    except (GoogleOAuthConfigError, GoogleOAuthFlowError, RuntimeError) as exc:
        query = urlencode({"gmail": "error", "reason": str(exc)})
        return RedirectResponse(url=f"{base}/?{query}", status_code=302)


@app.post("/auth/google/disconnect", response_model=GoogleConnectionStatus)
def google_disconnect() -> GoogleConnectionStatus:
    disconnect_google_account()
    return get_google_connection_status()


@app.get("/gmail/messages", response_model=GmailMessageListResponse)
def gmail_messages(
    max_results: int = Query(default=20, ge=1, le=50),
    page_token: str | None = Query(default=None),
    q: str | None = Query(default=None),
    label_ids: list[str] | None = Query(default=None),
) -> GmailMessageListResponse:
    try:
        return list_gmail_messages(
            max_results=max_results,
            page_token=page_token,
            query=q,
            label_ids=label_ids,
        )
    except GmailNotConnectedError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/gmail/messages/{message_id}", response_model=GmailMessageDetail)
def gmail_message_detail(message_id: str) -> GmailMessageDetail:
    try:
        return get_gmail_message_detail(message_id)
    except GmailNotConnectedError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/gmail/sync", response_model=IngestResponse)
def gmail_sync(
    max_messages: int = Query(default=150, ge=1, le=500),
    q: str | None = Query(default=None),
    label_ids: list[str] | None = Query(default=None),
    clear_non_gmail: bool = Query(default=False),
    backfill: bool = Query(default=False),
    reset_backfill: bool = Query(default=False),
    sync_until_complete: bool = Query(default=False),
) -> IngestResponse:
    _require_ai_capability()
    try:
        result = service.sync_connected_gmail(
            max_messages=max_messages,
            query=q,
            label_ids=label_ids,
            clear_non_gmail=clear_non_gmail,
            backfill=backfill,
            reset_backfill=reset_backfill,
            sync_until_complete=sync_until_complete,
        )
        return IngestResponse(
            ingested=result.ingested,
            has_more=result.has_more,
            backfill_complete=result.backfill_complete,
        )
    except GmailNotConnectedError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except (AIRuntimeError, AIProcessingError) as exc:
        _raise_ai_http_error(exc)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
