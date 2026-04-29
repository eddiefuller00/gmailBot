# Inbox Intelligence (AI Email Copilot)

## Design Brief
Inbox Intelligence helps a user turn a noisy inbox into a prioritized task list. The core problem is that unread email mixes high-stakes workflow items such as recruiter follow-ups and deadlines with newsletters, promotions, and generic digests, and users waste time scanning everything manually. The project uses profile-aware extraction, scoring, and grounded retrieval to decide what matters for one specific user rather than applying a generic inbox classifier.

Target user: a student or job seeker who wants a Gmail-connected assistant that highlights application updates, deadlines, recruiter emails, and other personally relevant workflow items.

Agentic pattern: **Sequential Workflow + RAG-style retrieval**.

Simple workflow:
1. Save a user onboarding profile with priorities, important senders, and categories to deprioritize.
2. Fetch Gmail or ingest emails, then preprocess and clean message bodies.
3. Run profile-aware extraction to classify each email, summarize it, and detect action/deadline signals.
4. Score the email, store structured metadata plus embeddings, and surface the results in dashboard views.
5. Answer inbox questions with grounded retrieval over stored emails and return citations to the supporting messages.

```text
Onboarding Profile
        |
        v
Gmail Fetch / Email Ingest
        |
        v
Preprocess -> Extraction -> Scoring -> Embeddings
        |                               |
        v                               v
 Dashboard / Alerts                RAG Retrieval
                                        |
                                        v
                            Grounded Ask Inbox Answer
```

## Project Requirements Mapping
- Design brief requirement: satisfied in this README under `Design Brief` and implemented across the core pipeline in `app/service.py`, `app/extraction.py`, and `app/scoring.py`.
- Sequential Workflow + RAG-style retrieval requirement: satisfied in this README under `Agentic Pattern Explanation` and in code at `app/service.py`, `app/retrieval.py`, and `app/qa.py`.
- Prompt iteration log requirement: satisfied in `docs/prompt-iteration-log.md`, with the final production prompt behavior in `app/prompting.py`.
- Personalized onboarding requirement: satisfied in `frontend/src/pages/OnboardingPage.tsx`, `app/main.py` (`/profile` routes), `app/profile_preferences.py`, `app/extraction.py`, and `app/scoring.py`.
- Demo walkthrough requirement: satisfied in this README under `Demo Walkthrough`, with UI surfaces in `frontend/src/pages/DashboardPage.tsx`, `frontend/src/pages/GmailPage.tsx`, and `frontend/src/pages/AskInboxPage.tsx`.
- Evaluation requirement: satisfied in this README under `Evaluation` and the automated suite in `tests/` plus `frontend/src/__tests__/`.
- Safety / ethics requirement: satisfied in this README under `Safety / Ethics Note`, with concrete guardrails in `app/prompting.py`, `app/extraction.py`, `app/scoring.py`, and `app/qa.py`.
- Limitations requirement: satisfied in this README under `Limitations`, with the relevant functional boundaries visible in `app/extraction.py`, `app/qa.py`, and `app/main.py`.
- Functional code path / grader usability requirement: satisfied in this README under `Run`, `Tests`, and `Quick Demo`, with the combined local startup script in `scripts/dev.sh`.

## Agentic Pattern Explanation
This system is not "one prompt" wrapped around an inbox. It is a multi-step agentic pipeline with stored state, intermediate structured outputs, deterministic ranking logic, and a separate retrieval step for grounded Q&A.

The production path is:
1. Gmail fetch or manual ingest enters through `app/main.py` and `app/service.py`.
2. Email bodies are cleaned in `app/preprocess.py`.
3. Metadata extraction runs in `app/extraction.py` using the prompt package in `app/prompting.py`.
4. Importance scoring runs in `app/scoring.py`, using both extracted metadata and the onboarding profile.
5. Embeddings are generated and stored through `app/service.py` and `app/retrieval.py`.
6. Dashboard and alert views read ranked stored rows from SQLite through `app/db.py`, `app/service.py`, and `app/alerts.py`.
7. Ask Inbox uses RAG-style retrieval in `app/retrieval.py` and grounded answer generation in `app/qa.py`, returning citations to specific emails.

