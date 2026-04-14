from __future__ import annotations

from contextlib import asynccontextmanager
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app import db, service
from app.alerts import generate_alerts
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
from app.schemas import (
    AlertsResponse,
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
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.frontend_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> dict[str, str]:
    return {"service": settings.app_name, "status": "ok"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.put("/profile", response_model=UserProfile)
@app.post("/profile", response_model=UserProfile)
def upsert_profile(profile: UserProfile) -> UserProfile:
    return db.save_profile(profile)


@app.get("/profile", response_model=UserProfile)
def get_profile() -> UserProfile:
    return db.get_profile()


@app.post("/emails/ingest", response_model=IngestResponse)
def ingest_emails(request: IngestRequest) -> IngestResponse:
    profile = db.get_profile()
    for email in request.emails:
        service.process_email(email, profile)
    return IngestResponse(ingested=len(request.emails))


@app.get("/emails", response_model=list[ProcessedEmail])
def list_emails(limit: int = Query(default=50, ge=1, le=200)) -> list[ProcessedEmail]:
    return service.list_recent_emails(limit=limit)


@app.get("/dashboard")
def dashboard(top_n: int = Query(default=5, ge=1, le=20)):
    return service.build_dashboard(top_n=top_n)


@app.post("/qa", response_model=QAResponse)
def qa(request: QARequest) -> QAResponse:
    return service.qa_over_inbox(request.query, request.limit)


@app.get("/alerts", response_model=AlertsResponse)
def alerts() -> AlertsResponse:
    profile = db.get_profile()
    deadline_items = db.list_with_deadlines(limit=40)
    action_items = db.list_action_required(limit=40)
    top_important = db.list_top_important(limit=60)
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
) -> IngestResponse:
    try:
        ingested = service.sync_connected_gmail(
            max_messages=max_messages,
            query=q,
            label_ids=label_ids,
            clear_non_gmail=clear_non_gmail,
        )
        return IngestResponse(ingested=ingested)
    except GmailNotConnectedError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
