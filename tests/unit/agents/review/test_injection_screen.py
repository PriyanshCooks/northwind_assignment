"""The narrow second question about a journal's free text: its yes is proved by the lexicon or kept unverified, and a
model that says no while the rules say yes is shown as disagreeing."""
from pathlib import Path

from app.agents.injection_screen.prompts import PROMPT_VERSION as SCREEN_VERSION
from app.agents.injection_screen.schema import InjectionVerdict
from app.agents.journal_reviewer.prompts import PROMPT_VERSION
from app.agents.journal_reviewer.schema import JournalVerdict
from app.agents.review.packets import screen_packet
from app.agents.review.units import Unit, journal_units
from app.domain.runs import Context
from app.llm.factory import load_llm_config, model_settings
from app.llm.ledger import Ledger, call_key
from app.services.review_service import review_unit

QUIET = dict.fromkeys(JournalVerdict.CATEGORIES, False)


def recorded(ctx: Context, tmp_path: Path, journal: str, said: bool, main: dict[str, bool] | None = None) -> Ledger:
    cfg = load_llm_config()
    unit: Unit = next(u for u in journal_units(ctx) if u.unit_id == journal)
    ledger = Ledger(tmp_path / "l.jsonl")
    verdict = JournalVerdict(reason="x", **(main or QUIET))
    ledger.append({"key": call_key(cfg.model, model_settings(cfg), PROMPT_VERSION, JournalVerdict, unit.packet),
                   "validated": True, "response": verdict.model_dump()})
    answer = InjectionVerdict(reason="x", addressed_to_reviewer=said)
    key = call_key(cfg.model, model_settings(cfg), SCREEN_VERSION, InjectionVerdict, screen_packet(unit.packet))
    ledger.append({"key": key, "validated": True, "response": answer.model_dump()})
    return ledger


def test_the_screen_sees_only_the_free_text(ctx: Context) -> None:
    unit = next(u for u in journal_units(ctx) if u.unit_id == "JE-006")
    packet = screen_packet(unit.packet)
    assert set(packet) == {"id", "texts"} and any("AUTOMATED REVIEWERS" in t for t in packet["texts"])


def test_a_yes_on_the_memo_is_verified_because_the_wording_lexicon_agrees(ctx: Context, tmp_path: Path) -> None:
    unit = next(u for u in journal_units(ctx) if u.unit_id == "JE-006")
    result = review_unit(ctx, load_llm_config(), recorded(ctx, tmp_path, "JE-006", True), unit)
    assert "text_contains_instruction" in result.grounded.verified


def test_a_yes_on_plain_wording_is_kept_as_unverified(ctx: Context, tmp_path: Path) -> None:
    unit = next(u for u in journal_units(ctx) if u.unit_id == "JE-001")
    result = review_unit(ctx, load_llm_config(), recorded(ctx, tmp_path, "JE-001", True), unit)
    assert result.grounded.unverified == ("text_contains_instruction",) and not result.grounded.risk


def test_a_no_on_the_memo_is_shown_as_the_model_missing_it(ctx: Context, tmp_path: Path) -> None:
    unit = next(u for u in journal_units(ctx) if u.unit_id == "JE-006")
    result = review_unit(ctx, load_llm_config(), recorded(ctx, tmp_path, "JE-006", False), unit)
    assert "text_contains_instruction" in result.missed


def test_without_a_recorded_screen_the_main_verdict_stands(ctx: Context, tmp_path: Path) -> None:
    cfg = load_llm_config()
    unit = next(u for u in journal_units(ctx) if u.unit_id == "JE-006")
    ledger = Ledger(tmp_path / "l.jsonl")
    key = call_key(cfg.model, model_settings(cfg), PROMPT_VERSION, JournalVerdict, unit.packet)
    ledger.append({"key": key, "validated": True, "response": JournalVerdict(reason="x", **QUIET).model_dump()})
    result = review_unit(ctx, cfg, ledger, unit)
    assert result.source == "model" and "text_contains_instruction" not in result.missed