## Stack
- Backend: Python, FastAPI, SQLite
- Frontend: React, Vite, TypeScript
- LLM / retrieval: OpenAI chat completions + embeddings

## Functional Code Path
Core files for graders:
- `app/main.py`: HTTP routes for profile, ingest, dashboard, alerts, Gmail, and Q&A
- `app/service.py`: orchestration for ingest, Gmail sync, dashboard assembly, profile rescoring, and QA entrypoints
- `app/preprocess.py`: body cleanup
- `app/extraction.py`: profile-aware extraction, conservative fallback, and heuristic enforcement
- `app/scoring.py`: weighted importance scoring
- `app/retrieval.py`: embedding + semantic ranking
- `app/qa.py`: grounded Ask Inbox answers with citations
- `app/db.py`: SQLite persistence
- `app/prompting.py`: system prompt, rules, few-shot examples, and payload builders
- `frontend/src/pages/DashboardPage.tsx`: ranked dashboard UI
- `frontend/src/pages/GmailPage.tsx`: Gmail browsing and sync entrypoint
- `frontend/src/pages/AskInboxPage.tsx`: grounded question-answer UI

## Run

### Backend
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Backend runs on `http://127.0.0.1:8000`.

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Frontend runs on `http://127.0.0.1:5173`.

### All-in-One Dev Script
```bash
./scripts/dev.sh
```

## Environment Variables
- `OPENAI_API_KEY`
- `OPENAI_CHAT_MODEL` (default: `gpt-5.4-mini`)
- `OPENAI_CHAT_TEMPERATURE` (default: `0`)
- `OPENAI_CHAT_TOP_P` (default: `1`)
- `OPENAI_CHAT_MAX_TOKENS` (default: `500`)
- `OPENAI_CHAT_FREQUENCY_PENALTY` (default: `0`)
- `OPENAI_CHAT_PRESENCE_PENALTY` (default: `0`)
- `OPENAI_CHAT_SEED` (optional)
- `OPENAI_CHAT_STOP_SEQUENCES` (optional)
- `OPENAI_EMBEDDING_MODEL` (default: `text-embedding-3-small`)
- `DATABASE_PATH` (default: `data/inbox_intelligence.db`)
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REDIRECT_URI`
- `TOKEN_ENCRYPTION_KEY`
- `VITE_GMAIL_AUTO_SYNC_INTERVAL_MS` (frontend process env, min `60000`, default `300000`)

## Tests
```bash
.venv/bin/python -m pytest -q
cd frontend && npm run test:run
```

## Quick Demo
One quick grader path with curl:

```bash
curl -X POST http://127.0.0.1:8000/profile \
  -H "Content-Type: application/json" \
  -d '{
    "role": ["student", "job_seeker"],
    "graduating_soon": true,
    "priorities": ["jobs", "school"],
    "important_senders": ["recruiters", "companies"],
    "deprioritize": ["promotions", "newsletters"],
    "highlight_deadlines": true
  }'

curl -X POST http://127.0.0.1:8000/emails/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "emails": [
      {
        "external_id": "demo-1",
        "from_email": "talent@stripe.com",
        "from_name": "Stripe Recruiting",
        "subject": "Interview scheduling",
        "body": "Action required: please confirm your interview slot by April 30 at 5 PM.",
        "received_at": "2026-04-28T16:00:00Z",
        "unread": true
      },
      {
        "external_id": "demo-2",
        "from_email": "promo@store.com",
        "from_name": "Store",
        "subject": "Flash sale ends tonight",
        "body": "Save 30% now. Unsubscribe below.",
        "received_at": "2026-04-28T15:00:00Z",
        "unread": true
      }
    ]
  }'

curl http://127.0.0.1:8000/dashboard | jq '.top_important_emails[0] | {subject, category: .metadata.category, importance: .metadata.importance}'

curl -X POST http://127.0.0.1:8000/qa \
  -H "Content-Type: application/json" \
  -d '{"query":"What needs my reply first?"}' | jq
