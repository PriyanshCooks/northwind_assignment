"""The review commands: advice from the reviewers and the reasoning layer, replayed from the ledger or recorded live."""
import argparse

from app.llm.cost import build_report, format_report
from app.llm.factory import load_llm_config
from app.llm.ledger import Ledger, LlmStop
from app.services.reasoning_service import run_reasoning
from app.services.review_service import BatchStopped, review_all
from app.services.run_service import build_context, stage
from app.utils.logging import RunLogger
from app.utils.paths import RUNTIME_DIR


def review(args: argparse.Namespace) -> int:
    """Advice from the reviewers (replayed from the ledger, or recorded with --live). It changes no figure."""
    if args.reasoning:
        return reasoning(args)
    ctx = build_context(args.data, args.config)
    cfg = load_llm_config()
    ledger = Ledger(cfg.ledger_path)
    try:
        results = review_all(ctx, cfg, ledger, "live" if args.live else "replay")
        stopped = None
    except BatchStopped as stop:
        results, stopped = stop.done, stop
    for r in results:
        if r.grounded.verified or r.grounded.unverified or r.missed:
            print(f"{r.unit.kind} {r.unit.unit_id} [{r.source}]: verified {list(r.grounded.verified)}, "
                  f"unverified {list(r.grounded.unverified)}, model missed {list(r.missed)}")
    answered = sum(r.source == "model" for r in results)
    print(f"{len(results)} units, {answered} answered by {cfg.model}, {len(results) - answered} by the rule fallback")
    if args.cost or stopped:
        print_cost(ledger, cfg.model)
    if stopped:
        print(f"stopped early: {stopped.reason}; {stopped.left} units were not reviewed")
        return 3
    return 0


def reasoning(args: argparse.Namespace) -> int:
    """The three reasoning checkpoints: advice only, replayed from the ledger unless --live. --smoke sends one unit
    to each checkpoint."""
    cfg = load_llm_config()
    ledger = Ledger(cfg.ledger_path)
    run = stage(build_context(args.data, args.config))
    try:
        report = run_reasoning(run, cfg, ledger, "live" if args.live else "replay", None, args.max_units, args.smoke)
    except LlmStop as stop:
        print(f"stopped: {stop}")
        return 3
    if not report.available or report.inputs is None or report.calcs is None or report.traces is None:
        print(report.note)
        return 0
    read = report.inputs
    print(f"input reader: {len(read.verified)} verified, {len(read.findings) - len(read.verified)} suspicion, "
          f"{len(read.dropped)} claims dropped, {len(read.unavailable)} chunks unanswered")
    print(f"calculation reviewer: {len(report.calcs.findings)} concerns, {len(report.calcs.dropped)} dropped, "
          f"{len(report.calcs.unavailable)} unanswered; investigations: {len(report.traces.traces)}")
    print(f"{len(ledger.new_keys)} units sent to {cfg.model} this run")
    if args.cost:
        print_cost(ledger, cfg.model)
    return 0


def print_cost(ledger: Ledger, model: str) -> None:
    """Tokens and estimated cost of the calls this review used, to the screen and the run log (never an output file)."""
    report = build_report([ledger.entries[k] for k in sorted(ledger.used)], ledger.new_keys)
    for line in format_report(report, model):
        print(line)
    log = RunLogger(RUNTIME_DIR / "logs", "review")
    for agent, row in report.per_agent.items():
        log.event("review", "cost", agent=agent, model=model, calls=row.calls, input_tokens=row.input_tokens,
                  output_tokens=row.output_tokens, recorded_cost_usd=str(row.recorded_cost),
                  new_cost_usd=str(row.new_cost))
    log.close()


def smoke(args: argparse.Namespace) -> int:
    """One live unit per reasoning checkpoint: the cheapest way to see a provider accept the schema and the tools."""
    args.reasoning, args.live, args.smoke, args.max_units, args.cost = True, True, True, None, False
    return reasoning(args)
