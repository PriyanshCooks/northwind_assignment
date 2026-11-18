"""Single entry point: consolidate | trace | check | serve. `serve` starts the review UI."""
import os
import sys

from app.cli import main as cli_main


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args[:1] == ["serve"]:
        from app.main import serve  # imported here so the other commands never load the web stack

        return serve()
    return cli_main(args)


def finish(code: int) -> None:
    """Flush and leave without interpreter teardown. After a live model call the process crashed in teardown (exit
    139) once the summary had printed; every file is closed by then, so nothing is lost."""
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


if __name__ == "__main__":
    code = main()
    if {"smoke", "--live"} & set(sys.argv[1:]):
        finish(code)
    sys.exit(code)
