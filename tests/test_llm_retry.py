"""_run_llm: transient provider errors retry with backoff instead of killing
the self-heal loop (gemini-2.5-flash 503 UNAVAILABLE mid-heal died at
attempt 1 with the ADF failure unhealed)."""

import time

import pytest
from pydantic_ai.exceptions import ModelHTTPError

from agent.validator import _run_llm


class _FlakyAgent:
    def __init__(self, failures: int, status: int = 503):
        self.failures = failures
        self.status = status
        self.calls = 0

    def run_sync(self, msg: str) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise ModelHTTPError(
                status_code=self.status,
                model_name="gemini-2.5-flash",
                body={"error": {"code": self.status, "status": "UNAVAILABLE"}},
            )
        return "ok"


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda s: None)


def test_transient_503_retried():
    agent = _FlakyAgent(failures=2)
    assert _run_llm(agent, "msg") == "ok"
    assert agent.calls == 3


def test_gives_up_after_cap():
    agent = _FlakyAgent(failures=99)
    with pytest.raises(ModelHTTPError):
        _run_llm(agent, "msg")
    assert agent.calls == 3


def test_non_transient_not_retried():
    agent = _FlakyAgent(failures=99, status=401)
    with pytest.raises(ModelHTTPError):
        _run_llm(agent, "msg")
    assert agent.calls == 1
