# Formats and exit codes

All inputs are UTF-8 TOML or JSON. All JSON renderers sort keys so identical inputs
produce stable output.

## `seamcheck`

Manifest version: `1`.

- `[project].sources`: paths or glob patterns inside the manifest directory.
- `[project].strict_unregistered`: fail when a scanned external call matches no seam.
- `[project].ignore_calls`: explicit `fnmatch` patterns for intentionally unregistered calls.
- `[[seams]]`: `id`, `caller`, `target`, optional `call_kind`, `risk`, `rationale`, and
  `required` threat-dimension labels.
- `[[seams.evidence]]` or inline `evidence`: test selector, optional neighbor source,
  covered labels, and note.

Targets use shell-style matching against `<target>.<method>`, for example
`IPool(self.pool).exchange` or `*.price_oracle`.

Exit codes:

- `0`: all declared requirements covered and, in strict mode, no unregistered calls;
- `1`: coverage gap or strict-mode unregistered call;
- `2`: invalid manifest, missing declared call, missing evidence file, or I/O error.

## `vyper-semantic-diff`

Artifact schema version: `1`.

Top-level fields are `compiler`, `source`, `contract`, and `traces`. The contract payload
accepts Vyper `combined_json` keys including `abi`, `method_identifiers`, `layout`, and
`bytecode_runtime`. A raw single-contract Vyper `combined_json` file is accepted too.

Every trace must have a unique non-empty `case`. Other trace fields are user-defined and
compared recursively after policy-ignored keys are removed.

Exit codes:

- `0`: no policy-failing difference;
- `1`: ABI, selector, storage, trace, or other configured difference;
- `2`: malformed artifact/policy, compiler failure, timeout, or I/O error;
- `3`: behavior is unassessed because traces are required but absent on both sides.

## `vyper-sig-matrix`

Policy version: `1`. Generated matrices include a SHA-256 fingerprint of the normalized
policy. Check input is either a JSON array or `{ "results": [...] }`. Each result requires:

```json
{
  "id": "erc1271-magic",
  "observed": "accept",
  "path": "erc1271-staticcall"
}
```

`path` is optional. When present, it must match the policy-derived verification route.

Exit codes:

- `0`: every expected case is present and matches;
- `1`: missing, unexpected, or mismatched case;
- `2`: malformed policy/results or I/O error.
