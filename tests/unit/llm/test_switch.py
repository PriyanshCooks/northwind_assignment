"""Switching model is a config change: a different model string, settings and ledger file, and nothing else."""
from pathlib import Path

import pytest

from app.agents.journal_reviewer.llm_model import review_journal
from app.agents.journal_reviewer.prompts import PROMPT_VERSION
from app.agents.journal_reviewer.schema import JournalVerdict
from app.domain.runs import Context
from app.llm.factory import LlmConfig, load_llm_config, model_settings
from app.llm.ledger import Ledger, LedgerMiss, call_key
from app.review.units import journal_units
from app.services.review_service import review_all, review_unit
from app.services.run_service import stage
from app.utils.hashing import json_hash

CLOUD = """[llm]
model = "openai:gpt-6-luna"
ledger = "ledger/gpt-6-luna.jsonl"
max_output_tokens = 400
ollama_base_url = "http://localhost:11434/v1"

[llm.settings]
"""


def test_a_cloud_config_sends_no_sampling_settings_and_has_its_own_ledger(tmp_path: Path) -> None:
    path = tmp_path / "llm.toml"
    path.write_text(CLOUD, encoding="utf-8")
    cfg = load_llm_config(path)
    assert cfg.model == "openai:gpt-6-luna" and cfg.ledger_path.name == "gpt-6-luna.jsonl"
    assert model_settings(cfg) == {"max_tokens": 400}


def test_the_same_packet_has_a_different_key_for_each_model(ctx: Context, tmp_path: Path) -> None:
    packet = journal_units(ctx)[0].packet
    local = load_llm_config()
    path = tmp_path / "llm.toml"
    path.write_text(CLOUD, encoding="utf-8")
    cloud = load_llm_config(path)
    keys = {call_key(c.model, model_settings(c), PROMPT_VERSION, JournalVerdict, packet) for c in (local, cloud)}
    assert len(keys) == 2


def test_the_local_ledger_cannot_answer_for_a_cloud_model(ctx: Context, tmp_path: Path) -> None:
    path = tmp_path / "llm.toml"
    path.write_text(CLOUD, encoding="utf-8")
    cloud = load_llm_config(path)
    local_ledger = Ledger(load_llm_config().ledger_path)
    unit = journal_units(ctx)[0]
    result = review_unit(ctx, cloud, local_ledger, unit)
    assert result.source == "rules" and "no recorded answer" in result.note
    with pytest.raises(LedgerMiss):
        review_journal(cloud, local_ledger, unit.packet)


def test_running_the_reviewers_changes_no_figure(ctx: Context) -> None:
    before = json_hash({k: f.model_dump(mode="json") for k, f in stage(ctx).figures.items()})
    review_all(ctx, load_llm_config(), Ledger(load_llm_config().ledger_path))
    assert json_hash({k: f.model_dump(mode="json") for k, f in stage(ctx).figures.items()}) == before


def test_northwind_model_alone_switches_the_model_and_nothing_else(monkeypatch: pytest.MonkeyPatch) -> None:
    local = load_llm_config()
    monkeypatch.setenv("NORTHWIND_MODEL", "openai:gpt-4o-mini")
    cloud = load_llm_config()
    assert (cloud.model, cloud.ledger) == ("openai:gpt-4o-mini", "ledger/openai-gpt-4o-mini.jsonl")
    assert model_settings(cloud) == {"max_tokens": local.max_output_tokens}
    same = {"max_output_tokens", "ollama_base_url", "request_timeout_s"}
    assert cloud.model_dump(include=same) == local.model_dump(include=same)
    assert cloud.ledger_path != local.ledger_path


def _hostile_cloud_ledger(ctx: Context, cfg: LlmConfig, path: Path) -> Ledger:
    """A fake recording that flags every category on every journal, to prove advice cannot move a number."""
    ledger = Ledger(path)
    answer = {name: True for name in JournalVerdict.CATEGORIES} | {"reason": "everything is wrong"}
    for unit in journal_units(ctx):
        key = call_key(cfg.model, model_settings(cfg), PROMPT_VERSION, JournalVerdict, unit.packet)
        ledger.append({"key": key, "agent": "journal_reviewer", "model": cfg.model, "validated": True,
                       "response": answer, "packet": unit.packet})
    return ledger


def _outcome(ctx: Context) -> str:
    run = stage(ctx)
    return json_hash({"figures": {k: f.model_dump(mode="json") for k, f in run.figures.items()},
                      "dispositions": [d.model_dump(mode="json") for d in run.dispositions],
                      "findings": [f.model_dump(mode="json") for f in run.findings]})


def test_figures_dispositions_and_findings_are_identical_with_a_local_ledger_a_cloud_ledger_and_no_model(
    ctx: Context, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _outcome(ctx)
    local = load_llm_config()
    review_all(ctx, local, Ledger(local.ledger_path))
    assert _outcome(ctx) == baseline
    monkeypatch.setenv("NORTHWIND_MODEL", "openai:gpt-4o-mini")
    cloud = load_llm_config()
    flagged = review_all(ctx, cloud, _hostile_cloud_ledger(ctx, cloud, tmp_path / "cloud.jsonl"))
    assert any(r.source == "model" for r in flagged)
    assert _outcome(ctx) == baseline
    review_all(ctx, cloud, Ledger(tmp_path / "empty.jsonl"))
    assert _outcome(ctx) == baseline


def test_the_recorded_cloud_answers_leave_figures_dispositions_and_findings_unchanged(
    ctx: Context, monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = _outcome(ctx)
    monkeypatch.setenv("NORTHWIND_MODEL", "openai:gpt-4o-mini")
    cloud = load_llm_config()
    results = review_all(ctx, cloud, Ledger(cloud.ledger_path))
    assert len(results) == 63 and {r.source for r in results} == {"model"}
    assert _outcome(ctx) == baseline
