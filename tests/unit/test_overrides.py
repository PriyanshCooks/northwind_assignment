from pathlib import Path

from app.config import load_assumptions, load_overrides
from app.detectors.registry import run_all
from app.domain.runs import Context
from app.services.overrides_service import approve, override_states, reject, review_queue
from app.services.run_service import build_context, stage
from app.utils.paths import CONFIG_DIR, DEFAULT_DATA_DIR
from tests.conftest import Edit

OVERRIDES = CONFIG_DIR / "overrides.toml"
MAP_ROW = ("2310,Deferred income,4100", "2310,Deferred income,4000")


def test_the_uk_2310_remap_comes_from_the_override_file_not_the_assumptions() -> None:
    assert load_assumptions(CONFIG_DIR / "assumptions.toml")["map_uk_2310"] == "none"
    rows = load_overrides(CONFIG_DIR / "overrides.toml")
    assert [(r.target, r.to, r.status) for r in rows] == [("mapping:UK:2310", "2300", "approved")]
    assert rows[0].approver == "Priyansh (user)"
    assert rows[0].effect_if_reversed


def test_reversing_the_override_leaves_uk_2310_in_revenue(tmp_path: Path) -> None:
    for name in ("policy.toml", "assumptions.toml"):
        (tmp_path / name).write_text((CONFIG_DIR / name).read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "overrides.toml").write_text("", encoding="utf-8")
    ctx = build_context(DEFAULT_DATA_DIR, tmp_path)
    assert ctx.assumptions["map_uk_2310"] == "none"
    assert build_context(DEFAULT_DATA_DIR).assumptions["map_uk_2310"] == "remap_2300"
    reversed_run = stage(ctx)
    line = next(m for m in reversed_run.mapped if (m.line.entity, m.line.local_code) == ("UK", "2310"))
    assert (line.verdict, line.group_code) == ("SUSPECT", "4100")
    remapped = next(m for m in stage(build_context(DEFAULT_DATA_DIR)).mapped
                    if (m.line.entity, m.line.local_code) == ("UK", "2310"))
    assert (remapped.verdict, remapped.group_code) == ("REMAPPED", "2300")


def _config_copy(tmp_path: Path) -> Path:
    for name in ("policy.toml", "assumptions.toml", "overrides.toml"):
        (tmp_path / name).write_text((CONFIG_DIR / name).read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path


def test_a_changed_mapping_row_makes_the_decision_stale(edited_context: Edit) -> None:
    ctx = edited_context("map_uk.csv", *MAP_ROW)
    assert ctx.assumptions["map_uk_2310"] == "none"
    assert [s.state for s in override_states(load_overrides(OVERRIDES), ctx.inputs)] == ["stale"]


def test_a_changed_trial_balance_row_makes_the_decision_stale(edited_context: Edit) -> None:
    ctx = edited_context("tb_uk.csv", "2310,Deferred income,,GBP,,-180000.00", "2310,Deferred income,,GBP,,-181000.00")
    assert [s.state for s in override_states(load_overrides(OVERRIDES), ctx.inputs)] == ["stale"]


def test_a_stale_override_is_back_in_the_review_queue(edited_context: Edit) -> None:
    ctx = edited_context("map_uk.csv", *MAP_ROW)
    queue = review_queue(run_all(ctx), override_states(load_overrides(OVERRIDES), ctx.inputs))
    assert (queue[0]["kind"], queue[0]["key"], queue[0]["state"]) == ("override", "mapping:UK:2310", "stale")


def test_an_approved_override_on_unchanged_evidence_is_not_queued(ctx: Context) -> None:
    states = override_states(load_overrides(OVERRIDES), ctx.inputs)
    queue = review_queue(run_all(ctx), states)
    assert [s.state for s in states] == ["applied"]
    assert not [q for q in queue if q["kind"] == "override" or q["key"].startswith("D02")]
    assert "D03:adjustments.json:102:balance" in {q["key"] for q in queue}


def test_approving_signs_the_current_evidence(tmp_path: Path, ctx: Context) -> None:
    path = _config_copy(tmp_path) / "overrides.toml"
    text = path.read_text(encoding="utf-8").replace('status = "approved"', 'status = "open"')
    path.write_text(text.replace("Priyansh (user)", "pending"), encoding="utf-8")
    assert override_states(load_overrides(path), ctx.inputs)[0].state == "open"
    approve(path, ctx.inputs, "mapping:UK:2310", "A. Reviewer")
    row = load_overrides(path)[0]
    assert (row.status, row.approver) == ("approved", "A. Reviewer")
    assert override_states([row], ctx.inputs)[0].state == "applied"


def test_a_rejected_override_does_not_remap(tmp_path: Path) -> None:
    config = _config_copy(tmp_path)
    reject(config / "overrides.toml", "mapping:UK:2310", "A. Reviewer")
    assert build_context(DEFAULT_DATA_DIR, config).assumptions["map_uk_2310"] == "none"
