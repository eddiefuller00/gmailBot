# Inbox Intelligence (AI Email Copilot)

MVP

- personalized onboarding profile
- email ingestion + preprocessing
- classification/extraction agent (OpenAI-backed with heuristic fallback)
- weighted importance scoring engine
- storage of raw + structured metadata + embeddings
- dashboard views
- natural-language inbox Q&A (RAG-style retrieval)
- smart alert generation

## Stack

- Python + FastAPI
- SQLite (local persistence)
- OpenAI API (optional for classification + embeddings)

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Service starts on `http://127.0.0.1:8000`.

## Environment Variables

- `OPENAI_API_KEY` (optional)
- `OPENAI_CHAT_MODEL` (default: `gpt-5.4-mini`)
- `OPENAI_CHAT_TEMPERATURE` (default: `0`)
- `OPENAI_CHAT_TOP_P` (default: `1`)
- `OPENAI_CHAT_MAX_TOKENS` (default: `500`)
- `OPENAI_CHAT_FREQUENCY_PENALTY` (default: `0`)
- `OPENAI_CHAT_PRESENCE_PENALTY` (default: `0`)
- `OPENAI_CHAT_SEED` (optional; enables reproducible extraction runs)
- `OPENAI_CHAT_STOP_SEQUENCES` (optional; `|`- or comma-delimited stop strings)
- `OPENAI_EMBEDDING_MODEL` (default: `text-embedding-3-small`)
- `DATABASE_PATH` (default: `data/inbox_intelligence.db`)
- `VITE_GMAIL_AUTO_SYNC_INTERVAL_MS` (frontend process env, milliseconds; min `60000`, default `300000`)

## API Quickstart

### 1) Save profile

```bash
curl -X POST http://127.0.0.1:8000/profile \
  -H "Content-Type: application/json" \
  -d '{
    "role": ["student", "job_seeker"],
    "graduating_soon": true,
    "priorities": ["jobs", "school", "events"],
    "important_senders": ["recruiters", "professors"],
    "deprioritize": ["promotions"],
    "highlight_deadlines": true
  }'
```

### 2) Ingest emails

```bash
curl -X POST http://127.0.0.1:8000/emails/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "emails": [
      {
        "external_id": "msg-1",
        "from_email": "talent@stripe.com",
        "from_name": "Stripe Recruiting",
        "subject": "Interview scheduling",
        "body": "Action required: Please confirm by April 20, 2026 at 5:00 PM.",
        "received_at": "2026-04-13T14:00:00Z",
        "unread": true
      },
      {
        "external_id": "msg-2",
        "from_email": "newsletter@shop.com",
        "from_name": "Shop",
        "subject": "Flash sale",
        "body": "Promo ends tonight.",
        "received_at": "2026-04-13T10:00:00Z",
        "unread": true
      }
    ]
  }'
```

### 3) Dashboard

```bash
curl http://127.0.0.1:8000/dashboard
```

### 4) Ask inbox questions

```bash
curl -X POST http://127.0.0.1:8000/qa \
  -H "Content-Type: application/json" \
  -d '{"query":"Do I have any interviews scheduled?"}'
```

### 5) Alerts

```bash
curl http://127.0.0.1:8000/alerts
```

## Project Layout

```text
app/
  main.py         # FastAPI routes
  service.py      # Pipeline orchestration
  preprocess.py   # Body cleanup
  extraction.py   # LLM/heuristic metadata extraction
  scoring.py      # Weighted importance scoring
  retrieval.py    # Embeddings + semantic ranking
  db.py           # SQLite persistence
  qa.py           # Intent-aware answer generation
  alerts.py       # Smart alerts
tests/
```

## Notes

- If `OPENAI_API_KEY` is missing, extraction and embeddings gracefully fall back to deterministic local logic.
- The current API is backend-first and ready to connect to React UI pages (`Onboarding`, `Dashboard`, `Chat`).
