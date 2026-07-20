# Security policy

These tools are offline analyzers. They should never require a private key, sign a
message, broadcast a transaction, or mutate a chain.

Report vulnerabilities privately to `yuriykhomenkov@gmail.com`. Include the tool,
version, minimal input, observed verdict, expected verdict, and whether the issue can
produce a false PASS. False PASS bugs have priority over crashes and false positives.

## In scope

- manifest path traversal;
- command execution outside the explicit compiler executable and arguments;
- malformed input producing a false PASS;
- omitted ABI, storage, trace, or signature cases being reported as covered;
- nondeterministic output for identical inputs.

## Out of scope

- vulnerabilities in contracts used only as examples;
- correctness of third-party compilers, wallets, or test runners;
- claims beyond the explicit evidence represented in an input artifact.
