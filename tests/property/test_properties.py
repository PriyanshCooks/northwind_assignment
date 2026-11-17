"""Random but sensible changes to the rates and to the US books. Whatever the change, the accounting identities hold:
the balance sheet balances, intercompany nets to zero and the two reserve routes agree. A hardcoded figure fails."""
import tempfile
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.services.run_service import build_context, stage
from app.services.whatif_service import Change, patched_copy
from app.utils.paths import CONFIG_DIR, DEFAULT_DATA_DIR

RATES = {3: "1.2780", 4: "1.2840", 6: "1.2530", 9: "83.95", 11: "85.62"}  # fx_rates.csv line -> supplied rate
percent = st.integers(min_value=60, max_value=160)


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(percent, min_size=5, max_size=5), st.integers(min_value=-500_000, max_value=500_000))
def test_the_identities_hold_for_any_rates_and_any_balanced_us_posting(scales: list[int], extra: int) -> None:
    patches = [f"fx_rates.csv:{line}.rate={float(old) * scale / 100:.4f}"
               for (line, old), scale in zip(RATES.items(), scales, strict=True)]
    patches += ["tb_us.csv:18.credit=%.2f" % (18400000 + extra), "tb_us.csv:2.debit=%.2f" % (4875000 + extra)]
    with tempfile.TemporaryDirectory() as tmp:
        patched_copy(DEFAULT_DATA_DIR, Path(tmp) / "data", Change(patches=patches))
        run = stage(build_context(Path(tmp) / "data", CONFIG_DIR))
    assert run.blocked is None
    broken = [c.name for c in run.checks if not c.ok and not c.name.startswith("oracle:")]
    assert broken == []
