from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel
from pydantic_ai import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.llm.client import run_structured
from app.llm.cost import build_report, cost_fields, format_report, load_prices
from app.llm.factory import LlmConfig
from app.llm.ledger import Ledger

CFG = LlmConfig(model="openai:gpt-4o-mini", ledger="ledger/x.jsonl", max_output_tokens=100,
                ollama_base_url="http://localhost:11434/v1")


class Verdict(BaseModel):
    flag: bool


def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    return ModelResponse(parts=[TextPart('{"flag": true}')])


def ask(ledger: Ledger, mode: str = "live") -> None:
    run_structured(CFG, ledger, agent="journal_reviewer", system_prompt="Review.", prompt_version="v1",
                   packet={"unit": "JE-1"}, schema=Verdict, mode=mode, model=FunctionModel(respond))  # type: ignore[arg-type]


def test_the_cost_of_a_call_uses_the_price_per_million_tokens() -> None:
    got = cost_fields("openai:gpt-4o-mini", {"input_tokens": 2_000_000, "output_tokens": 1_000_000})
    assert got["cost_usd"] == "0.900000"
    assert "ASSUMED" in got["cost_note"]


def test_an_unknown_model_has_a_null_cost_with_a_reason() -> None:
    got = cost_fields("openai:gpt-future", {"input_tokens": 10, "output_tokens": 10})
    assert got["cost_usd"] is None and "no price for openai:gpt-future" in got["cost_note"]


def test_the_price_file_names_a_source_and_a_date_and_stays_assumed_until_checked() -> None:
    row = load_prices()["openai:gpt-4o-mini"]
    assert row["source"].startswith("https://") and row["date_read"] == "2026-11-18" and row["status"] == "ASSUMED"


def test_a_recorded_call_carries_its_tokens_and_cost_and_a_replay_adds_no_new_cost(tmp_path: Path) -> None:
    path = tmp_path / "l.jsonl"
    first = Ledger(path)
    ask(first)
    entry = first.entries[next(iter(first.new_keys))]
    assert entry["cost_usd"] is not None and entry["usage"]["input_tokens"] > 0
    live = build_report([first.entries[k] for k in first.used], first.new_keys)
    again = Ledger(path)
    ask(again, "replay")
    replayed = build_report([again.entries[k] for k in again.used], again.new_keys)
    assert replayed.total().new_cost == Decimal(0) and replayed.total().new_calls == 0
    assert replayed.total().recorded_cost == live.total().recorded_cost > 0
    assert "new cost this run $0" in format_report(replayed, CFG.model)[-1]
