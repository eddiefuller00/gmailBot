from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ValidationError

from app.ai_runtime import get_openai_client, raise_ai_processing_error, record_ai_success, run_openai_request
from app.config import settings
from app.prompting import ASK_INBOX_SYSTEM_PROMPT, build_qa_user_payload
from app.schemas import ProcessedEmail, QAResponse, UserProfile


QA_MAX_COMPLETION_TOKENS = 260


class QACompletionPayload(BaseModel):
    answer: str
    citations: list[str]


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
        parsed = parse_qa_payload(json.loads(raw), ranked_emails=candidates)
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
        raise_ai_processing_error("answer generation", exc)
