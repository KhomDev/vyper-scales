# Agent operating rules

This directory is the standalone Vyper Scales workspace. Keep it independently runnable;
do not import private KhomDev protocol packages or rely on sibling repository layout.

## Work loop

1. Read the relevant tool README, schema, fixtures, and tests before editing.
2. Write or update the failing test first when changing verdict behavior.
3. Keep the core dependency-free unless a dependency removes more security surface than
   it adds.
4. Run the narrow test, the full suite, `ruff check .`, and `ruff format --check .`.
5. Put generated reports under `reports/` or `artifacts/`; both are gitignored.
6. Never rewrite an authored article from generated output.

## Safety contract

- No private keys, seed phrases, RPC credentials, transaction signing, or broadcast code.
- External compiler execution must use an argument vector, never `shell=True`.
- Paths from manifests must remain inside the manifest project root.
- A missing input is an error, never an implicit PASS.
- Unsupported semantics are reported as `UNASSESSED`, never silently ignored.
- Tests may use adversarial fixtures. Fixtures must be labeled as fixtures, not real
  protocol neighbors.

## Shipping bar

A change ships only when its machine-readable format, CLI output, regression tests,
example, limitations, and article statement agree. If any disagree, the code wins and
the documentation must be corrected before merge.
