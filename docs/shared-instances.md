# Shared program instances and processor versions

A shared instance lets an author and reviewer independently operate the same
running DDlog program. The operator starts one owner; each client starts its own
MCP stdio bridge. Closing either bridge leaves the program, facts, and registered
claims alive. This local implementation supports Unix and trusted clients running
as the same OS user. It retains the existing standalone stdio mode.

## Start, attach, and stop

Build `cargo build --features mcp --bin lemmalog-ddlog-mcp` and configure the
trusted DDlog build environment in [ddlog.md](ddlog.md). The compiler, build root,
and operation registry are operator configuration, never authored rule inputs.
Use absolute paths and a short private endpoint directory because Unix socket
paths have an OS length limit. The endpoint's parent must already exist; the host
can create the final directory with mode `0700`.

```sh
export LEMMALOG_DDLOG_WORKDIR=/absolute/builds
export LEMMALOG_DDLOG_BUILD=/absolute/lemmalog/scripts/build-ddlog.sh
export LEMMALOG_PROCESSOR_REGISTRY=/absolute/private/processor-registry

lemmalog-ddlog-mcp host \
  --socket /absolute/private/instance/socket \
  --descriptor /absolute/private/instance/descriptor.json
```

Run the host under an operator-controlled process supervisor, independently of
either client. A ready descriptor is published only after the socket and owner
exist. Both the socket and descriptor have mode `0600`, inside the same `0700`
directory. A stale endpoint is rejected, never automatically replaced or resumed.

Configure each MCP client to launch its own bridge:

```json
{
  "mcpServers": {
    "lemmalog-ddlog": {
      "command": "/absolute/lemmalog/target/debug/lemmalog-ddlog-mcp",
      "args": ["connect", "--descriptor", "/absolute/private/instance/descriptor.json"]
    }
  }
}
```

Bridges use ordinary pipes. They do not need access to another client's terminal,
process handle, build environment, or operation registry. All attached clients
have equal full tool authority. Labels such as author, reviewer, or worker do not
confer roles. Same-user filesystem access is the trust boundary; this is not
isolation between mutually untrusted agents sharing one OS account.

```sh
lemmalog-ddlog-mcp stop --descriptor /absolute/private/instance/descriptor.json
```

Explicit stop closes admission, aborts active compiler/runtime work, kills their
process groups, drops the owner, and removes its socket and descriptor. SIGTERM
and SIGINT follow the same cleanup path. Build artifacts and the processor
registry remain. Stop is allowed even when the ordinary attachment limit of 64
is reached. Disconnecting every client does not stop the host. The host must not
be killed with a client's process group; SIGKILL cannot run cleanup.

No arguments still runs one isolated stdio-owned program, ending on stdin EOF.
Standalone compiler/runtime children remain in the client process group so the
existing relay can terminate that group. The original four tools are retained when no operation/processor registry is
configured. Hosted mode adds `instance_info`; a configured processor registry
adds the nine processor tools below. MCP still advertises `2024-11-05` over stdio;
the internal Unix socket does not require custom transport support in clients.

## Processor identity and immutable definitions

The processor registry stores reusable definitions, not live facts or claims.
Each processor has a stable `processor_<32 hex digits>` identity from 128 random
bits. Its versions are `sha256:<64 hex digits>` content identities. Instance IDs
are separately generated 128-bit random incarnations. None of these IDs are
creation timestamps, MCP request IDs, entity revisions, or DDlog install counters.
UUIDv7 is unnecessary here: ordering is metadata, while content identity must stay
stable for the same exact definition.

A program definition contains `rules`, `schemas`, optionally an explicit interface,
and optionally an operation binding. A composition definition instead contains an
exact-version manifest, described in [composition.md](composition.md):

```json
{
  "rules": "echo(V) :- source(V).",
  "schemas": {
    "source": {"input": true, "fields": ["string"]},
    "echo": {"input": false, "fields": ["string"]}
  },
  "operation": null
}
```

The hash covers compact JSON with recursively sorted object keys, exact rule text,
schema declarations, and the full optional operation binding. Whitespace changes
inside authored rule text produce a different version. Omitted operation is
normalized to null. Creation time (`created_at_unix_ms`), optional Git provenance,
processor identity, and fork lineage are outside the definition hash. Identical
content in two processors can share a version hash while retaining distinct
processor identities. Republishing old content preserves that immutable record's
original creation time and provenance.

Optional `git_provenance` is `{ "repository": "...", "revision": "...",
"path": "..." }`, with optional path. It is supplied metadata; the registry does
not invoke Git or attest that a commit contains the definition.

