"""Single entry point: consolidate | trace | check | serve. `serve` starts the review UI."""
import sys

from app.cli import main as cli_main


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args[:1] == ["serve"]:
        from app.main import serve  # imported here so the other commands never load the web stack

        return serve()
    return cli_main(args)


if __name__ == "__main__":
    sys.exit(main())
