# Experimental DDlog MCP backend

The goal is for an agent to author and run data-centric programs through MCP,
with facts and changes as inputs and incremental results as outputs.

This opt-in server uses Lemmalog's existing AST parser to lower explicitly typed,
positive, non-recursive rules into DDlog. The official DDlog compiler produces
Rust running Differential Dataflow on Timely. A child process remains alive
between input transactions. The existing `lemmalog-mcp` memory server is unchanged.

Build the server with `cargo build --features mcp --bin lemmalog-ddlog-mcp`.
Set `LEMMALOG_DDLOG_BUILD` to the absolute path of `scripts/build-ddlog.sh` and
`LEMMALOG_DDLOG_WORKDIR` to a writable absolute build directory. Set `DDLOG_HOME`
to the DDlog distribution. The build driver takes a source path and an output
executable path; only the operator configures it. Start the built server as an
MCP stdio process. For independently attached clients sharing one program, see
[shared instances and processor versions](shared-instances.md). Explicit typed
[composition](composition.md) connects exact saved versions in one graph.

Tool calls use typed schema declarations. Example installation arguments:

```json
{
  "rules": "actionable(P,F) :- finding(P,F,S), current(P), S =< 2.",
  "schemas": {
    "finding": {"input": true, "fields": ["int", "int", "int"]},
    "current": {"input": true, "fields": ["int"]},
    "actionable": {"input": false, "fields": ["int", "int"]}
  }
}
```

`apply_changes` accepts insert/delete operations with `predicate` and `values`.
`lemmalog_query` takes an output `predicate`. `lemmalog_why` takes a zero-based
`rule` index and returns DDlog-derived variable-binding witnesses. Install
replaces the entire program and replays retained input; it does not append a
Lemmalog memory rule batch. Tool names are familiar but this experimental server
is **not wire-compatible with the existing memory MCP server**.

## Verified locally

Run `python3 scripts/test-ddlog-mcp.py` with the server and build environment set.
It launches the actual Rust MCP server and compiles two actual DDlog programs.
It checks a join, additions, deletions, duplicate insertion, explanation witnesses,
program replacement/replay, and rejection preserving previous state. Request and
response receipts go to `DDLOG_RECEIPTS` (default `/tmp/lemmalog-ddlog-receipts.json`).
Normal lowering tests run with `cargo test --features mcp --test ddlog_lowering`.

The local execution used official DDlog v1.2.3, its pinned Differential Dataflow
0.12 / Timely 0.12 forks, and Rust 1.65 for generated code. The server itself builds
with the current Rust toolchain. Modern Rust does not build that old generated
runtime unchanged. The release's bundled vendor directory was incomplete;
local verification reused a previously prepared complete vendor directory.

Optional build environment: `DDLOG_CARGO`, `RUSTC`, `DDLOG_CARGO_CONFIG`,
`DDLOG_CARGO_LOCK`, `DDLOG_OFFLINE=1`, and an absolute `CARGO_TARGET_DIR`.
These provide reproducible/offline toolchain and dependency control. A supplied
lockfile must describe the generated package named `program`. Build artifacts
remain in the work directory for inspection; large intermediate targets can be
removed after copying the executables. No compiler/dependency installer runs
implicitly in the MCP server.

The pinned CLI was separately tested to exit on a rejected noninteractive command
before the completion echo. This adapter relies on that contract and validates
all emitted mutation values. It does not support arbitrary CLI implementations.

## Remaining work

See [the migration requirements](ddlog-requirements.md). This implementation is a
backend foundation, not full AgentMemory integration. It has no durable graph
state, per-operation compilation/runtime timeouts, general
recursive explanations, mixed-value columns, negation, aggregates, temporal
builtins, inline facts, or native LLM calls. Schemas cannot change while retained
facts exist. Queries and witnesses currently return DDlog text. Compilation is
blocking. Unsupported language features are rejected before replacing the active
program; candidate build failures preserve its runtime and evidence metadata.

Strings containing control characters that require JSON Unicode escapes are
rejected before evaluation; the pinned CLI does not support those escapes.
Ordinary UTF-8 Unicode and the supported newline/tab escapes remain available.
