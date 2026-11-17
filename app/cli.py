"""Command line: consolidate, resume, trace and check. whatif, impact, diff-inputs and review follow in wave 2."""
import argparse
import json
import sys
from pathlib import Path

from app.orchestrator.graph import resume_graph, run_graph, thread_for
from app.orchestrator.runner_plain import run_plain
from app.orchestrator.state import RunState, initial_state
from app.services.env_service import check_environment
from app.services.trace_service import trace
from app.utils.hashing import dumps
from app.utils.paths import CONFIG_DIR, DEFAULT_DATA_DIR, DEFAULT_OUTPUT_DIR, RUNTIME_DIR


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
        print(f"resume with: run.py resume --thread {thread_for(Path(state['data_dir']))} --approver NAME "
              f"--approve {state['open_items'][0]}")
        return 2
    print(f"outputs written to {out_dir}")
    for key, value in json.loads((out_dir / "control_figures_pb.json").read_text(encoding="utf-8")).items():
        print(f"  {key}: {dumps(value, indent=None)}")
    print("checks: " + ("all passed" if state["checks_passed"] else "FAILED"))
    if state["blocked"]:
        print(f"BLOCKED: {state['blocked']}")
    return 0 if state["blocked"] is None and state["checks_passed"] else 1


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
                                ("resume", _resume, "answer a paused run and let it finish")):
        command = sub.add_parser(name, help=text)
        command.set_defaults(handler=handler)
        command.add_argument("--data", type=Path, default=DEFAULT_DATA_DIR, help="folder holding the supplied files")
        command.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR, help="folder for the outputs")
        command.add_argument("--db", type=Path, default=RUNTIME_DIR / "run.db", help="evidence store file")
        command.add_argument("--config", type=Path, default=CONFIG_DIR, help="folder holding policy and overrides")
        if name == "consolidate":
            command.add_argument("--engine", choices=("graph", "plain"), default="graph",
                                 help="LangGraph or plain runner")
        if name == "resume":
            command.add_argument("--thread", required=True, help="thread printed when the run paused")
            command.add_argument("--approver", required=True, help="who is signing the decisions")
            command.add_argument("--approve", action="append", default=[], help="override target to approve")
            command.add_argument("--reject", action="append", default=[], help="override target to reject")
        if name == "trace":
            command.add_argument("target", help="a control figure key or a group account code")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
