import shutil
from decimal import Decimal
from pathlib import Path

from app.domain.figures import Unknown
from app.domain.runs import Context
from app.services.run_service import build_context, stage
from app.utils.money import round2
from app.utils.paths import CONFIG_DIR, DEFAULT_DATA_DIR
from tests.conftest import Edit


def edited_policy(tmp_path: Path, old: str, new: str) -> Context:
    config = tmp_path / "config"
    shutil.copytree(CONFIG_DIR, config)
    text = (config / "policy.toml").read_text(encoding="utf-8")
    assert old in text
    (config / "policy.toml").write_text(text.replace(old, new), encoding="utf-8")
    return build_context(DEFAULT_DATA_DIR, config)


def test_the_supplied_policy_text_matches_its_approved_hash(ctx: Context) -> None:
    assert stage(ctx).blocked is None


def test_changing_the_policy_file_without_re_approval_blocks_the_run(edited_context: Edit) -> None:
    run = stage(edited_context("group_policies.md", "Translate at full precision", "Translate at 4 decimals"))
    assert run.blocked is not None and "approve it again" in run.blocked
    assert all(isinstance(f, Unknown) for f in run.figures.values())


def test_the_run_still_finishes_and_lists_its_findings_when_blocked(edited_context: Edit) -> None:
    run = stage(edited_context("group_policies.md", "Translate at full precision", "Translate at 4 decimals"))
    assert run.findings


def test_editing_one_policy_line_changes_the_output(tmp_path: Path) -> None:
    old = 'difference_account = "7300"\n\n[business_combination]'
    ctx = edited_policy(tmp_path, old, old.replace("7300", "6500"))
    base = stage(build_context(DEFAULT_DATA_DIR))
    assert round2(stage(ctx).balances["6500"] - base.balances["6500"]) == Decimal("11957.88")


def test_the_residual_account_for_intercompany_income_is_read_from_the_policy(tmp_path: Path) -> None:
    ctx = edited_policy(tmp_path, 'residual_account = "7300"', 'residual_account = "6500"')
    income = next(e for e in stage(ctx).eliminations if e.id == "ELIM-IC-INCOME")
    assert [p.account for p in income.lines] == ["4200", "6300", "6500"]
