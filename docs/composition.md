# Compose immutable processors in one graph

A composition selects exact saved processor versions and connects their declared
interfaces. Installing it compiles one DDlog program and starts one Differential
Dataflow graph. An external fact transaction crosses all connected processors
before the next query completes. There are no independently ticking child
instances, cross-process fact copies, or provider calls during graph evaluation.

Use the existing [host, registry, and stdio tools](shared-instances.md). Create
and validate each program, run it independently with fixtures, then save a fourth
processor whose definition is a composition manifest. Saving performs syntax,
type, interface, dependency and supported-lowering checks without invoking the
native compiler or starting a graph. `processor_install` compiles and activates
an exact version in a fresh instance.

## Declare each program's interface

Schemas remain the source of field types. An explicit interface lists every input
and the derived relations consumers may read. Other derived relations are private
implementation details. For example:

```json
{
  "rules": "scratch(P,R,F) :- finding(P,R,F,S), S =< 2. eligible(P,R,F) :- scratch(P,R,F).",
  "schemas": {
    "finding": {"input": true, "fields": ["int", "int", "int", "int"]},
    "scratch": {"input": false, "fields": ["int", "int", "int"]},
    "eligible": {"input": false, "fields": ["int", "int", "int"]}
  },
  "interface": {"inputs": ["finding"], "outputs": ["eligible"]}
}
```

Pass this as `definition` to `processor_create`. Independently installing this
version permits mutations of `finding` and queries of `eligible`. `scratch` is
not addressable by the ordinary fact tools. `lemmalog_why` still exposes direct
rule-variable witnesses: this interface boundary is not a confidentiality
boundary between trusted clients. Old definitions without an interface retain
their existing behavior and content hashes; composition requires explicit
interfaces on every selected program.

## Connect exact versions

This shortened two-node example shows the manifest shape; the executable
[three-program fixture](evidence/composition/fixture.json) adds the support join.
Replace the illustrative identities and versions with actual create results.

```json
{
  "composition": {
    "nodes": {
      "severity": {"processor_id": "processor_<id>", "version": "sha256:<version>"},
      "current": {"processor_id": "processor_<id>", "version": "sha256:<version>"}
    },
    "inputs": {
      "findings": {
        "fields": ["int", "int", "int", "int"],
        "targets": [{"node": "severity", "relation": "finding"}]
      },
      "current_revisions": {
        "fields": ["int", "int"],
        "targets": [{"node": "current", "relation": "current"}]
      }
    },
    "bindings": [{
      "from": {"node": "severity", "relation": "eligible"},
      "to": {"node": "current", "relation": "eligible"}
    }],
    "outputs": {"selected": {"node": "current", "relation": "selected"}}
  }
}
```

The manifest is source-construction syntax: it contains references and bindings,
not copies of the selected rules. Its result is an ordinary program with the same
registry identity, versioning, activation, querying and lifecycle operations.
Composition provenance is metadata, not a separate kind of running object.
An individually authored or composed program can be selected as a node through
the same interface. Every node input has exactly one source: an external input or an exported output
of another node. An external input's `targets` explicitly broadcasts its fact set
to multiple inputs. A producer may feed several consumers. Multiple writers to
one input, implicit unions, private output bindings, missing inputs, input/output
name ambiguity and arity/type mismatches are rejected before publication.
After source expansion, the ordinary program lowerer validates the resulting
rules. A cycle between node bindings is not independently forbidden: an unused
input can make such a connection cycle computationally acyclic. Actual recursive
relation dependencies remain outside the current ordinary compiler subset. Ordering or renaming manifest arrays can change its content version;
JSON object insertion order does not.

Use external names in the combined instance's ordinary tools:

```json
{"changes": [{"op": "insert", "predicate": "findings", "values": [1, 3, 7, 2]}]}
```

`lemmalog_query` accepts only exported external output names. Rows and mutation
deltas use these public names; deltas omit private relations and witnesses.
Private predicates receive deterministic per-node names in the parsed AST.
String literals and variables are not rewritten. Inputs between nodes become
ordinary derived relations linked by rules in the same graph.

## Inspect the selected graph

The saved version's `composition` metadata retains the exact node references,
generated source SHA-256, external-to-generated relation maps, relation origins,
and rule origins. `processor_get` checks immutable content hashes and recomputes
this resolution, including its generated source hash. Changed or missing retained
dependencies fail explicitly. Nested definitions are recursively expanded;
`composition.nodes` holds immediate references and `composition.dependencies`
holds the full exact closure using dot-separated node paths. Cyclic immutable
definition references cannot be resolved. Expansion guards of 128 nested levels
and 4096 expanded nodes bound stack and memory amplification and report how to
simplify the submitted construction.

The installation result and `instance_info` include the resolved composition.
For `lemmalog_why`, each combined rule index corresponds to an entry in
`composition.rules`. Its returned `origin` identifies either a processor's exact
version and local rule index, an external input binding, a processor connection,
or an output export. Generated `EvidenceN` corresponds to rule index `N`;
`composition.relations` maps generated `R_<name>` relations to their owning
processor or public port. Witnesses describe direct variable bindings, not
recursive proof trees or confidence provenance.

Publishing a new leaf version does not rewrite a composition. Publish a new
composition manifest with its expected current version to select different leaf
versions, then install it in a new instance. An already running graph retains its
old composition version and dependency closure. Composition versions use the
same conditional publication and fork lineage as ordinary program versions.

## Scope and failure behavior

The supported rules are the existing typed, positive, nonrecursive subset:
`int` and `string` fields, positive joins and supported comparisons. Negation,
aggregates, arithmetic, clock builtins and recursion remain unsupported. The
same ordinary lowerer validates individually authored and expanded programs;
there is no additional prohibition on cycles between node bindings.

Processors selecting external operations cannot be composed in this increment.
They remain independently installable with the existing explicit input, claim,
completion and freshness tools. Routing multiple operation identities and
request/response relations through one composed owner requires a separate
contract; no provider work is implied or replayed by composition.

All clients of an instance have equal same-OS-user authority. The host serializes
fact transactions, queries and installation. Registry compare-and-swap applies to
version publication; fact writes do not have a stale-state check. Bridge loss
leaves the graph alive, but a lost mutation reply is an uncertain result and is
never transparently retried. Process failure loses live facts and claims; saved
definitions are not a durable graph checkpoint. Operator stop and cleanup retain
the [existing owner lifecycle](shared-instances.md).

Generated source, native executable, build log, and installation attempt are
retained under the operator's configured build root. A saved definition reports
`ddlog_compilation_performed: false`; a successful installation is the separate
activation result. Native compiler/runtime and executable identities are recorded
by the acceptance driver, not inferred from successful pure validation. There is
no new diagnostic endpoint, runtime inventory/resource controller, CI workflow,
remote transport, role model, live graph migration, or connector in this change.

The current acceptance fixture exercises three joins/filters, not a connected-
components algorithm. LARGE-STAR/SMALL-STAR execution is not implemented or
validated by this change; its recursive aggregation and iterative execution
requirements need a separate compiler/runtime assessment.
