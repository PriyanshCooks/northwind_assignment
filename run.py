"""Single entry point: consolidate | serve | check. Each command is built in the wave shown."""
import argparse
import sys

COMMANDS = {
    "consolidate": ("run the consolidation and write /output", 1),
    "serve": ("start the API and review UI", 2),
    "check": ("check the environment and the data bundle", 1),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="run.py", description="Northwind consolidation")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, (help_text, _wave) in COMMANDS.items():
        sub.add_parser(name, help=help_text)
    args = parser.parse_args(argv)
    wave = COMMANDS[args.command][1]
    print(f"not built yet (Wave {wave})")
    return 2


if __name__ == "__main__":
    sys.exit(main())
