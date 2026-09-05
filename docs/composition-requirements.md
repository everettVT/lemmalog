# Composition and registry lifecycle acceptance

This increment composes three independently validated and exercised pure programs
into one DDlog graph. It also adds bounded registry discovery and reversible
archival. Existing shared instance ownership, standalone transport, version
identity and registered-operation contracts remain in force.

| Requirement | Executable acceptance |
|---|---|
| C1. Each leaf declares all external inputs and exported derived outputs with int/string schemas; private relation names cannot collide. | `processor_composition_registry`: namespace/literal/broadcast contract; `test-composition.py`: three leaves share local `scratch` names and run independently. |
| C2. A composed definition is an ordinary program that can itself be selected as a node. It references exact immutable versions and explicit connections, without copying authored rules; its resolved dependency closure and generated source identity are retained. | Registry exact-version/pointer-move/hash/tamper tests; real driver retains manifests, resolution, generated source and executable hashes. |
| C3. Missing connections, private endpoints, ambiguous names, multiple input writers and incompatible fields reject before publication; explicit external broadcast is supported. | Composition registry negative cases; `test_composition_mcp.py` rejection/pointer-preservation cases. |
| C4. Composition and leaf rules remain positive and nonrecursive; recursive relation dependencies, unsupported language and external-operation nodes fail clearly. Nested programs expand recursively; only cyclic definition references are unresolvable. | Lowering and composition registry tests, MCP recursion rejection, and a legal node-binding cycle with an unused port. External operations retain their standalone request/response API. |
| C5. One installation compiles one graph containing all nodes; upstream additions/retractions propagate through all three with set semantics against an independent oracle. | `test-composition.py` compiles three leaves, one initial nested program and one updated nested program sequentially; compares multiple revisions/support additions and removals against `composition_oracle.py`. |
| C6. External changes use one transaction boundary and completed queries observe its resulting graph. Clients attach independently to the same explicit owner. | Real driver transaction snapshots and independent reviewer bridge; inherited shared-owner serialization/disconnect/cleanup tests. |
| C7. Composition does not admit or replay external effects. | Registry rejects any operation-bound leaf; prior standalone registered-operation tests remain applicable. Multi-operation composition is explicitly unsupported. |
| C8. Direct witness indexes map to an exact leaf version/local rule or a generated binding; generated relation ownership is inspectable. | Registry origin assertions, MCP witness mapping contract, real driver witness read. No recursive proof claim. |
| C9. Conditional publication and forks preserve lineage; moving current pointers does not change old running pins. New composition behavior requires a new instance. | Registry CAS/fork tests and real old/new composition comparison. |
| C10. Saving validates without compilation/activation; evidence distinguishes validation, generated source, native compilation and running graph identity. | Validation metadata and no-build MCP assertions; real driver records compiler/backend/generated-program identities and activation responses. |
| D1. List/search are bounded (1–100), sorted by stable identity, use explicit keyset continuation, default active-only and optionally include archived status. Search is a defined literal case-insensitive substring. | Registry discovery/pagination/current-only-search tests and MCP discovery tests. Pagination is not a snapshot. |
| D2. Archive and restore keep the same identity, all immutable code versions, current code pointer, lineage and existing composition references; restore permits new use without compilation. No physical-delete tool. | Registry lifecycle/filesystem tests and MCP lifecycle matrix; real running graph snapshots across transitions. |
| D3. Lifecycle writes require expected code version and independent lifecycle revision. Initial revision is 0; each state transition increments it. Same-state calls at the current revision are no-ops; stale revision calls conflict, including archive/restore ABA. Committed transitions are recorded separately from definitions. | Registry revision/no-op/ABA/competing-writer tests defined before implementation, plus MCP assertions. |
| D4. Failures explain the cause, relevant current/expected values and a concrete correction/discovery action; they never authorize blind retries or automatic restoration. | Registry and MCP assertions check meaningful state/action fragments rather than exact prose. |
| S1–S3. Stable identities, immutable content versions, separate timestamps/Git metadata, conditional publication/fork lineage and automatic pure validation remain compatible. | Existing `processor_registry` known-hash/history/provenance/type tests plus composition extensions. |
| S4–S6. Explicit owner lifetime, same-user authority, no terminal sharing, failure uncertainty, instance pins and cleanup remain intact. | Existing `test_shared_host.py`, previous real shared-instance evidence, and current independent composition clients. No new durability or isolation claim. |

Lifecycle tests were specified and run against the archive-only implementation
before restore was implemented: they failed for the absent lifecycle revision and
missing follow-up action. The finalized transition contract uses
`expected_version` plus `expected_revision`; a code version alone cannot detect an
archive–restore cycle. An uncertain earlier transition must be inspected before
any new conditional request.

The runnable implementation uses existing `processor_*` tool names. A naming
migration, diagnostic endpoint, CI wiring, inventory/resource scheduling, remote
HTTP, roles, hot migration, effectful composition, arbitrary DDlog language,
and crash-durable live graphs are outside this increment. Evidence and final
results are recorded in [evidence/composition](evidence/composition/README.md).
