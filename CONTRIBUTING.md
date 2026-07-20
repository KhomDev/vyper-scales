# Contributing

Each contribution should close one concrete false-positive or false-negative path.
Large framework rewrites are less useful than a small regression fixture that another
Vyper team can copy into its repository.

## Development

```bash
uv sync --dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

For behavior changes, include:

- the smallest input artifact or manifest that reproduces the problem;
- a test that fails before the change;
- the expected CLI exit code;
- any schema compatibility impact;
- a limitation note when the tool cannot distinguish two cases safely.

Do not commit generated Markdown or JSON reports. Commit authored examples and fixtures.
