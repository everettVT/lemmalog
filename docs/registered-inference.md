# External inference for a registered program

The Python worker in [`scripts/lemmalog_inference_worker.py`](../scripts/lemmalog_inference_worker.py)
connects to an existing shared program instance through its own stdio bridge.
It validates the operation binding, claims each supplied request, invokes the
configured provider outside DDlog, and completes the request with the exact text
response. The graph exposes current results through
`agent_result(entity, revision, output)` and can join them with ordinary inputs.
The Rust server and its MCP tools are unchanged.

This is an explicit finite worker invocation, not a background scheduler.
Submitting input does not itself call the model. An operator starts the worker
with selected request IDs. Its library API separates `dispatch()` from `settle()`
so a controller can retain a completed response before inserting it into the
graph; `run()` performs both steps.

## Configuration and identity

[`examples/registered-inference.json`](../examples/registered-inference.json)
is the public configuration used by the acceptance run. The endpoint requires
the operator's existing Modal authentication. Configure an endpoint you are
authorized to use; this file grants no access and contains no credentials.

Configuration includes operation name, endpoint, model, system prompt, token
allowance, sampling and reasoning settings. Canonical JSON with materialized
defaults determines a SHA-256 operation version. Changing any setting creates a
different operation version. The host operation registry and immutable saved
program must contain the exact generated binding. For example:

```python
import json
import sys
from pathlib import Path
sys.path.insert(0, "scripts")
from lemmalog_inference_worker import InferenceConfig

config = InferenceConfig.load("examples/registered-inference.json")
Path("operations.json").write_text(json.dumps(config.operation_registry()))
print(json.dumps(config.operation_binding()))
```

Set `LEMMALOG_AGENT_OPERATIONS` to that operator-owned file before starting the
[shared host](shared-instances.md). Save a program through `processor_create`
using `operation: config.operation_binding()`, its authored rules and typed
schemas, then compile/activate the returned exact version with
`processor_install`. The acceptance driver contains a complete example using
`reviewed(E,R,O) :- agent_result(E,R,O)` and an ordinary owner join.

The worker reads `instance_info`, the exact `processor_get` version, and
`agent_operations` before admission. They must agree with its configuration.
Before settlement it checks that the instance and installed version still
match. Configuration hash, program content version, live instance ID, backend
binary hash and compiled graph artifact hash are distinct identities.

## Invocation

Use Python 3.11 or later and an already authenticated Modal CLI. After an author
submits input using `submit_agent_input`, pass the exact returned request ID:

```sh
python3 scripts/lemmalog_inference_worker.py \
  --config examples/registered-inference.json \
  --binary target/debug/lemmalog-ddlog-mcp \
  --descriptor /path/to/instance.json \
  --modal-bin /path/to/modal \
  --request-id 'EXACT_REQUEST_ID_FROM_SUBMIT' \
  --max-concurrency 2 \
  --receipt /path/to/worker-receipt.json
```

Request IDs contain the exact payload; they are not secret-free identifiers.
Consider shell history and receipt permissions for private workloads. This
example uses synthetic public text only. The worker sends request JSON on the
Modal CLI's stdin and inherits its operator authentication; it never extracts
or records credentials. Provider output stays a string, not executable code.

At most the configured number of provider requests run concurrently. Requests
are claimed before their provider call. One request produces one attempt; there
are no automatic retries of provider calls or uncertain MCP mutations. Receipt
metadata records configuration and request/response digests, provider model and
response IDs, usage and finish reason, without a reasoning transcript. Incomplete
generations and unsupported response shapes are rejected. If the provider
returned text but settlement fails, the receipt retains that exact prepared
response for operator reconciliation; it does not automatically resubmit it.
Local timeout cleanup terminates the worker's Modal/curl process group, which
does not establish cancellation at the remote provider.

## Boundaries and verification

The endpoint/model name does not identify immutable weights. A pinned
configuration records the requested behavior, not reproducibility or provider
exactly-once execution. Authenticated same-user MCP clients retain equal full
access; claims do not authenticate the completing worker. A stale admitted
request can still finish externally, but its response cannot replace a newer
current result. Claims/results are session-local, with no durable queue, lease,
cancellation or automatic recovery. A worker failure can leave a claimed request
that requires explicit operator reconciliation. Native processes and the
provider CLI run with operator privileges; no OS security sandbox is added.

[`inference-requirements.md`](inference-requirements.md) defines the contracts and
test mapping. Unit tests use controlled providers and MCP doubles. The separate
`scripts/test-registered-inference.py --real-provider` driver requires the normal
DDlog build environment and invokes the configured provider exactly twice. It
holds revision 1 outside the graph, settles revision 2 first, inserts revision 1
late, checks duplicate/conflicting settlement, and changes ordinary owner facts.
Complete output relations are compared with an independent set/join oracle
using the actual response text. It is not an inference quality benchmark.
The [recorded real run](evidence/registered-inference/README.md) passed all seven
output comparisons with two actual provider responses; 22 focused unit tests
passed separately using controlled providers and MCP doubles where needed.