| Tool | Arguments and behavior |
|---|---|
| `processor_create` | `definition`, optional `git_provenance`; creates a new identity and its first current version |
| `processor_get` | `processor_id`, optional `version`; reads an exact immutable version, or resolves current once |
| `processor_publish` | `processor_id`, `expected_version`, `definition`, optional `git_provenance`; advances current only if the old version matches |
| `processor_fork` | `processor_id`, exact `version`, optional `git_provenance`; creates a new identity whose lineage references that source version |
| `processor_install` | `processor_id`, optional `version`; selects current once or an explicit version, compiles it, and pins a fresh instance |
| `processor_list` | `limit`, `after`, `include_archived`; bounded discovery in stable-identity order |
| `processor_search` | `query` plus list options; literal case-insensitive substring search |
| `processor_archive` | `processor_id`, `expected_version`, `expected_revision`; preserves definitions while retiring the identity from active use |
| `processor_restore` | Same lifecycle preconditions; restores active discovery and eligibility without compiling or running |

`processor_install` means compile and activate the selected saved program in an
instance; it does not install software. Creating or publishing a definition
validates and saves it without starting a graph.

A conditional pointer conflict rejects the publication. Concurrent processes
serialize updates through a create-new registry lock; contention fails explicitly.
A crashed writer can leave `.update.lock`. An operator must establish writer
absence and reconcile the registry before removing it; clients never steal locks.
Files are atomically published and synchronized. A failed sync can leave an
uncertain publication and must be inspected before retry. The registry verifies
record identity and definition hashes when reading. Saving automatically checks authored syntax, schema/type consistency, supported
lowering, and registered-relation restrictions without running a graph. Invalid
definitions are rejected before any version or pointer is written. Returned
`validation` metadata explicitly distinguishes these checks from full DDlog
compilation, which happens at activation. This immutable metadata describes the
saving checks; it is not a global record of whether any instance later compiled
that version.

Fork lineage is retained on subsequent versions of the fork. A fork contains no
live instance state. Moving a registry's current pointer never changes a running
instance. Once `processor_install` succeeds, ordinary install, registered install,
and another processor install are rejected on that instance. Start another
instance to select a different version. Unpinned instances can still use the
existing whole-program replacement tool, with retained-fact replay.

For a registered program, define `operation` as
`{"name":"review","version":"v1","description":"Review text"}` and write rules
consuming `agent_result`. Installation requires an exact match against the host's
immutable `LEMMALOG_AGENT_OPERATIONS` registry. Operation credentials and execution
stay outside the definition. The same owner holds `Backend` and `AgentProgram`,
so all attached workers share claims, completions, and revision freshness. See
[agent-requests.md](agent-requests.md) for external-effect limitations.

## Serialization and failures

All semantic calls execute under one owner lock, including reads, registered
operations, and the entire compile/replay/activate operation. Queries observe a
completed state. A compilation blocks other semantic calls; lifecycle control is
independent. Responses are written after releasing the semantic owner, so a slow
or disconnected receiver cannot block another client's computation.

Fact batches retain set semantics and execute serially. There is no fact-state
compare-and-swap and no atomic query-then-mutate sequence across clients. Later
serialized calls apply to the current state; simultaneous arrival order is not
promised. The existing `version` counter counts installations, not transactions.
Registry `expected_version` protects only the definition pointer.

The wire accepts complete newline-delimited requests up to 1 MiB, including the
newline, independent of pipe fragmentation. Partial EOF and oversized messages
close only that connection without admitting partial changes. Invalid JSON gets
a JSON-RPC parse error. Runtime output and encoded responses are limited to 4 MiB;
a reply can still exceed the encoded limit after a tool completes. Bridge output
has a five-second write timeout to stop slow receivers retaining connection work.
These limits do not bound compiler memory, retained facts, or registry growth.

An acknowledged successful operation survives client disconnect. A disconnected
client with no acknowledgement must treat the outcome as uncertain. Bridges do
not reconnect or replay requests automatically, and JSON-RPC IDs do not deduplicate
work. A registered claim can remain claimed even when its worker lost the reply;
reconnecting does not authorize repeating the external action.

Candidate installation failure preserves an existing active graph. Runtime I/O
failure or oversized runtime output drops that runtime and marks the shared
instance failed. Inspection reports failure; new semantic work is rejected.
Operator reconciliation and explicit recreation are required. A process restart
loses facts, graph state, and claims; retained executables and the durable definition
registry do not provide graph or provider recovery. No automatic claim expiry,
provider exactly-once guarantee, or transparent uncertain retry is introduced.

There are no per-operation compiler/runtime deadlines yet. Explicit stop can abort
stalled process groups; it is destructive to in-flight work and does not prove
rollback. The bounded cleanup tests exercise ordinary Unix processes and their
descendants; they do not establish cleanup after SIGKILL, kernel-level unkillable
processes, or a trusted child deliberately escaping its process group.

## Requirements and executable evidence

These are the accepted scope of this change. Each requirement is mapped to an
executable oracle, with actual-runtime evidence distinguished from simulation.
Results and sanitized receipts live in [the evidence directory](evidence/shared-instances/README.md).

