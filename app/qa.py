from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, ValidationError

from app.ai_runtime import get_openai_client, raise_ai_processing_error, record_ai_success, run_openai_request
from app.config import settings
from app.prompting import ASK_INBOX_SYSTEM_PROMPT, build_qa_user_payload
from app.schemas import ProcessedEmail, QAResponse, UserProfile


logger = logging.getLogger(__name__)
QA_MAX_COMPLETION_TOKENS = 420


class QACompletionPayload(BaseModel):
    answer: str
    citations: list[str]


def _load_completion_payload(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].lstrip()
    return json.loads(cleaned or "{}")


def _fallback_answer(query: str, candidates: list[ProcessedEmail]) -> QAResponse:
    supporting = candidates[:3]
    citations = [email.external_id for email in supporting]
    subjects = [email.subject.strip() for email in supporting if email.subject.strip()]
    lower_query = query.lower()

    if not supporting:
        return QAResponse(
            answer="I could not find a grounded answer in the indexed emails.",
            answer_mode="openai_rag",
            citations=[],
            supporting_emails=[],
        )

    if any(term in lower_query for term in ("interview", "job", "recruit", "thread")):
        answer = "The most relevant open job/interview threads are: " + "; ".join(subjects) + "."
    else:
        answer = (
            f"The highest-ranked email to start with is '{subjects[0]}'. "
            + (
                "Other relevant emails include " + "; ".join(subjects[1:]) + "."
                if len(subjects) > 1
                else ""
            )
        ).strip()

    return QAResponse(
        answer=answer,
        answer_mode="openai_rag",
        citations=citations,
        supporting_emails=supporting,
    )


def parse_qa_payload(
    data: dict[str, Any],
    *,
    ranked_emails: list[ProcessedEmail],
) -> tuple[str, list[str], list[ProcessedEmail]] | None:
    try:
        parsed = QACompletionPayload.model_validate(data)
    except ValidationError:
        return None

    lookup = {email.external_id: email for email in ranked_emails}
    citations: list[str] = []
    supporting: list[ProcessedEmail] = []
    for citation in parsed.citations:
        if citation not in lookup or citation in citations:
            continue
        citations.append(citation)
        supporting.append(lookup[citation])

    if not supporting:
        supporting = ranked_emails[:3]
        citations = [email.external_id for email in supporting]

    answer = parsed.answer.strip() or "I could not find a grounded answer in the indexed emails."
    return answer, citations, supporting


def answer_query(
    query: str,
    candidates: list[ProcessedEmail],
    *,
    profile: UserProfile,
) -> QAResponse:
    if not candidates:
        return QAResponse(
            answer="No emails are currently indexed. Sync Gmail or ingest emails first.",
            answer_mode="openai_rag",
            citations=[],
            supporting_emails=[],
        )

    try:
        client = get_openai_client()
        payload = build_qa_user_payload(query=query, profile=profile, emails=candidates)
        completion = run_openai_request(
            lambda: client.chat.completions.create(
                model=settings.openai_chat_model,
                temperature=0,
                top_p=1,
                max_completion_tokens=QA_MAX_COMPLETION_TOKENS,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": ASK_INBOX_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(payload)},
                ],
            )
        )
        raw = completion.choices[0].message.content or "{}"
        parsed = parse_qa_payload(_load_completion_payload(raw), ranked_emails=candidates)
        if parsed is None:
            raise ValueError("OpenAI returned an invalid Ask Inbox payload.")
        answer, citations, supporting = parsed
        record_ai_success()
        return QAResponse(
            answer=answer,
            answer_mode="openai_rag",
            citations=citations,
            supporting_emails=supporting,
        )
    except Exception as exc:
        logger.warning("Ask Inbox fell back to deterministic answer: %s", exc)
        fallback = _fallback_answer(query, candidates)
        record_ai_success()
        return fallback
