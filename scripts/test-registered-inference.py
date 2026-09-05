#!/usr/bin/env python3
"""Two REAL provider calls and one REAL DDlog graph; explicit operator opt-in.

Use INFERENCE_CONFIG, LEMMALOG_DDLOG_MCP, LEMMALOG_DDLOG_BUILD and the
supported native build environment. Requires --real-provider to spend calls.
INFERENCE_ARTIFACTS retains raw receipts and native source/build/executable.
"""
import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import traceback

from inference_oracle import expected, rows
from lemmalog_inference_worker import InferenceConfig, InferenceWorker, MCPPipe, ProviderClient

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('shared', HERE / 'test-shared-instance.py')
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)
ARTIFACTS = Path(os.environ.get('INFERENCE_ARTIFACTS') or tempfile.mkdtemp(prefix='inference-proof-'))
ARTIFACTS.mkdir(parents=True, exist_ok=True)
receipt = {'passed': False, 'backend': 'official DDlog / Differential Dataflow',
           'provider': 'actual external Modal endpoint', 'server_sha256': shared.BINARY_SHA256,
           'checks': [], 'rpc': [], 'provider_calls': [], 'snapshots': []}


def digest(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class RecordedClient:
    def __init__(self, client, role):
        self.client, self.role = client, role

    async def call(self, name, arguments=None):
        event = {'client': self.role, 'tool': name, 'arguments': arguments or {}}
        receipt['rpc'].append(event)
        try:
            event['result'] = await self.client.call(name, arguments or {})
            return event['result']
        except Exception as error:
            event['error'] = str(error)
            raise


class CountedProvider:
    def __init__(self, provider):
        self.provider, self.calls, self.inflight = provider, 0, 0
        self.started = asyncio.Event()

    async def infer(self, payload):
        assert self.calls < 2, 'Acceptance permits exactly two provider calls; no retry'
        self.calls += 1
        event = {'ordinal': self.calls, 'payload': payload,
                 'started_at': datetime.now(timezone.utc).isoformat()}
        receipt['provider_calls'].append(event)
        print(json.dumps({'provider_call': self.calls, 'state': 'started'}), flush=True)
        started = time.monotonic()
        self.inflight += 1
        self.started.set()
        try:
            result = await self.provider.infer(payload)
            event['result'] = asdict(result)
            return result
        except Exception as error:
            event['error'] = str(error)
            raise
        finally:
            self.inflight -= 1
            event['elapsed_seconds'] = round(time.monotonic() - started, 3)
            print(json.dumps({'provider_call': event['ordinal'], 'state': 'failed' if 'error' in event else 'completed',
                              'elapsed_seconds': event['elapsed_seconds']}), flush=True)


async def rejects(client, name, arguments, cause):
    try:
        await client.call(name, arguments)
    except Exception as error:
        assert cause.lower() in str(error).lower(), str(error)
        return str(error)
    raise AssertionError(name + ' unexpectedly succeeded')


async def observe(client, phase, current, responses, owners):
    oracle = expected(current, responses, owners)
    snapshot = {'phase': phase, 'relations': {}}
    for predicate in ['reviewed', 'routed']:
        result = await client.call('lemmalog_query', {'predicate': predicate})
        actual = rows(result['rows'], predicate)
        assert actual == oracle[predicate], {'phase': phase, 'predicate': predicate,
                                            'actual': actual, 'expected': oracle[predicate]}
        snapshot['relations'][predicate] = {'actual': sorted(actual), 'expected': sorted(oracle[predicate])}
    receipt['snapshots'].append(snapshot)


async def run(root):
    config = InferenceConfig.load(os.environ.get('INFERENCE_CONFIG', str(HERE.parent / 'examples/registered-inference.json')))
    receipt['configuration'] = config.public_dict()
    receipt['config_sha256'] = config.config_sha256
    receipt['operation'] = config.operation_binding()
    operations = root / 'operations.json'
    operations.write_text(json.dumps(config.operation_registry()))
    env = dict(os.environ, LEMMALOG_PROCESSOR_REGISTRY=str(root / 'registry'),
               LEMMALOG_AGENT_OPERATIONS=str(operations))
    host = shared.Host(root, 1, env)
    pipes = []
    pending = None
    try:
        author_pipe = await MCPPipe.connect(shared.BINARY, host.descriptor)
        pipes.append(author_pipe)
        worker_pipe = await MCPPipe.connect(shared.BINARY, host.descriptor)
        pipes.append(worker_pipe)
        author, worker_client = RecordedClient(author_pipe, 'author'), RecordedClient(worker_pipe, 'worker')
        definition = {'operation': config.operation_binding(),
                      'rules': 'reviewed(E,R,O) :- agent_result(E,R,O).\nrouted(E,R,O,T) :- agent_result(E,R,O), owner(E,T).',
                      'schemas': {'owner': {'input': True, 'fields': ['string', 'string']},
                                  'reviewed': {'input': False, 'fields': ['string', 'int', 'string']},
                                  'routed': {'input': False, 'fields': ['string', 'int', 'string', 'string']}},
                      'interface': {'inputs': ['owner'], 'outputs': ['reviewed', 'routed']}}
        receipt['definition'] = definition
        registered = await author.call('processor_create', {'definition': definition})
        assert registered['validation']['types_checked']
        assert not registered['validation']['ddlog_compilation_performed']
        pin = {key: registered[key] for key in ['processor_id', 'version']}
        receipt['processor'] = pin
        await author.call('processor_install', pin)
        print(json.dumps({'native_graph': 'compiled_and_installed', 'processor': pin}), flush=True)
        provider = CountedProvider(ProviderClient(config, modal_bin=os.environ.get('MODAL_BIN', 'modal')))
        worker = InferenceWorker(config, worker_client, provider, max_concurrency=2)
        receipt['binding'] = await worker.bind()
        assert receipt['binding']['processor'] == pin
        assert receipt['binding']['instance_id'] == host.identity
        receipt['checks'].append('I1_exact_config_operation_program_instance_binding')
        current, responses, owners = {}, {}, {'item': {'team-blue'}}
        await author.call('apply_changes', {'changes': [{'op': 'insert', 'predicate': 'owner', 'values': ['item', 'team-blue']}]})
        first_payload = json.dumps({'revision': 1, 'item': 'synthetic delivery note', 'text': 'Package A is awaiting review.'}, sort_keys=True)
        first = (await author.call('submit_agent_input', {'entity': 'item', 'revision': 1, 'payload': first_payload}))['request_id']
        current['item'] = (1, first)
        pending = asyncio.create_task(worker.dispatch(first))
        await asyncio.wait_for(provider.started.wait(), timeout=30)
        assert provider.inflight == 1
        # The author can query the running graph while the independent worker
        # awaits HTTP. These RPCs would hang if provider work held the host lock.
        await observe(author, 'provider_call_1_inflight', current, responses, owners)
        held = await pending
        pending = None
        receipt['held_revision_1'] = asdict(held)
        assert provider.calls == 1 and held.output
        await rejects(author, 'claim_agent_request', {'request_id': first}, 'already claimed or completed')
        assert provider.calls == 1
        await observe(author, 'response_1_held_outside_graph', current, responses, owners)
        receipt['checks'].append('I2_I3_independent_client_graph_responsive_claim_once_before_provider')
        second_payload = json.dumps({'revision': 2, 'item': 'synthetic delivery note', 'text': 'Package A is approved for dispatch.'}, sort_keys=True)
        second = (await author.call('submit_agent_input', {'entity': 'item', 'revision': 2, 'payload': second_payload}))['request_id']
        current['item'] = (2, second)
        fresh = await worker.dispatch(second)
        receipt['revision_2'] = asdict(fresh)
        assert fresh.output and provider.calls == 2
        second_completion = await worker.settle(fresh)
        assert second_completion['fresh'] and not second_completion['duplicate']
        responses[second] = fresh.output
        await observe(author, 'revision_2_completed_first', current, responses, owners)
        stale_completion = await worker.settle(held)
        assert not stale_completion['fresh'] and not stale_completion['duplicate']
        responses[first] = held.output
        await observe(author, 'revision_1_completed_late', current, responses, owners)
        status = await author.call('agent_request_status')
        assert status['durability'] == 'session-local'
        states = {item['request_id']: item for item in status['requests']}
        assert states[first]['status'] == states[second]['status'] == 'completed'
        assert states[first]['fresh'] is False and states[second]['fresh'] is True
        receipt['checks'].append('I4_two_actual_responses_latest_visible_stale_retained')
        assert (await worker.settle(held))['duplicate']
        assert (await worker.settle(fresh))['duplicate']
        await rejects(author, 'complete_agent_request', {'request_id': second, 'output': fresh.output + ' conflicting'}, 'conflicting completion')
        await rejects(author, 'claim_agent_request', {'request_id': second}, 'already claimed or completed')
        await observe(author, 'duplicate_completion_unchanged', current, responses, owners)
        receipt['checks'].append('I5_duplicate_completion_idempotent_conflict_and_duplicate_claim_rejected')
        await author.call('apply_changes', {'changes': [
            {'op': 'delete', 'predicate': 'owner', 'values': ['item', 'team-blue']},
            {'op': 'insert', 'predicate': 'owner', 'values': ['item', 'team-green']}]})
        owners['item'] = {'team-green'}
        await observe(author, 'ordinary_owner_change_no_inference', current, responses, owners)
        assert provider.calls == 2
        receipt['checks'].append('I6_ordinary_input_rederives_exact_text_without_third_provider_call')
        assert (await author.call('instance_info'))['processor'] == pin
        # Closing and reconnecting a client does not drop the retained results.
        await author_pipe.close()
        pipes.remove(author_pipe)
        reconnected = await MCPPipe.connect(shared.BINARY, host.descriptor)
        pipes.append(reconnected)
        await observe(RecordedClient(reconnected, 'author_reconnected'), 'author_reconnected', current, responses, owners)
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        errors = []
        for pipe in pipes:
            try:
                await pipe.close()
            except Exception as error:
                errors.append(str(error))
        try:
            host.stop()
        except Exception as error:
            errors.append(str(error))
        receipt['cleanup_errors'] = errors
        assert not errors, errors
    sources = list((host.directory / 'build').rglob('program.dl'))
    assert len(sources) == 1, sources
    build = sources[0].parent
    retained = ARTIFACTS / 'native-build'
    retained.mkdir(exist_ok=True)
    receipt['build'] = {}
    for filename in ['program.dl', 'program_cli', 'build.log']:
        source, target = build / filename, retained / filename
        # One local native binary is enough: hard-link the retained artifact.
        if filename == 'program_cli':
            os.link(source, target)
        else:
            shutil.copyfile(source, target)
        receipt['build'][filename] = {'sha256': digest(source), 'bytes': source.stat().st_size}
    receipt['native_builds'] = 1
    assert not host.socket.exists() and not host.descriptor.exists()
    receipt['checks'].append('I8_one_native_graph_two_provider_calls_bounded_cleanup')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--real-provider', action='store_true', required=True,
                        help='Authorize this driver to invoke the configured provider exactly twice')
    parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix='lminfer-', dir='/tmp'))
    implementation = ['lemmalog_inference_worker.py', 'inference_oracle.py', 'test-registered-inference.py']
    receipt['implementation_sha256'] = {name: digest(HERE / name) for name in implementation}
    try:
        asyncio.run(run(root))
        assert digest(shared.BINARY) == shared.BINARY_SHA256, 'Backend changed during acceptance'
        assert receipt['implementation_sha256'] == {name: digest(HERE / name) for name in implementation}, 'Worker or acceptance code changed during the run'
        receipt['passed'] = True
    except BaseException:
        receipt['error'] = traceback.format_exc()
        raise
    finally:
        # Host construction can fail after spawning; cover that path as well as
        # the normal async run cleanup without leaving an owner behind.
        cleanup_errors = receipt.setdefault('cleanup_errors', [])
        for host in shared.hosts:
            if not host.log.closed:
                try:
                    host.stop()
                except Exception as error:
                    cleanup_errors.append(str(error))
        if cleanup_errors:
            receipt['passed'] = False
        receipt['raw_directory'] = str(root)
        (ARTIFACTS / 'real-backend-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps({'passed': receipt['passed'], 'checks': receipt['checks'],
                          'provider_calls': len(receipt['provider_calls']), 'snapshots': len(receipt['snapshots']),
                          'receipt': str(ARTIFACTS / 'real-backend-receipt.json')}))
