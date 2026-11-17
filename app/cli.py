"""Command line: run (consolidate), trace and check. whatif, impact, diff-inputs, review and verify arrive in wave 2."""
import argparse
import sys
from pathlib import Path

from app.domain.figures import Unknown
from app.services.env_service import check_environment
from app.services.run_service import run_consolidation
from app.services.trace_service import trace
from app.utils.hashing import dumps
from app.utils.money import round_tree
from app.utils.paths import DEFAULT_DATA_DIR, DEFAULT_OUTPUT_DIR, RUNTIME_DIR


def _run(args: argparse.Namespace) -> int:
    run = run_consolidation(args.data, args.output, args.db)
    print(f"outputs written to {args.output}")
    for key, figure in run.figures.items():
        shown = "null" if isinstance(figure, Unknown) else dumps(round_tree(figure.value), indent=None)
        print(f"  {key}: {shown}" + ("" if isinstance(figure, Unknown) else f"  [{figure.kind}]"))
    failed = [c.name for c in run.checks if not c.ok]
    passed = len(run.checks) - len(failed)
    print(f"checks: {passed} of {len(run.checks)} passed" + (f"; failed: {failed}" if failed else ""))
    if run.blocked:
        print(f"BLOCKED: {run.blocked}")
    return 0 if run.blocked is None and not failed else 1


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
                                ("check", _check, "check the environment and the data bundle")):
        command = sub.add_parser(name, help=text)
        command.set_defaults(handler=handler)
        command.add_argument("--data", type=Path, default=DEFAULT_DATA_DIR, help="folder holding the supplied files")
        command.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR, help="folder for the outputs")
        command.add_argument("--db", type=Path, default=RUNTIME_DIR / "run.db", help="evidence store file")
        if name == "trace":
            command.add_argument("target", help="a control figure key or a group account code")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
