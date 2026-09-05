# Shared-instance requirement evidence

The final server passed a deterministic real-DDlog two-client driver and a
separate agent-issued author/reviewer exercise. These test shared access and
processor lifecycle. They do not establish crash durability, provider exactly-once
execution, learning, or swarm performance.

[The requirement specification](../../shared-instances.md#requirements-and-executable-evidence)
maps each accepted requirement to its executable oracle. The implementation uses
one operator-owned Unix host, independent stdio bridges, and a durable definition
registry; running graph state remains in memory.

| Evidence | Result |
|---|---|
| Real compiler/runtime driver | Nine grouped checks passed; three DDlog-generated executables ran |
| Independent access | Separate pipe clients reused JSON-RPC IDs without reply mixing |
| Large request | One 262,302-byte request, fragmented into pipe writes, produced the exact expected row |
| Disconnect/reconnect | Reviewer read/mutated after author bridge exited; author reattached to retained state |
| Registry | Automatic validation metadata, stale expected-version rejection, immutable pin, fork lineage |
| Isolation and operations | Separate hosts isolated data; registered processor claims survived worker disconnect; stale results stayed excluded |
| Actual agent-issued exercise | Author, reviewer, and reconnected author independently issued 15 JSON-RPC requests on the final server |
| Cleanup | Explicit actor stop returned successfully and removed both endpoint files; real driver stopped all hosts |

The [real-backend receipt](real-backend-receipt.json) records request size/hash,
completed checks, final server/compiler hashes, generated sources, and generated
executable hashes. The driver snapshots the server hash before its first host
and rejects a changed executable at the end. It uses the official offline DDlog
v1.2.3 compiler and its pinned Differential/Timely runtime through the documented
operator build driver, with one reusable generated-code target directory.

The final driver also exposed an invalid test fixture when automatic saving
validation was introduced: its unactivated replacement used unsupported `!=`
syntax. Validation rejected it correctly. The fixture now uses a supported join
to test a changed definition without activating it. The passing receipt records
the corrected final scenario; earlier failures are not counted as passing trials.

[Agent exchanges](agent-exchanges.json), [provenance](agent-provenance.json),
[generated source](agent-program.dl), and [cleanup](agent-cleanup.json) record the
separate actual exercise. The author deliberately tried invalid syntax, observed
rejection, saved and activated a valid copy relation, inserted `author_seed`, and
closed its bridge. A different agent launched its own pipe client, checked the
instance/pin and existing row, inserted `reviewer_probe`, and closed that client.
The author then reconnected through another bridge and verified both exact rows
before explicit stop. No terminal/session handle was shared.

This actor exercise reused an already compiled official DDlog executable only
after the operator's cache driver verified the generated source bytes and the
source/executable SHA256. It did not freshly compile that executable. The
independent deterministic driver did compile its three programs. Reviewer receipts
preserve request parameters and decoded results; author receipts preserve complete
JSON-RPC envelopes. Those evidence formats are intentionally described separately.

The [verification receipt](verification.json) records the Rust, Python, and
standalone compatibility checks. The simulated host tests exercise the real Rust
host and bridges with explicitly fake compiler/runtime processes. They cover
malformed/oversized/partial input, uncertain replies, runtime failure fencing,
failed candidate preservation, slow receivers, private/stale descriptors,
64-client stop admission, immediate-ready SIGTERM, stalled compiler/runtime
process groups, and standalone process-group compatibility. Their fixture output
is not evidence of Datalog evaluation.

Local descriptor/build paths, process IDs, and operator environment paths are
excluded from published actor evidence. Inputs are synthetic strings and programs;
no provider credentials or external inference were used. Build logs and large
executables remain local. The manifest hashes the published evidence files.

The accepted local-instance requirements are covered. Native HTTP, per-client
roles, graph recovery, fact-state CAS, and per-operation compiler/runtime deadlines
remain deferred. Content-addressed `expected_version` compares only the registry
pointer. A future diagnosis interface is tracked separately in
[issue #4](https://github.com/everettVT/lemmalog/issues/4); this change uses the
current authoring, query, and witness API and adds no diagnosis endpoint or CI
workflow.
