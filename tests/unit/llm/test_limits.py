"""Call limits, retries, the stop on a bad key, the circuit breaker and key hygiene. Fake models only."""
import json
from pathlib import Path

import pytest
from pydantic import BaseModel
from pydantic_ai import ModelMessage, ModelResponse, TextPart
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.llm.client import BREAKER_LIMIT, run_structured
from app.llm.factory import LlmConfig
from app.llm.ledger import Ledger, LlmStop, LlmUnavailable

SECRET = "sk-proj-FAKEKEY1234567890abcdef"
CFG = LlmConfig(model="openai:gpt-4o-mini", ledger="ledger/test.jsonl", max_output_tokens=100,
                ollama_base_url="http://localhost:11434/v1")
GOOD = '{"flag": true, "reason": "unbalanced"}'


class Verdict(BaseModel):
    flag: bool
    reason: str


def failing(error: Exception, then: str | None = None, times: int = 99) -> tuple[FunctionModel, list[int]]:
    calls: list[int] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls.append(1)
        if then is not None and len(calls) > times:
            return ModelResponse(parts=[TextPart(then)])
        raise error

    return FunctionModel(respond), calls


def ask(ledger: Ledger, model: FunctionModel, unit: str = "JE-001", sleeps: list[float] | None = None) -> Verdict:
    waits = sleeps if sleeps is not None else []
    return run_structured(CFG, ledger, agent="journal_reviewer", system_prompt="Review.", prompt_version="v1",
                          packet={"unit": unit}, schema=Verdict, mode="live", model=model,
                          sleep=waits.append)


def http(status: int, body: object = None) -> ModelHTTPError:
    return ModelHTTPError(status, "gpt-4o-mini", body)


def test_a_recorded_unit_is_never_sent_again(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "l.jsonl")
    model, calls = failing(http(500), then=GOOD, times=0)
    ask(ledger, model)
    ask(ledger, model)
    ask(Ledger(tmp_path / "l.jsonl"), model)
    assert len(calls) == 1


def test_a_429_is_retried_twice_with_a_wait_and_then_succeeds(tmp_path: Path) -> None:
    model, calls = failing(http(429, "rate limit"), then=GOOD, times=2)
    waits: list[float] = []
    assert ask(Ledger(tmp_path / "l.jsonl"), model, sleeps=waits).flag is True
    assert len(calls) == 3 and waits == [2.0, 8.0]


def test_a_persistent_503_gives_up_after_three_attempts_and_records_nothing(tmp_path: Path) -> None:
    model, calls = failing(http(503))
    with pytest.raises(LlmUnavailable):
        ask(Ledger(tmp_path / "l.jsonl"), model)
    assert len(calls) == 3 and not (tmp_path / "l.jsonl").exists()


def test_a_timeout_is_not_retried(tmp_path: Path) -> None:
    model, calls = failing(ModelAPIError("gpt-4o-mini", "Request timed out."))
    with pytest.raises(LlmUnavailable):
        ask(Ledger(tmp_path / "l.jsonl"), model)
    assert len(calls) == 1


@pytest.mark.parametrize("error", [http(401, "bad key"), http(403, "region"),
                                   http(429, {"error": {"code": "insufficient_quota"}})])
def test_a_rejected_key_or_no_credit_stops_the_run_without_a_retry(tmp_path: Path, error: ModelHTTPError) -> None:
    model, calls = failing(error)
    with pytest.raises(LlmStop):
        ask(Ledger(tmp_path / "l.jsonl"), model)
    assert len(calls) == 1


def test_the_breaker_stops_the_batch_after_five_failures_in_a_row(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "l.jsonl")
    model, calls = failing(ModelAPIError("gpt-4o-mini", "Request timed out."))
    for n in range(BREAKER_LIMIT):
        with pytest.raises(LlmUnavailable):
            ask(ledger, model, unit=f"JE-{n}")
    with pytest.raises(LlmStop, match="circuit breaker"):
        ask(ledger, model, unit="JE-next")
    assert len(calls) == BREAKER_LIMIT


def test_one_success_resets_the_breaker(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "l.jsonl")
    bad, _ = failing(ModelAPIError("gpt-4o-mini", "Request timed out."))
    good, _ = failing(http(500), then=GOOD, times=0)
    for n in range(BREAKER_LIMIT - 1):
        with pytest.raises(LlmUnavailable):
            ask(ledger, bad, unit=f"JE-{n}")
    ask(ledger, good, unit="JE-ok")
    assert ledger.failed_in_a_row == 0


def test_a_key_in_an_error_never_reaches_the_ledger_or_the_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    ledger = Ledger(tmp_path / "l.jsonl")
    leaked = f"Incorrect API key provided: {SECRET}. Authorization: Bearer {SECRET}"
    with pytest.raises(LlmStop) as stopped:
        ask(ledger, failing(http(401, leaked))[0])
    assert SECRET not in str(stopped.value)
    bad_json, _ = failing(http(500), then=f"{SECRET} not json", times=0)
    with pytest.raises(Exception) as invalid:
        ask(ledger, bad_json, unit="JE-2")
    assert SECRET not in str(invalid.value)
    text = (tmp_path / "l.jsonl").read_text(encoding="utf-8")
    assert text and SECRET not in text and "FAKEKEY" not in json.dumps(ledger.entries)
