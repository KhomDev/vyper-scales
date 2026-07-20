from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .analyzer import analyze
from .manifest import ManifestError, load_manifest
from .render import render_json, render_markdown, render_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seamcheck",
        description="Check declared adversarial evidence at Vyper external-call seams.",
    )
    parser.add_argument("--manifest", default="seams.toml", help="path to seams.toml")
    parser.add_argument("--format", choices=("text", "json", "markdown"), default="text")
    parser.add_argument("--output", help="write rendered report to this path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = analyze(load_manifest(args.manifest))
    except (OSError, ManifestError) as exc:
        print(f"seamcheck: ERROR: {exc}", file=sys.stderr)
        return 2

    renderers = {"text": render_text, "json": render_json, "markdown": render_markdown}
    output = renderers[args.format](report)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output)
    else:
        print(output, end="")
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
