# Connected components with Large-Star / Small-Star

An ordinary program can declare a typed `large_small_star` operator. The compiler
places it inside the same DDlog/Differential graph as the program's rules and
composition bindings. Registration validates the relation references and types;
installation performs native compilation and activation. Existing processor
identity, immutable versions, interfaces, composition, archive/restore and live
instance pinning apply unchanged.

```json
{
  "rules": "",
  "schemas": {
    "vertices": {"input": true, "fields": ["int"]},
    "edges": {"input": true, "fields": ["int", "int"]},
    "labels": {"input": false, "fields": ["int", "int"]}
  },
  "operators": [
    {"type": "large_small_star", "vertices": "vertices", "edges": "edges", "output": "labels"}
  ],
  "interface": {"inputs": ["vertices", "edges"], "outputs": ["labels"]}
}
```

Pass this definition to `processor_create`, then select the returned exact
reference with `processor_install` in a fresh instance. `lemmalog_install_rules`
also accepts `operators` for standalone programs. The `rules` field may be empty
when an operator supplies the computation. Omitted or empty `operators` preserves
existing definition hashes. Callers choose supported operators and typed relation
names; they cannot submit native code or select build paths.

Each vertex ID is a signed 64-bit integer. The vertex universe is the union of
explicit `vertices` and all `edges` endpoints. This makes an explicit isolated
vertex produce `(v,v)` and lets an edge introduce its endpoints. Removing an
explicit vertex while incident edges remain keeps that vertex present. Removing
the final support for an implicit endpoint removes it. A self-loop introduces a
singleton vertex but does not enter star contraction.

Edges represent undirected connectivity. Input facts keep the existing set
semantics: repeating `(u,v)` is idempotent, but `(u,v)` and `(v,u)` are distinct
input facts. Deleting one orientation preserves the other as support. The result
contains exactly one `(vertex, minimum_vertex_in_component)` row per vertex.

For vertices `1,2,3,4,9` and edges `(1,2),(3,4)`, querying `labels` returns
`(1,1),(2,1),(3,3),(4,3),(9,9)`. An `apply_changes` transaction inserting `(2,3)`
changes the rows for `3,4` to component `1`. Deleting that bridge restores
component `3`. Reads occur after the completed transaction has reached its fixed
point; the client does not drive the algorithm's iterations.

## Algorithm and lowering

The algorithm comes from Kiveris et al.,
[Connected Components in MapReduce and Beyond (2014)](https://research.google/pubs/connected-components-in-mapreduce-and-beyond/).
The phase formulas were checked against the official
[GraphFrames implementation](https://github.com/graphframes/graphframes/blob/master/core/src/main/scala/org/graphframes/lib/TwoPhase.scala#L293-L314):

1. Large-star groups symmetric neighbors around each center `u`, finds the
   minimum of that neighborhood including `u`, and connects every neighbor
   greater than `u` to that minimum.
2. Small-star orients the resulting edges from larger to smaller, groups the
   smaller neighbors, and connects both their center and each nonminimum neighbor
   to the group's minimum. Retaining the center is essential.
3. Both phases replace and deduplicate the edge set. They alternate until the
   complete edge set stops changing. Final stars and vertex self-labels produce
   the minimum representative for every vertex.

The implementation uses Differential's `Iterate` and keyed `Reduce`/`distinct`.
Its feedback consolidates cancelling differences and preserves DDlog's `Weight`
type. Original inputs enter the iteration's source; changes to that source are
propagated through the iterative computation, including removals. It does not
restart from only the previous contracted edges. See the
[Differential iteration implementation](https://github.com/TimelyDataflow/differential-dataflow/blob/v0.12.0/src/operators/iterate.rs).

This is a supported native compiler primitive. The ordinary rule subset still
rejects general recursion and aggregates. Merely allowing both would be
incorrect here because [DDlog disallows grouped aggregation inside a recursive
dependency cycle](https://github.com/vmware-archive/differential-datalog/blob/master/doc/language_reference/language_reference.md#constraints-on-dependency-graph).
DDlog's existing `graph::ConnectedComponents` uses a different propagation
implementation and is not called by this operator.

Operator inputs may be declared input or derived relations with the required
types. The output must be derived. Operators participate in ordinary dependency
validation; they cannot introduce unsupported cycles between relations.
Composition namespaces all three references, including repeated and nested uses.
Ordinary rules can consume the operator result or add results to the same output
relation. `lemmalog_why` retains its ordinary-rule indexing; native operators do
not manufacture `Evidence` rows or recursive proofs.

The program content version identifies authored rules, schemas and operator
configuration. It is distinct from the backend/operator implementation identity.
Versioned repository changes supply the bundled implementation; the server's
binary hash and the native declaration/implementation hashes identify the exact
code used in verification. The generated source contains the latter hashes.
The build directory includes those exact files alongside
`program.dl`, the native executable, and the build log. The operator uses the
installed compiler's implementation; this is not a user-supplied plugin system.
Running instances keep their loaded executable when registry pointers move.
When using an operator-supplied offline `DDLOG_CARGO_LOCK`, its path-workspace
packages must include `types__lemmalog_star`. The verification run updated the local workspace entries and dependency edges
for that module with offline Cargo; no third-party dependency changed.

Adding another native operator is a versioned repository/code-review change with
dedicated semantic and integration tests. Interactive authors can only select
and configure vetted operators. The intended development boundary also requires
a sandboxed context for developing and executing new native code. The current
host does **not** enforce an OS native-code sandbox: this work used an isolated
checkout and private build/socket directories, but the native child still runs
with the host user's privileges. Those directories provide operational
separation, not security isolation. Runtime sandbox enforcement remains an
explicit gap rather than a guarantee of this API.

## Boundaries and verification

The implementation has no arbitrary fixed number of rounds. It inherits the
local host's memory/process lifetime and transaction behavior. This change does
not add distributed execution, durable live facts, arbitrary native code,
general recursive aggregation, or performance claims for large graphs. Combining
typed operators with a registered external operation is explicitly unsupported
in this increment; use a pure program for the graph.

[Acceptance requirements and evidence](large-small-star-requirements.md) distinguish
the real native graph exercise from registry/unit tests and simulated-runtime
compatibility tests. The independent oracle uses breadth-first search and no
production compiler or star-contraction code.
