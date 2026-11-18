"""Command line: consolidate, resume, trace, check, whatif, impact and diff-inputs. Review commands: cli_review.py."""
import argparse
import json
import sys
from pathlib import Path

from app.cli_review import review, smoke
from app.orchestrator.graph import resume_graph, run_graph, thread_for
from app.orchestrator.runner_plain import run_plain
from app.orchestrator.state import RunState, initial_state
from app.parsers.contracts import ContractError
from app.services.env_service import check_environment
from app.services.trace_service import trace
from app.services.whatif_service import Change, Diff, diff_inputs, impact, whatif
from app.utils.hashing import dumps
from app.utils.money import round2
from app.utils.paths import CONFIG_DIR, DEFAULT_DATA_DIR, DEFAULT_OUTPUT_DIR, RUNTIME_DIR

REJECTED = 2  # an input file is impossible; no output was written
PAUSED = 4  # waiting at the review gate, not a failure; 3 is a review stopped early


def _run(args: argparse.Namespace) -> int:
    state = initial_state(args.data, args.output, args.config, args.db, args.db.parent / "logs")
    if args.engine == "plain":
        final = run_plain(state)
    else:
        final = run_graph(state, args.db.parent / "checkpoints.db")
    return _report(final, args.output)


def _resume(args: argparse.Namespace) -> int:
    decisions = {t: "approve" for t in args.approve} | {t: "reject" for t in args.reject}
    answer = {"approver": args.approver, "decisions": decisions}
    return _report(resume_graph(args.thread, answer, args.db.parent / "checkpoints.db"), args.output)


def _report(state: RunState, out_dir: Path) -> int:
    if state["status"] == "awaiting_review":
        items = ", ".join(state["open_items"])
        print(f"paused at the review gate; waiting for a decision on: {items}")
        thread = thread_for(Path(state["data_dir"]), Path(state["config_dir"]))
        print(f"resume with: run.py resume --thread {thread} --approver NAME "
              f"--approve {state['open_items'][0]}")
        return PAUSED
    print(f"outputs written to {out_dir}")
    for key, value in json.loads((out_dir / "control_figures_pb.json").read_text(encoding="utf-8")).items():
        print(f"  {key}: {dumps(value, indent=None)}")
    print("checks: " + ("all passed" if state["checks_passed"] else "FAILED"))
    if state["blocked"]:
        print(f"BLOCKED: {state['blocked']}")
    return 0 if state["blocked"] is None and state["checks_passed"] else 1


def _print_diff(diff: Diff) -> int:
    if not diff.figures:
        print("no control figure changes")
    for key, (before, after) in diff.figures.items():
        print(f"  {key}: {before} -> {after}")
    if diff.new_findings:
        print("new findings: " + ", ".join(diff.new_findings))
    if diff.cleared_findings:
        print("findings gone: " + ", ".join(diff.cleared_findings))
    if diff.accounts:
        print("accounts that moved: " + ", ".join(
            f"{a} {round2(b)} -> {round2(n)}" for a, (b, n) in diff.accounts.items()))
    return 0


def _whatif(args: argparse.Namespace) -> int:
    return _print_diff(whatif(args.data, Change(args.patch, args.append, args.set), args.config))


def _impact(args: argparse.Namespace) -> int:
    return _print_diff(impact(args.data, args.target, args.config))


def _diff_inputs(args: argparse.Namespace) -> int:
    print("\n".join(diff_inputs(args.baseline, args.data) or ["inputs are identical"]))
    return 0


def _trace(args: argparse.Namespace) -> int:
    lines = trace(args.db, args.target)
    print("\n".join(lines))
    return 0


def _check(args: argparse.Namespace) -> int:
    results = check_environment(args.data)
    for name, ok, detail in results:
        print(f"{'ok  ' if ok else 'FAIL'}  {name}" + (f": {detail}" if detail else ""))
    return 0 if all(ok for _, ok, _ in results) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="run.py", description="Northwind consolidation")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, handler, text in (("consolidate", _run, "run the consolidation and write the outputs"),
                                ("trace", _trace, "walk a figure or an account down to file:line"),
                                ("check", _check, "check the environment and the data bundle"),
                                ("review", review, "AI reviewer advice per unit (replay, or --live to record)"),
                                ("smoke", smoke, "send one unit to each reasoning checkpoint (calls the model)"),
                                ("resume", _resume, "answer a paused run and let it finish"),
                                ("whatif", _whatif, "re-run on a patched copy of the inputs and show the figure diff"),
                                ("impact", _impact, "nudge one input row by 1% and show which figures move"),
                                ("diff-inputs", _diff_inputs, "what changed between two input folders")):
        command = sub.add_parser(name, help=text)
        command.set_defaults(handler=handler)
        command.add_argument("--data", type=Path, default=DEFAULT_DATA_DIR, help="folder holding the supplied files")
        command.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR, help="folder for the outputs")
        command.add_argument("--db", type=Path, default=RUNTIME_DIR / "run.db", help="evidence store file")
        command.add_argument("--config", type=Path, default=CONFIG_DIR, help="folder holding policy and overrides")
        if name == "consolidate":
            command.add_argument("--engine", choices=("graph", "plain"), default="graph",
                                 help="LangGraph or plain runner")
        if name == "review":
            command.add_argument("--live", action="store_true", help="call the configured model for unrecorded units")
            command.add_argument("--cost", action="store_true", help="print tokens and estimated cost per agent")
            command.add_argument("--reasoning", action="store_true", help="run the three reasoning checkpoints")
            command.add_argument("--max-units", type=int, default=None, help="most units sent live in one run")
            command.add_argument("--smoke", action="store_true", help="with --reasoning: one unit per checkpoint")
        if name == "resume":
            command.add_argument("--thread", required=True, help="thread printed when the run paused")
            command.add_argument("--approver", required=True, help="who is signing the decisions")
            command.add_argument("--approve", action="append", default=[], help="override target to approve")
            command.add_argument("--reject", action="append", default=[], help="override target to reject")
        if name == "whatif":
            command.add_argument("--patch", action="append", default=[], help="file:LINE.column=value")
            command.add_argument("--append", action="append", default=[], help="file=csv row to add")
            command.add_argument("--set", action="append", default=[], help="assumption key=value for this run")
        if name == "impact":
            command.add_argument("target", help="file:LINE, for example fx_rates.csv:3")
        if name == "diff-inputs":
            command.add_argument("baseline", type=Path, help="the older input folder to compare against")
        if name == "trace":
            command.add_argument("target", help="a control figure key or a group account code")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except ContractError as error:
        print(f"input rejected: {error}", file=sys.stderr)
        return REJECTED


if __name__ == "__main__":
    sys.exit(main())
