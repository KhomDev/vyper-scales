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

Targets use shell-style matching against the normalized `<target>.<method>` string,
for example `IPool(self.pool).exchange` or `*.price_oracle`. Whitespace inside the
scanned expression is removed before matching, and a target that is character-for-character
equal to that string matches even when it contains `[]`. A bare method name does not match
every call of that method. `ignore_calls` patterns use the same fnmatch rules against
`path:target.method` (for example `contracts/Router.vy:IPool(self.pool).exchange`).
Ignore patterns do not suppress calls the scanner could not classify.

A Python evidence selector (`path.py::test_name`, `path.py::Class::test_name`, or a
parametrized `test_name[...]`) must name a function or class defined in that file.
The tool does not execute the test or import helpers from other modules.

Exit codes:

- `0`: all declared requirements covered and, in strict mode, no unregistered calls;
- `1`: coverage gap or strict-mode unregistered call;
- `2`: invalid manifest, missing declared call, missing or unparsable evidence, or I/O error;
- `3`: one or more `extcall`, `staticcall`, or `raw_call` sites could not be classified.
  An unclassified call is `UNASSESSED`, including when a seam also has a coverage gap.
  A manifest error still exits `2`.

## `vyper-semantic-diff`

Artifact schema version: `1`.

Top-level fields are `compiler`, `source`, `contract`, and `traces`. The contract payload
accepts Vyper `combined_json` keys including `abi`, `method_identifiers`, `layout`, and
`bytecode_runtime`. A raw single-contract Vyper `combined_json` file is accepted too.

`abi`, `method_identifiers`, storage layout (`layout` or `storage_layout`), and runtime
bytecode (`bytecode_runtime` or `deployed_bytecode`) must be present. An omitted field is
an error, not an empty value. Duplicate ABI signatures are an error. Event `indexed` flags
are part of the ABI comparison. Tuple types must include `components`.

Creation bytecode (`bytecode`) and `integrity` are compared when present and are
informational unless policy `fail_on` includes `bytecode` or `integrity`. Two artifacts
that both omit creation bytecode do not prove creation-code equality. Compiler metadata
is compared except for the absolute `executable` path, which is environment-specific.
Version, EVM version, optimizer, and Vyper `settings_dict` values merged into that
metadata are informational unless policy `fail_on` includes `compiler`.

Every trace must have a unique non-empty `case`. Other trace fields are user-defined.
`ignore_trace_fields` removes keys only at the top level of each trace, not inside nested
objects. A trace with no fields besides `case` and ignored keys is unassessed.

Exit codes:

- `0`: no policy-failing difference;
- `1`: ABI, selector, storage, trace, or other configured difference;
- `2`: malformed artifact/policy, duplicate ABI entry, compiler failure, timeout, or I/O error;
- `3`: behavior is unassessed because traces are required but absent on both sides, or
  because every present trace lacks comparable fields.

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
A results object may include `policy_fingerprint`. When it is present it must equal the
SHA-256 of the normalized policy passed to `check`; a mismatch is an error. Omitting the
fingerprint does not skip outcome checks.

Exit codes:

- `0`: every expected case is present and matches;
- `1`: missing, unexpected, or mismatched case;
- `2`: malformed policy/results or I/O error.
