from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .artifact import ArtifactError, load_artifact
from .compare import compare
from .compiler import CompilerError, compile_artifact
from .policy import PolicyError, load_policy
from .render import render_json, render_markdown, render_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vyper-semantic-diff",
        description="Compare Vyper compiler artifacts and execution traces.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    compare_parser = subparsers.add_parser("compare", help="compare two JSON artifacts")
    compare_parser.add_argument("baseline")
    compare_parser.add_argument("candidate")
    compare_parser.add_argument("--policy")
    compare_parser.add_argument("--format", choices=("text", "json", "markdown"), default="text")
    compare_parser.add_argument("--output")

    compile_parser = subparsers.add_parser("compile", help="capture one compiler artifact")
    compile_parser.add_argument("source")
    compile_parser.add_argument("--compiler", default="vyper")
    compile_parser.add_argument("--evm-version", default="prague")
    compile_parser.add_argument("--optimize", choices=("gas", "codesize", "none"), default="gas")
    compile_parser.add_argument("--project-root")
    compile_parser.add_argument("--traces")
    compile_parser.add_argument("--output", required=True)
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
        if args.command == "compile":
            artifact = compile_artifact(
                args.compiler,
                args.source,
                evm_version=args.evm_version,
                optimize=args.optimize,
                project_root=args.project_root,
                traces=args.traces,
            )
            _write_or_print(json.dumps(artifact, indent=2, sort_keys=True) + "\n", args.output)
            return 0

        report = compare(
            load_artifact(args.baseline),
            load_artifact(args.candidate),
            load_policy(args.policy),
        )
        renderers = {"text": render_text, "json": render_json, "markdown": render_markdown}
        _write_or_print(renderers[args.format](report), args.output)
        return report.exit_code
    except (OSError, ValueError, ArtifactError, PolicyError, CompilerError) as exc:
        print(f"vyper-semantic-diff: ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
