from __future__ import annotations

import argparse
import sys

from walkthrough.config import load_config


def cmd_doctor(args) -> int:
    config = load_config()
    names = args.languages.split(",") if args.languages else list(config.languages)
    missing = 0
    for name in names:
        language = config.languages[name]
        status = "ok" if language.installed() else "missing"
        print(f"{name}\t{status}\t{' '.join(language.command)}")
        if status == "missing":
            missing += 1
            print(f"  install: {language.install}")
    return 1 if missing else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="walkthrough")
    sub = parser.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor", help="check language servers")
    doctor.add_argument("--languages", help="comma-separated language names")
    doctor.set_defaults(func=cmd_doctor)
    return parser


def main(argv) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
