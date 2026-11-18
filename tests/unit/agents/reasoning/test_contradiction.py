"""A claim the code can check and finds false is dropped as contradicted, one kind of check at a time."""
from decimal import Decimal
from pathlib import Path

import pytest

from app.agents.reasoning.calc_review import review_calculations
from app.agents.reasoning.evidence import Evidence
from app.agents.reasoning.grounding import ground_line_claims
from app.agents.reasoning.schema import LineClaim
from app.domain.runs import Context
from app.llm.ledger import Ledger
from app.services.reasoning_service import build_evidence
from app.services.run_service import stage
from app.utils.paths import DEFAULT_DATA_DIR
from tests.unit.agents.reasoning.fakes import CFG, scripted

FILES = frozenset(p.name for p in DEFAULT_DATA_DIR.iterdir() if p.is_file())


@pytest.fixture(scope="module")
def real(ctx: Context) -> Evidence:
    return build_evidence(stage(ctx))


def ground(evidence: Evidence, file: str, number: int, flag: str, quoted: list[str]) -> tuple[list, list]:
    text = evidence.lines(file)[number - 1]
    claim = LineClaim(cite=f"{file}:{number}", flag=flag, reason="looks wrong", quoted=quoted)  # type: ignore[arg-type]
    return ground_line_claims([claim], file, text, evidence)


def test_a_date_claim_on_a_valid_date_is_contradicted(real: Evidence) -> None:
    kept, dropped = ground(real, "fx_rates.csv", 2, "value_not_plausible", ["2023-12-31"])
    assert not kept and dropped[0].why.startswith("contradicted") and "valid date" in dropped[0].why


def test_a_rate_claim_on_a_rate_inside_the_tolerance_is_contradicted(real: Evidence) -> None:
    assert real.rate_gaps["fx_rates.csv:11"] <= real.rate_tolerance
    kept, dropped = ground(real, "fx_rates.csv", 11, "inconsistent_with_neighbours", ["85.62"])
    assert not kept and "tolerance" in dropped[0].why


def test_a_rate_claim_on_a_rate_outside_the_tolerance_stays(real: Evidence) -> None:
    far = Evidence(data_dir=real.data_dir, files=real.files, rate_gaps={"fx_rates.csv:11": Decimal(99)})
    kept, _ = ground(far, "fx_rates.csv", 11, "unit_or_direction_suspect", ["85.62"])
    assert [k.tier for k in kept] == ["suspicion"]


def test_a_nature_claim_on_a_name_that_matches_its_account_is_contradicted(real: Evidence) -> None:
    line = next(c for c in sorted(real.nature_agrees) if c.startswith("map_uk"))
    kept, dropped = ground(real, "map_uk.csv", int(line.split(":")[1]), "nature_mismatch", [])
    assert not kept and "same nature" in dropped[0].why


def test_the_real_nature_mismatch_is_not_in_the_agreeing_set(real: Evidence) -> None:
    assert "map_uk.csv:12" not in real.nature_agrees
    kept, _ = ground(real, "map_uk.csv", 12, "nature_mismatch", [])
    assert len(kept) == 1


def test_a_missing_name_claim_on_a_line_with_a_name_is_contradicted(real: Evidence) -> None:
    kept, dropped = ground(real, "tb_uk.csv", 2, "no_valid_name", ["Bank - Barclays GBP"])
    assert not kept and dropped[0].why == "contradicted: the line has a name"


def test_a_sign_concern_on_a_positive_total_is_contradicted(real: Evidence, tmp_path: Path) -> None:
    assert real.results["fig:total_assets"] > 0
    claim = {"cite": "fig:total_assets", "concern": "sign_implausible", "reason": "looks wrong", "quoted": []}
    model, _ = scripted(lambda p: {"claims": [claim] if p["calculation_id"] == "fig:total_assets" else []})
    report = review_calculations(CFG, Ledger(tmp_path / "l.jsonl"), real, "live", model)
    assert not report.findings and report.dropped[0].why == "contradicted: the result is not negative"