```

## Demo Walkthrough
Sample end-to-end flow:

### 1. Save profile
Sample input:
```json
{
  "role": ["student", "job_seeker"],
  "priorities": ["jobs", "school"],
  "important_senders": ["recruiters", "companies"],
  "deprioritize": ["promotions", "newsletters"],
  "highlight_deadlines": true
}
```

Expected effect:
- recruiter updates and application workflow emails should outrank newsletters and promotions
- sales deadlines should not become high-priority workflow items

### 2. Sync or ingest emails
Options:
- connect Gmail in the UI and click `Backfill Unread`
- or use the curl ingest path above for a controlled demo

Sample inbox inputs:
- `Interview scheduling` from a recruiter with a reply deadline
- `Flash sale ends tonight` from a marketing sender

Expected result:
- the recruiter email is classified as `job`, action-required, and high importance
- the promotion is classified as `promotion`, bulk, and low importance

### 3. Show dashboard result
Sample output:
```json
{
  "subject": "Interview scheduling",
  "category": "job",
  "importance": 9.3,
  "action_required": true,
  "summary": "Recruiter asks the user to confirm an interview slot by April 30 at 5 PM."
}
```

Suggested screenshot for submission if you want one:
- Dashboard page showing `Top Priorities`, `Smart Alerts`, and the Gmail-connected sync controls

### 4. Ask an inbox question
Sample question:
```json
{"query": "What needs my reply first?"}
```

Sample output:
```json
{
  "answer": "Interview scheduling needs your reply first because the recruiter asks you to confirm a slot by April 30 at 5 PM.",
  "citations": ["demo-1"]
}
```

Suggested screenshot for submission if you want one:
- Ask Inbox page showing the grounded answer plus cited supporting emails

## Evaluation
Testing used both automated regression tests and live manual runs against the local UI/API.

Automated coverage summary:
- Backend: `46` tests in `tests/`
- Frontend: `10` tests in `frontend/src/__tests__/`

Representative cases covered:
- recruiter email vs. generic job digest: `tests/test_extraction.py`, `tests/test_scoring.py`
- urgent promotion vs. real deadline: `tests/test_scoring.py`, `tests/test_alerts.py`, `tests/test_dashboard_service.py`
- grounded Q&A with citations: `tests/test_qa.py`
- Gmail sync and Gmail-backed persistence behavior: `tests/test_service_sync.py`
- dashboard display behavior and expansion controls: `frontend/src/__tests__/DashboardPage.test.tsx`

Manual validation highlights:
- connected Gmail sync and unread backfill
- dashboard ranking after onboarding changes
- Ask Inbox grounded answers over stored inbox data
- filtering/removal of legacy sample rows once Gmail is connected

## Safety / Ethics Note
- Privacy risk from Gmail data: the app stores raw email text, structured metadata, and embeddings locally in SQLite. A real deployment would need stronger secrets management, access control, and retention policies.
- False positives / false urgency: an LLM can overreact to marketing language or article headlines if prompts and scoring are weak. The system now counters this with profile-aware prompting and conservative scoring rules.
- Personalization bias from user profile: onboarding choices shape what is considered important, which can hide useful but non-priority messages or overweight a user's stated interests.
- Incomplete prompt-injection protection: the app does not yet have a full adversarial content sanitization layer for email bodies before LLM processing.

Actual guardrails already present:
- conservative classification when uncertain: the prompt explicitly says to choose the conservative category and lower confidence
- bulk / no-reply suppression: extraction and scoring downrank automated, no-reply, digest, and promotion-style messages
- grounded answers with citations: Ask Inbox returns cited email ids rather than freeform unsupported claims

## Limitations
- OpenAI dependency for ranking and Q&A: the strongest extraction and retrieval experience depends on OpenAI services.
- No full prompt-injection defense layer: email content can still contain adversarial instructions that are not fully sandboxed semantically.
- No autonomous email sending: the system reads, ranks, and answers, but it does not safely send email on the user's behalf.
- Possible misclassification on ambiguous emails: mixed-purpose updates, vague subject lines, or incomplete bodies can still be scored imperfectly.

## Prompt Iteration Log
See `docs/prompt-iteration-log.md` for the initial prompt, failure mode, and final prompt strategy.
