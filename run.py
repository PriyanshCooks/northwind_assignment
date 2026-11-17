"""Single entry point: consolidate | trace | check | serve. `serve` is built in wave 2."""
import sys

from app.cli import main as cli_main


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args[:1] == ["serve"]:
        print("not built yet (Wave 2)")
        return 2
    return cli_main(args)


if __name__ == "__main__":
    sys.exit(main())
