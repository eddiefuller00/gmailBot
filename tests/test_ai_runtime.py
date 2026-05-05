from __future__ import annotations

from app import ai_runtime


class _RetryableError(RuntimeError):
    status_code = 503


def test_run_openai_request_retries_transient_failures(monkeypatch) -> None:
    monkeypatch.setattr(ai_runtime.time, "sleep", lambda _: None)
    attempts = {"count": 0}

    def flaky_request():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise _RetryableError("temporary outage")
        return "ok"

    result = ai_runtime.run_openai_request(flaky_request)

    assert result == "ok"
    assert attempts["count"] == 3


def test_run_openai_request_does_not_retry_non_retryable_failures(monkeypatch) -> None:
    monkeypatch.setattr(ai_runtime.time, "sleep", lambda _: None)
    attempts = {"count": 0}

    def broken_request():
        attempts["count"] += 1
        raise ValueError("bad payload")

    try:
        ai_runtime.run_openai_request(broken_request)
    except ValueError as exc:
        assert str(exc) == "bad payload"
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected ValueError to be raised")

    assert attempts["count"] == 1


def test_record_ai_error_redacts_api_key_like_values(monkeypatch) -> None:
    captured: dict[str, str | None] = {}

    monkeypatch.setattr(ai_runtime.db, "set_runtime_state", lambda key, value: captured.update({key: value}))
    monkeypatch.setattr(ai_runtime.logger, "exception", lambda *args, **kwargs: None)

    ai_runtime.record_ai_error(
        "extraction",
        RuntimeError("Incorrect API key provided: sk-proj-secretvalue123"),
    )

    assert captured["last_ai_error"] is not None
    assert "[redacted-api-key]" in str(captured["last_ai_error"])
    assert "sk-proj-secretvalue123" not in str(captured["last_ai_error"])

