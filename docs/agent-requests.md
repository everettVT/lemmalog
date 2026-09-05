# Registered agent requests

An operator registers an agent operation; a program author selects it and writes
rules over `agent_result(entity: string, revision: int, output: string)`. The
adapter creates the request, claim, response, and freshness relations. Authors
do not generate ad hoc inference calls inside Datalog evaluation.

Set `LEMMALOG_AGENT_OPERATIONS` to an operator-owned JSON file:

```json
{"review":{"version":"v1","description":"Review a text payload"}}
```

The initial signature is string payload -> string result. The registry does not
contain credentials and does not execute a provider. An external worker uses
the claim and completion tools to invoke the selected provider. These tools are
trusted within one MCP session, not a multi-tenant authorization system.

With a registry configured the server additionally exposes:

- `agent_operations`: discover names, versions and signature.
- `install_agent_program`: select an operation and install user rules/schemas.
- `submit_agent_input`: supply entity, nonnegative revision, and payload.
- `claim_agent_request`: admit a current request once in this session.
- `complete_agent_request`: record the corresponding worker output.
- `agent_request_status`: inspect identity, freshness, and lifecycle status.

For example, the installation arguments are:

```json
{
  "operation":"review",
  "rules":"reviewed(E,R,O) :- agent_result(E,R,O).",
  "schemas":{"reviewed":{"input":false,"fields":["string","int","string"]}}
}
```

User rules cannot write registered relations, read private operation relations,
or mutate them through `apply_changes`. They may consume `agent_result` and
compose it with their own typed relations. Ordinary sessions without a registry
retain the original experimental four-tool interface.

## Identity and lifecycle

Request identity is a canonical JSON tuple of operation name, registered version,
entity, revision, and exact payload. It is not a randomized hash or a sequence
counter. It can be large because it contains the payload; treat IDs as data, not
secret-free log labels. Same-revision payload changes are rejected. Revisions
cannot move backwards for an entity. Duplicate input is a set-semantic no-op.

A committed submission creates a pending relation row. Claiming commits an
`agent_claimed` input and removes pending membership, adding running membership.
Only then is admission returned to the worker. Duplicate claims are rejected.
Completion records the response, removes running membership, and produces a
current result only if the request still matches the entity's current identity.
A delayed old response is retained but never joins current outputs.

Repeated identical completion is acknowledged without reinserting the response;
a different completion for the same request is rejected. Advancing revision
retracts the former current output through Differential. A newly installed
operation version participates in identity; changing the registry takes effect
in a new session. Registered programs cannot be replaced after input admission
in this initial implementation.

## Execution and recovery boundaries

The worker executes outside DDlog. Claim-once means this server does not admit a
second execution of the same request in the session. It is not a guarantee of
provider-side exactly-once effects. A worker already admitted can still execute
after the entity advances; freshness protects result visibility, not the outside
world. There is no automatic claim expiry, timeout retry, or replay of uncertain
external actions.

State and claims are session-local. A process restart does not recover them.
Production recovery needs durable claims and provider reconciliation before
resubmission; callers must not turn a restart into an unconditional retry. Runtime
failure prevents successful new admission and requires reconciliation. Compiler
and runtime timeouts, cancellation, durable export, and generalized operation
signatures remain follow-ups.

## Verification

`scripts/test-agent-requests.py` drives actual MCP requests through the Rust
server, official DDlog compiler, and generated Differential/Timely executable.
The external worker is deliberately mocked and labeled in the output. The test
covers stable identity, conflicting revisions, pending/running transitions,
duplicate claims, stale completions, current completions, duplicate/conflicting
responses, blocked protocol bypass, output retraction, stale admission rejection,
and entity isolation. It uses the same build environment as `docs/ddlog.md`.

This establishes the registered lowering and lifecycle boundary. Actual
model-authored tool calls are being dogfooded separately; this test is not an LLM
benchmark or evidence of successful live inference.
