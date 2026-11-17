"""Checkpoint 1 with a fake model: every line is read, claims are grounded, the two tiers are kept apart."""
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from app.llm.ledger import Ledger, LlmStop
from app.reasoning.evidence import Evidence
from app.reasoning.reader import CHUNK, chunk_packets, read_inputs
from app.reasoning.schema import CalcReview, InputReading, Investigation
from app.utils.paths import DEFAULT_DATA_DIR
from tests.unit.reasoning.fakes import CFG, scripted

FILES = frozenset(p.name for p in DEFAULT_DATA_DIR.iterdir() if p.is_file())
LINE = "map_uk.csv:12"  # UK 2310 Deferred income, mapped to a revenue account


def evidence(confirmed: bool = False, data_dir: Path = DEFAULT_DATA_DIR, files: frozenset[str] = FILES) -> Evidence:
    return Evidence(data_dir=data_dir, files=files,
                    confirmed={"nature_mismatch": frozenset({LINE})} if confirmed else {})


def claim(cite: str, flag: str = "nature_mismatch", reason: str = "looks wrong",
          quoted: list[str] | None = None) -> dict[str, Any]:
    return {"cite": cite, "flag": flag, "reason": reason, "quoted": quoted or []}


def only_in(file: str, *claims: dict[str, Any]) -> Any:
    """Answer the first chunk of one file with these claims and every other chunk with none."""
    return lambda p: {"claims": list(claims) if p["file"] == file and p["lines"][0]["line"].endswith(":1") else []}


def test_every_line_of_every_file_is_shown_exactly_once() -> None:
    for file in sorted(FILES):
        shown = []
        for packet, _ in chunk_packets(evidence(), file):
            context = packet["context_line_numbers_before"]
            shown += [x["line"] for x in packet["lines"] if int(x["line"].rsplit(":", 1)[1]) not in context]  # type: ignore[attr-defined]
        total = len(evidence().lines(file))
        assert shown == [f"{file}:{n}" for n in range(1, total + 1)], file


def test_a_file_longer_than_a_chunk_is_split() -> None:
    assert len(chunk_packets(evidence(), "adjustments.json")) == -(-388 // CHUNK)


def test_each_packet_carries_the_plain_meaning_of_its_file() -> None:
    packet, _ = chunk_packets(evidence(), "map_uk.csv")[0]
    assert "Maps each UK nominal code" in str(packet["meaning"])


def test_a_claim_the_rules_confirm_is_verified_and_one_they_do_not_is_suspicion(tmp_path: Path) -> None:
    model, _ = scripted(only_in("map_uk.csv", claim(LINE)))
    first = read_inputs(CFG, Ledger(tmp_path / "a.jsonl"), evidence(True), "live", model)
    model, _ = scripted(only_in("map_uk.csv", claim(LINE)))
    second = read_inputs(CFG, Ledger(tmp_path / "b.jsonl"), evidence(False), "live", model)
    assert [f.tier for f in first.findings] == ["verified"] and [f.tier for f in second.findings] == ["suspicion"]


def test_a_cited_line_that_does_not_exist_is_dropped(tmp_path: Path) -> None:
    model, _ = scripted(only_in("map_uk.csv", claim("map_uk.csv:999"), claim("tb_uk.csv:3")))
    report = read_inputs(CFG, Ledger(tmp_path / "a.jsonl"), evidence(), "live", model)
    assert report.findings == []
    assert [d.why for d in report.dropped] == ["the cited line does not exist in this file"] * 2


def test_a_quoted_number_that_is_not_in_the_evidence_is_dropped(tmp_path: Path) -> None:
    model, _ = scripted(only_in("map_uk.csv", claim(LINE, quoted=["999999"]), claim(LINE, reason="balance is 123456")))
    report = read_inputs(CFG, Ledger(tmp_path / "a.jsonl"), evidence(), "live", model)
    assert report.findings == [] and len(report.dropped) == 2


def test_an_invalid_date_is_verified_by_code_without_any_rule(tmp_path: Path) -> None:
    (tmp_path / "fx_rates.csv").write_text("a,b\nGBP,USD,closing,1.2,00.02.2222,USD per 1 GBP\n", encoding="utf-8")
    ev = evidence(data_dir=tmp_path, files=frozenset({"fx_rates.csv"}))
    model, _ = scripted(lambda p: {"claims": [claim("fx_rates.csv:2", "value_not_plausible", "no such date")]})
    report = read_inputs(CFG, Ledger(tmp_path / "a.jsonl"), ev, "live", model)
    assert [(f.cite, f.tier) for f in report.findings] == [("fx_rates.csv:2", "verified")]


def test_one_chunk_the_model_cannot_answer_is_reported_and_the_rest_goes_on(tmp_path: Path) -> None:
    answers = iter(["not json", "not json"])  # the first chunk fails twice (one retry), every later chunk is empty

    def respond(messages: Any, info: Any) -> ModelResponse:
        return ModelResponse(parts=[TextPart(next(answers, '{"claims": []}'))])

    report = read_inputs(CFG, Ledger(tmp_path / "a.jsonl"), evidence(), "live", FunctionModel(respond))
    assert len(report.unavailable) == 1 and report.findings == []


def test_five_failures_in_a_row_stop_the_run(tmp_path: Path) -> None:
    broken = FunctionModel(lambda m, i: ModelResponse(parts=[TextPart("not json")]))
    with pytest.raises(LlmStop, match="circuit breaker"):
        read_inputs(CFG, Ledger(tmp_path / "a.jsonl"), evidence(), "live", broken)


def test_replay_answers_every_chunk_from_the_ledger_with_no_model(tmp_path: Path) -> None:
    model, asked = scripted(only_in("map_uk.csv", claim(LINE)))
    first = read_inputs(CFG, Ledger(tmp_path / "a.jsonl"), evidence(True), "live", model)
    calls = len(asked)
    again = read_inputs(CFG, Ledger(tmp_path / "a.jsonl"), evidence(True), "replay")
    assert again.findings == first.findings and len(asked) == calls


def test_no_output_schema_has_a_number_field() -> None:
    def types(node: Any) -> set[str]:
        found: set[str] = set()
        if isinstance(node, dict):
            found |= {node["type"]} if isinstance(node.get("type"), str) else set()
            for value in node.values():
                found |= types(value)
        elif isinstance(node, list):
            for value in node:
                found |= types(value)
        return found

    for schema in (InputReading, CalcReview, Investigation):
        assert not types(schema.model_json_schema()) & {"number", "integer"}, schema.__name__


@pytest.mark.parametrize("flag", ["approve", "post_journal", "set_rate"])
def test_a_flag_outside_the_menu_is_rejected(flag: str) -> None:
    with pytest.raises(ValueError):
        InputReading.model_validate({"claims": [claim("map_uk.csv:1", flag)]})
