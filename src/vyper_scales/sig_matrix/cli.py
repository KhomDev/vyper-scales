from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .checker import ResultsError, check, load_results
from .matrix import generate_cases
from .policy import SignaturePolicyError, load_policy
from .render import render_cases_json, render_cases_markdown, render_check_json, render_check_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vyper-sig-matrix",
        description="Generate and check a smart-account signature compatibility matrix.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate")
    generate.add_argument("--policy", required=True)
    generate.add_argument("--format", choices=("json", "markdown"), default="json")
    generate.add_argument("--output")
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("results")
    check_parser.add_argument("--policy", required=True)
    check_parser.add_argument("--format", choices=("text", "json"), default="text")
    check_parser.add_argument("--output")
    return parser


def _write_or_print(output: str, path: str | None) -> None:
    if path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(output)
    else:
        print(output, end="")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        policy = load_policy(args.policy)
        if args.command == "generate":
            cases = generate_cases(policy)
            output = (
                render_cases_json(policy, cases)
                if args.format == "json"
                else render_cases_markdown(policy, cases)
            )
            _write_or_print(output, args.output)
            return 0
        report = check(policy, load_results(args.results))
        output = render_check_json(report) if args.format == "json" else render_check_text(report)
        _write_or_print(output, args.output)
        return report.exit_code
    except (OSError, ValueError, SignaturePolicyError, ResultsError) as exc:
        print(f"vyper-sig-matrix: ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