| Requirement | Executable oracle |
|---|---|
| Independent clients share one owner; author loss does not lose state | `scripts/test-shared-instance.py`: independent client IDs, disconnect/reconnect, reviewer mutation; separate author/reviewer exchange |
| One request of at least 256 KiB arrives intact without a PTY | Real driver: fragmented request hash/byte count and exact queried row |
| Fact changes serialize, instances isolate data | Real driver: concurrent independent writes, separate H2 with same schema |
| Saving automatically validates syntax/types/supported forms without activation | Registry invalid syntax/type/unsupported-form tests preserve current pointer; valid registered definition checks |
| Stable processor identity, immutable versions, separate content/time/Git metadata | `tests/processor_registry.rs`: fixed content hash, restart persistence, immutable history and metadata |
| Current pointer updates reject stale expected versions | Registry OS-process race test plus real driver pointer conflict |
| Fork creates distinct identity with exact source lineage | Registry tests and real driver fork/H2 |
| Running instances remain pinned when current moves | Real driver observes original version/behavior after publication |
| Registered claims/freshness are shared between attached clients | Real driver H3: claim, disconnect, duplicate rejection, stale and current completion |
| Lost replies never cause automatic retry | `tests/test_shared_host.py`: admitted mutation, lost connection, exact one simulated commit and reconnect inspection |
| Runtime failure fences new work; rejected candidate preserves active state | Simulated failure tests, plus existing real standalone failed-build contract |
| Partial/oversize input, stale descriptors, slow receivers isolate connections | Simulated host tests with real Rust host/bridges and sockets |
| Explicit cleanup is bounded for stalled compiler/runtime descendants | Simulated process-group tests, SIGTERM, and stop with 64 idle clients; real driver endpoint cleanup |
| Standalone mode and existing DDlog tools remain supported | Existing real `test-ddlog-mcp.py` and `test-agent-requests.py`; Rust lowering contracts |

Run Rust contracts with `cargo test --offline --features mcp`. The simulated suite
uses no DDlog compiler and must never be cited as real graph evaluation:

```sh
python3 -m unittest discover -s tests -p test_shared_host.py -v
```

With the official offline DDlog toolchain configured, run:

```sh
python3 scripts/test-shared-instance.py
python3 scripts/test-ddlog-mcp.py
python3 scripts/test-agent-requests.py
```

The real driver uses one reusable generated-code target directory when configured
through `CARGO_TARGET_DIR`. Do not run concurrent compilers against the same target
because the driver copies its resulting executable. No provider inference is
needed. Native HTTP, per-client roles, graph crash recovery, and fact-state CAS
are intentionally outside these accepted local-instance requirements.

## Discover, archive and restore definitions

`processor_list` returns saved definitions ordered by stable processor identity.
`processor_search` uses a case-insensitive literal substring of the identity,
current version, or compact authored definition JSON; an empty query is a list.
There is no relevance ranking or separate search index.

Both take `limit` (1–100, default 20), optional `after`, and optional
`include_archived` (default false). Pass the returned `next_cursor` as `after` to
continue with the same query and options. Results include identity, current
version, content hash, version creation time, kind, lineage, and `status` (`active`
or `archived`) plus `lifecycle_revision`; archived entries also carry their archive time. Pagination uses
sorted identity keys, not offsets or a snapshot. Concurrent additions before the
cursor may not appear, and concurrent publication/archive may change later pages.

`processor_archive({processor_id, expected_version, expected_revision})` changes
active to archived. `processor_restore` with the same argument shape changes
archived to active. Neither compiles or runs a program. The initial lifecycle
revision is 0; every actual transition increments it, independently of code
publication. Both the expected current code version and lifecycle revision must
match. Conflicts report expected/current state and direct the caller to inspect
and reconsider the operation before submitting new preconditions.

A same-state call with the current revision is a no-op: it preserves the revision
and change time. Revision 0 has no lifecycle change time (`null`); later
transitions record a timestamp. Code publication does not advance this clock.
Repeating an earlier request with its old revision fails as
stale, even if archive followed by restore returned to the same status and code
version. No transport retry token is implied. Read the current summary before
acting on an uncertain previous response. Committed lifecycle transitions are
retained in separate immutable revision records with an atomic current lifecycle
pointer; no source, version, lineage, or build artifact is deleted. Transition
events retain the code version selected at that event. API lifecycle state pairs
the last lifecycle revision/time with the current code version, so later code
publication does not rewrite old event records.

Archived identities disappear from default discovery. They remain visible with
`include_archived: true`, and `processor_get` with an exact version remains
readable. Current-version lookup, publication, new forks from that identity, and
new direct installation are rejected. Installation checks active status when it
selects a version; archival does not cancel an installation already admitted.
Running instances and existing fork identities retain their pins and behavior.
Restoring the identity makes current lookup and new use available again without
changing its current code version, immutable history, or any running graph.

An existing composition retains its exact archived dependencies and remains
readable and installable. New composition publication and new forks of
compositions require active dependencies. This keeps historical compositions
usable while preventing new authored references to archived code. Archiving a
composition itself prevents its new direct installation, while its running
instances remain unchanged. Archival never acts as garbage collection.

Programs can declare interfaces and compose exact saved versions using the same
registry and lifecycle tools; see [composition.md](composition.md).
