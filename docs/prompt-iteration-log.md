# Prompt Iteration Log

## Purpose
This document records how the inbox extraction prompt evolved from an earlier generic classifier into the current profile-aware prompt package used by `app/prompting.py`.

The final system behavior is not just one system prompt string. It is the combination of:
- `EMAIL_EXTRACTION_SYSTEM_PROMPT`
- `EMAIL_EXTRACTION_RULES`
- `EMAIL_EXTRACTION_OUTPUT_SCHEMA`
- `EMAIL_EXTRACTION_FEW_SHOTS`
- `build_extraction_user_payload(...)`, which injects the user's onboarding profile and normalized profile policy

## Iteration 1: Initial Prompt
Source: initial committed version of `app/prompting.py` from commit `82e9f95`.

Initial system prompt:

```text
You are an inbox ranking analyst. Classify each email for personal relevance using the user's onboarding profile. Do not inflate urgency for bulk promotions/newsletters. Follow the required schema exactly and output strict JSON only.
```

Initial prompt characteristics:
- profile-aware in a basic sense
- conservative about bulk promotions
- structured JSON output
- a few examples for obvious recruiter vs. promotion cases

## Failure It Caused
This initial strategy was directionally correct but not explicit enough for real Gmail traffic. In practice, the system could still overvalue broad job digests, content roundups, or promotional emails that used urgent language.

Observed failure pattern:
- generic urgency words such as "last chance", "deadline", or "today" could still leak into high-priority scoring
- content digests and mass recommendations could be mistaken for user-critical job workflow
- early outputs did not require `confidence`, `is_bulk`, or `action_channel`, which reduced downstream scoring precision
- dashboard cards could show priorities that matched broad job-search language but not the user's actual candidacy workflow

Representative failure examples later captured in tests:
- recruiter email vs. job digest: `tests/test_extraction.py`, `tests/test_scoring.py`
- urgent promotion vs. real deadline: `tests/test_scoring.py`, `tests/test_alerts.py`
- noisy dashboard priorities: `tests/test_dashboard_service.py`

## Before / After Prompt Example

### Before
This is the original committed system prompt:

```text
You are an inbox ranking analyst. Classify each email for personal relevance using the user's onboarding profile. Do not inflate urgency for bulk promotions/newsletters. Follow the required schema exactly and output strict JSON only.
```

Why it was weaker:
- it did not explicitly force the model to ground decisions in sender, subject, and body evidence
- it did not explicitly say onboarding priorities should outrank generic urgency and recency
- it did not explicitly call out article headlines, shopping offers, and mass digests as non-priority by default

### After
This reflects the current production strategy in `app/prompting.py`.

Current system prompt:

```text
You are an inbox ranking analyst for a single user. Classify each email using the onboarding profile, extract the action channel, estimate confidence, and separate high-signal personal workflow from bulk automation. Base every decision on explicit evidence from the sender, subject, and body. Output strict JSON only.
```

Current high-impact rules:

```text
- Use the user's onboarding priorities as the primary ranking lens before generic urgency or recency.
- Base the category, action_required flag, and reason on concrete sender, subject, and body evidence, not on generic marketing phrasing alone.
- Only classify as 'job' when the email is directly about the user's candidacy, application, interview, assessment, offer, recruiter follow-up, or employer workflow.
- Do not treat article headlines, shopping offers, mass recommendations, or entertainment/news digests as user priorities unless the onboarding profile explicitly prioritizes them.
- Do not elevate sale end dates, coupon expirations, or promotional deadlines into high-priority workflow items.
- If uncertain, choose the conservative category and lower confidence.
```

## Final Prompt Strategy
The final strategy is intentionally layered.

1. The system prompt sets the role and requires sender/subject/body-grounded reasoning.
2. Rules explicitly define what counts as real job workflow, what counts as bulk content, and how onboarding priorities must dominate generic urgency.
3. The output schema enforces structured fields used later by the scoring engine.
4. Few-shot examples include both positive cases (real recruiter workflow) and negative cases (job digests, entertainment/news digests, promotions).
5. The user payload injects normalized profile policy so the LLM sees both raw onboarding responses and canonical priority/deprioritize categories.

## Techniques Used
- Structured outputs: `EMAIL_EXTRACTION_OUTPUT_SCHEMA` forces predictable JSON fields for category, action flags, dates, confidence, bulk flag, and action channel.
- Few-shot examples: `EMAIL_EXTRACTION_FEW_SHOTS` shows the intended boundary between real workflow and noisy bulk messages.
- Profile-aware prompting: `build_extraction_user_payload(...)` passes `profile` and `profile_policy` so the model reasons about one specific user's priorities.
- Conservative fallback: the prompt says to choose a conservative category when uncertain, and `app/extraction.py` also contains heuristic/profile constraint logic that reclassifies suspicious marketing-style false positives.

## Why the Final Strategy Is Better
The final prompt package is better aligned with the rest of the system because it produces signals that the downstream scorer can trust:
- `confidence`
- `is_bulk`
- `action_channel`
- cleaner `reason` strings tied to user goals
- more robust separation between real recruiter workflow and generic inbox noise

That improved behavior is reinforced by deterministic safeguards in:
- `app/extraction.py`
- `app/scoring.py`
- `app/alerts.py`

So the production system is best understood as prompt strategy plus deterministic post-processing, not prompt strategy alone.
