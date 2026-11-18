"""Batch run of the reviewers over the supplied units and the seeded ones. Writes everything to .northwind/ and prints
a short summary: python -m tests.evals.record [--live [--smoke]] [--minutes N]. Live mode appends to the ledger and
never sends a recorded unit again, so a second run costs nothing. --smoke covers one journal and one mapping unit."""
import argparse
import json
import time

from app.agents.review.units import journal_units, mapping_units
from app.llm.cost import build_report, format_report
from app.llm.factory import load_llm_config
from app.llm.ledger import Ledger, LlmStop
from app.services.review_service import UnitResult, review_unit
from app.services.run_service import build_context
from app.utils.paths import DEFAULT_DATA_DIR, RUNTIME_DIR
from tests.evals.labels import expected
from tests.evals.metrics import lines, score
from tests.evals.seeds import seeded_journals, seeded_mappings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--smoke", action="store_true", help="with --live: one journal and one mapping unit, then stop")
    parser.add_argument("--minutes", type=float, default=30)
    args = parser.parse_args()
    ctx, cfg = build_context(DEFAULT_DATA_DIR), load_llm_config()
    ledger = Ledger(cfg.ledger_path)
    mode = "live" if args.live else "replay"
    work = [(u, expected(u.unit_id, u.kind), "supplied") for u in mapping_units(ctx) + journal_units(ctx)]
    work += [(s.unit, s.expected, "seeded") for s in seeded_journals(ctx) + seeded_mappings(ctx)]
    if args.smoke:
        work = [next(w for w in work if w[0].kind == kind) for kind in ("journal", "mapping")]
    deadline = time.monotonic() + args.minutes * 60
    done: list[tuple[str, UnitResult, set[str]]] = []
    stopped = ""
    for unit, truth, origin in work:
        if time.monotonic() > deadline:
            break
        try:
            done.append((origin, review_unit(ctx, cfg, ledger, unit, mode), truth))  # type: ignore[arg-type]
        except LlmStop as stop:
            stopped = f"stopped: {stop}; {len(work) - len(done)} of {len(work)} units not reviewed"
            break
    RUNTIME_DIR.mkdir(exist_ok=True)
    out = RUNTIME_DIR / "eval_results.json"
    out.write_text(json.dumps([{"origin": o, "unit": r.unit.unit_id, "source": r.source,
                                "verified": list(r.grounded.verified), "dropped": [list(d) for d in r.grounded.dropped],
                                "unverified": list(r.grounded.unverified), "expected": sorted(t), "note": r.note}
                               for o, r, t in done], indent=1), encoding="utf-8")
    if args.smoke:
        for _, r, _ in done:
            print(f"{r.unit.kind} {r.unit.unit_id} [{r.source}]: verified {list(r.grounded.verified)}, "
                  f"dropped {len(r.grounded.dropped)}, unverified {list(r.grounded.unverified)}")
    for source in () if args.smoke else ("model", "rules"):
        for origin in ("supplied", "seeded"):
            pairs = [(r, t) for o, r, t in done if o == origin and r.source == source]
            if pairs:
                print(*lines(f"{source} on {origin}", score(pairs)), sep="\n")
    print(f"answered by the model: {sum(r.source == 'model' for _, r, _ in done)} of {len(done)}; file {out}")
    report = build_report([ledger.entries[k] for k in sorted(ledger.used)], ledger.new_keys)
    print(*format_report(report, cfg.model)[-1:], sep="")
    if stopped:
        print(stopped)
    return 3 if stopped else 0


if __name__ == "__main__":
    raise SystemExit(main())
