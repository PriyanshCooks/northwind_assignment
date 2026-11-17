from pathlib import Path

import pytest
from pydantic import BaseModel
from pydantic_ai import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.llm.client import run_structured
from app.llm.factory import LlmConfig, load_llm_config, model_settings
from app.llm.ledger import Ledger, LedgerMiss, RecordedFailure, call_key


class Verdict(BaseModel):
    flag: bool
    reason: str


CFG = LlmConfig(model="ollama:test", ledger="ledger/test.jsonl", max_output_tokens=100,
                ollama_base_url="http://localhost:11434/v1", settings={"temperature": 0.0, "seed": 7})
PACKET = {"unit": "JE-006", "debits": "1200.00", "credits": "0.00"}


def scripted(*answers: str) -> tuple[FunctionModel, list[int]]:
    calls: list[int] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls.append(1)
        return ModelResponse(parts=[TextPart(answers[min(len(calls), len(answers)) - 1])])

    return FunctionModel(respond), calls


def ask(ledger: Ledger, model: FunctionModel | None, mode: str = "live", version: str = "v1") -> Verdict:
    return run_structured(CFG, ledger, agent="journal_reviewer", system_prompt="Review.", prompt_version=version,
                          packet=PACKET, schema=Verdict, mode=mode, model=model)  # type: ignore[arg-type]


def test_a_live_call_is_recorded_and_the_second_call_replays_without_the_model(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "l.jsonl")
    model, calls = scripted('{"flag": true, "reason": "unbalanced"}')
    first = ask(ledger, model)
    again = ask(Ledger(tmp_path / "l.jsonl"), model)
    assert first == again == Verdict(flag=True, reason="unbalanced")
    assert len(calls) == 1
    line = (tmp_path / "l.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(line) == 1 and '"validated": true' in line[0] and '"stop_reason"' in line[0]


def test_replay_of_a_call_that_was_never_recorded_raises_instead_of_calling_a_model(tmp_path: Path) -> None:
    with pytest.raises(LedgerMiss):
        ask(Ledger(tmp_path / "l.jsonl"), None, mode="replay")


def test_a_malformed_answer_is_recorded_as_a_failure_and_replays_as_one(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "l.jsonl")
    model, calls = scripted("not json", "still not json")
    with pytest.raises(RecordedFailure):
        ask(ledger, model)
    assert len(calls) == 2
    with pytest.raises(RecordedFailure):
        ask(Ledger(tmp_path / "l.jsonl"), None, mode="replay")


def test_a_new_prompt_version_or_model_is_a_new_call() -> None:
    base = call_key("ollama:a", {}, "v1", Verdict, PACKET)
    assert call_key("ollama:a", {}, "v2", Verdict, PACKET) != base
    assert call_key("ollama:b", {}, "v1", Verdict, PACKET) != base
    assert call_key("ollama:a", {"seed": 1}, "v1", Verdict, PACKET) != base
    assert call_key("ollama:a", {}, "v1", Verdict, {**PACKET, "unit": "JE-007"}) != base


def test_the_config_names_the_local_model_and_only_listed_settings_are_sent() -> None:
    cfg = load_llm_config()
    assert cfg.model.startswith("ollama:qwen3:4b-instruct") and cfg.ledger_path.name == "qwen3-4b-dev.jsonl"
    assert model_settings(cfg) == {"max_tokens": 400, "temperature": 0.0, "seed": 7}
    assert model_settings(CFG.model_copy(update={"settings": {}})) == {"max_tokens": 100}
