set shell := ["sh", "-eu", "-c"]

setup:
    uv sync --dev

test:
    uv run pytest

lint:
    uv run ruff check .
    uv run ruff format --check .

qa: test lint

examples:
    uv run seamcheck --manifest examples/seamcheck/seams.toml
    uv run vyper-semantic-diff compare examples/semantic-diff/baseline.json examples/semantic-diff/candidate.json
    uv run vyper-sig-matrix generate --policy examples/sig-matrix/policy.toml --format markdown
