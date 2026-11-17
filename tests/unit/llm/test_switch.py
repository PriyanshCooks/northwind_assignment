"""Switching model is a config change: a different model string, settings and ledger file, and nothing else."""
from pathlib import Path

import pytest

from app.agents.journal_reviewer.llm_model import review_journal
from app.agents.journal_reviewer.prompts import PROMPT_VERSION
from app.agents.journal_reviewer.schema import JournalVerdict
from app.domain.runs import Context
from app.llm.factory import load_llm_config, model_settings
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
