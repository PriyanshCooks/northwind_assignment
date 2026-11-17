from pathlib import Path

from app.config import load_assumptions, load_overrides
from app.services.run_service import build_context, stage
from app.utils.paths import CONFIG_DIR, DEFAULT_DATA_DIR


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
