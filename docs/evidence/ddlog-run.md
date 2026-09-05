# Actual DDlog MCP execution

The Rust `lemmalog-ddlog-mcp` binary was driven through initialization, tool
listing, and real tool calls by `scripts/test-ddlog-mcp.py`. Its existing Lemmalog
AST parser lowered the rule into typed DDlog, and the official compiler built
native ARM64 executables. Neither Lemmalog's existing evaluator nor a mock
computed the results.

Observed behavior:

- A finding alone produced no actionable result until the joining current fact
  arrived; then DDlog emitted the actionable row with weight +1.
- Reinserting the same current fact emitted no changes.
- An alternative supporting finding binding could be inserted and deleted
  without retracting the still-supported actionable row.
- Deleting the final supporting finding emitted weight -1 for the actionable
  row and removed its explanation witness.
- Replacing the severity threshold from 2 to 3 compiled another program and
  replayed two retained input facts; the severity-3 finding became actionable.
- A deliberately failing build driver left the previous version and its
  explanation metadata active.
- Unsupported rule syntax and a mistyped mutation returned tool errors while
  the previous version's result and evidence remained queryable.

The captured requests/results are in `ddlog-mcp-receipts.json`. This fixture is
hand-authored: it proves tool execution, not LLM generation quality or constrained
model decoding.

Compiler: official DDlog v1.2.3, commit
`cd1164ee3aed56734a3dd114a71ce4902fd7e3ef`.
Generated runtime dependency lock uses Differential Dataflow 0.12 fork
`f225896b4826fc0be2e26db10e0702ac38b377d2` and Timely 0.12 fork
`5b999d00949fe39689b1c334347d061d1f185318`.
Generated code built using Rust 1.65 and existing complete vendored dependencies.

A separate negative probe sent an unknown input relation to the pinned DDlog CLI
in noninteractive mode. It returned failure without reaching the subsequent echo
marker. This agrees with its `handle_cmd` / `cmd_parser::interact` source paths.

This evidence covers the experimental typed positive-rule backend. It does not
establish full AgentMemory compatibility, durability, inference execution,
concurrent clients, or a performance advantage.

## Registered-operation follow-up

The separate `test-agent-requests.py` fixture also executed the generated
registered-operation graph. `registered-agent-receipts.json` records its actual
MCP exchanges. It proved pending/running changes, stable identities, stale-response
exclusion, claim-once admission, completion idempotency/conflicts, output
retraction on revision change, and isolation across entities. The external
provider was a mock worker; this does not establish live model inference.
