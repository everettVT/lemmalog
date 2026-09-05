# Large-Star / Small-Star acceptance

This follow-up targets exact minimum-label connected components through the
existing MCP and ordinary program registry. It does not substitute reachability,
generic label propagation, or an external Python computation for the named
algorithm.

| Requirement | Executable verification | Result |
| --- | --- | --- |
| Exact alternating Large-Star then Small-Star inside one real DDlog/Differential graph | `scripts/test-large-small-star.py`; retained generated source, bundled native implementation and executable hashes; independent source review | Passed, fresh native compilation in the final run |
| Read complete output, merge components by inserting a bridge, split by deleting the final bridge support | Same driver, exact row comparisons and positive/negative output deltas | Passed |
| Explicit isolated vertices, signed IDs, self-loops, reverse/duplicate support, implicit endpoints and withdrawals | Independent BFS `scripts/connected_components_oracle.py`, 10 focused oracle tests, native mutation trace | Passed |
| Removing a minimum vertex and incident edges raises surviving labels; repeated changes cannot retain stale connectivity | Native minimum-removal case, relabelled path, 80 deterministic updates, complete retraction | Passed; 98 native output snapshots total |
| Shared owner and ordinary immutable program semantics, independent pipe clients, reconnect and explicit cleanup | Native driver registers a leaf and wrapper, pins the wrapper, uses two independent bridge processes, reconnects and stops | Passed |
| Pure save-time validation with actionable type/reference errors; no compile/start on registration | `tests/star_registry.rs` | Passed, 5 tests |
| Ordinary nested/repeated composition, namespaced operator references, exact dependency versions, unchanged rule witness indexes | `tests/star_registry.rs` plus existing `tests/processor_composition_registry.rs` | Passed |
| Existing definition hashes and registry lifecycle behavior stay compatible | `tests/processor_registry.rs`, operator legacy-hash check | Passed, 17 existing registry tests |
| Both direct and saved-program tool schemas expose the same typed field; unsupported native code and external-operation mixing reject explicitly | MCP unit tests in `src/ddlog/mcp.rs` | Passed |
| Existing host and composition MCP contracts remain valid | `tests/test_shared_host.py`, `tests/test_composition_mcp.py` using simulated graph fixtures | Passed, 13 + 6 tests; not native graph evidence |
| Vetted native implementations require versioned code updates and dedicated tests; interactive authors only configure known operators | Tagged typed operator schema and unknown-native-field rejection tests; backend, native source and executable hashes in evidence | Passed for this bundled implementation |
| Sandboxed native development/execution context | Current worktree/private-directory isolation inspected | **Not enforced as an OS security sandbox**; native child runs with host-user privileges |

The first native run passed its 97 graph comparisons and stopped cleanly, then
failed while the driver copied evidence from an incorrect build-directory path.
That failed receipt and log are retained. The corrected final driver discovers
the single generated source under the instance directory and adds the explicit
minimum-vertex removal case. It completed a second fresh native build, all 98
comparisons, hash verification, and cleanup with exit zero. This was a test-harness
failure; no production change or transparent retry occurred between native runs.

See [the evidence record](evidence/large-small-star/README.md) for raw/sanitized
provenance and the separate-agent author/reviewer exercise.

Unmet/out of scope: general recursion or aggregate syntax, arbitrary native
plugins, registered external-operation combination, benchmark/scalability
guarantees, persistent live state, remote transports and CI workflow wiring.
OS native-code sandbox enforcement is a documented current gap. Program content
versions and backend/native implementation hashes are distinct identities.
