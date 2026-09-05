#!/usr/bin/env python3
"""Record agent-authored JSON-RPC calls to a real MCP stdio server.

Send one JSON object per stdin line: {"method": ..., "params": ..., "stage": ...}.
The relay supplies only transport IDs; it never generates programs or tool calls.
This targets the experimental sequential Lemmalog server, not arbitrary MCP peers.
Send {"stop": true} to finish. Operator environment configures the backend build.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class McpRelay:
    def __init__(self, binary, directory, actor, timeout=600, maximum_calls=80):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.actor = actor
        self.timeout = timeout
        self.maximum_calls = maximum_calls
        self.sequence = 0
        self.buffer = b""
        self.cleanup_observation_errors = set()
        self.started = time.monotonic()
        self.events = (self.directory / "events.jsonl").open("x")
        self.stderr = (self.directory / "server.stderr").open("xb")
        binary = Path(binary).resolve(strict=True)
        self.write({"event": "session_start", "actor": actor,
                    "binary": str(binary), "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                    "per_call_timeout_seconds": timeout, "maximum_calls": maximum_calls,
                    "model_usage": None, "model_usage_note": "Use the calling agent's own usage records; this relay makes no inference API calls."})
        self.process = subprocess.Popen(
            [str(binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self.stderr, start_new_session=True, bufsize=0,
        )
        os.set_blocking(self.process.stdin.fileno(), False)
        self.write({"event": "server_start", "pid": self.process.pid})

    def write(self, value):
        value = {"at": timestamp(), **value}
        self.events.write(json.dumps(value, sort_keys=True) + "\n")
        self.events.flush()
        os.fsync(self.events.fileno())

    def response(self, deadline):
        while b"\n" not in self.buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.process.stdout], [], [], remaining)[0]:
                raise TimeoutError("MCP response deadline exceeded")
            chunk = os.read(self.process.stdout.fileno(), 65536)
            if not chunk:
                raise RuntimeError("MCP server exited before a complete response")
            self.buffer += chunk
            if len(self.buffer) > 4 * 1024 * 1024:
                raise ValueError("MCP response exceeded 4 MiB")
        line, self.buffer = self.buffer.split(b"\n", 1)
        return json.loads(line)

    def send(self, encoded, deadline):
        pending = memoryview(encoded)
        while pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([], [self.process.stdin], [], remaining)[1]:
                raise TimeoutError("MCP write deadline exceeded")
            try:
                written = os.write(self.process.stdin.fileno(), pending)
            except BlockingIOError:
                continue
            if written == 0:
                raise BrokenPipeError("MCP input closed")
            pending = pending[written:]

    def call(self, envelope):
        if not isinstance(envelope, dict) or not isinstance(envelope.get("method"), str):
            raise ValueError("Expected a method and params object")
        if not isinstance(envelope.get("params", {}), dict):
            raise ValueError("params must be an object")
        if self.sequence >= self.maximum_calls:
            raise ValueError("Session call allowance exhausted")
        self.sequence += 1
        request = {"jsonrpc": "2.0", "id": self.sequence,
                   "method": envelope["method"], "params": envelope.get("params", {})}
        record = {"sequence": self.sequence, "actor": self.actor,
                  "stage": envelope.get("stage", "unspecified"), "request": request}
        encoded = (json.dumps(request) + "\n").encode()
        if len(encoded) > 1024 * 1024:
            raise ValueError("MCP request exceeded 1 MiB")
        started = time.monotonic()
        self.write({"event": "request", **record})
        try:
            self.send(encoded, started + self.timeout)
            response = self.response(started + self.timeout)
            if (not isinstance(response, dict) or response.get("jsonrpc") != "2.0"
                    or type(response.get("id")) is not int or response["id"] != self.sequence
                    or ("result" in response) == ("error" in response)):
                raise ValueError("MCP response does not match request")
            self.write({"event": "exchange", **record, "response": response,
                        "elapsed_seconds": time.monotonic() - started})
            return response
        except Exception as error:
            self.write({"event": "transport_failure", **record,
                        "error_type": type(error).__name__, "error": str(error),
                        "elapsed_seconds": time.monotonic() - started})
            raise

    def group_exists(self):
        self.process.poll()
        try:
            os.killpg(self.process.pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError as error:
            # macOS can report EPERM while a terminated child is being reaped.
            # An unavailable observation never establishes disappearance.
            self.cleanup_observation_errors.add(str(error))
            return None

    def wait_group(self, seconds):
        deadline = time.monotonic() + seconds
        while True:
            if self.group_exists() is False:
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(0.05, remaining))

    def close(self):
        graceful = False
        cleanup_complete = False
        signal_errors = []
        cleanup_error = None

        def signal_group(sig):
            try:
                os.killpg(self.process.pid, sig)
            except ProcessLookupError:
                pass
            except OSError as error:
                signal_errors.append({"signal": int(sig), "error": str(error)})

        try:
            try:
                self.process.stdin.close()
                self.process.wait(timeout=5)
                graceful = True
            except (BrokenPipeError, subprocess.TimeoutExpired):
                pass
            # Include compiler/runtime descendants even if the MCP parent exited early.
            signal_group(signal.SIGTERM)
            if not self.wait_group(2):
                signal_group(signal.SIGKILL)
            cleanup_complete = self.wait_group(2)
            self.process.wait(timeout=2)
        except Exception as error:
            cleanup_error = str(error)
        finally:
            self.process.stdout.close()
            try:
                self.write({"event": "session_end", "calls": self.sequence,
                            "server_exit_code": self.process.returncode, "graceful": graceful,
                            "process_group_gone": cleanup_complete,
                            "cleanup_observation_errors": sorted(self.cleanup_observation_errors),
                            "cleanup_signal_errors": signal_errors, "cleanup_error": cleanup_error,
                            "elapsed_seconds": time.monotonic() - self.started})
            finally:
                self.events.close()
                self.stderr.close()
        if not cleanup_complete or cleanup_error:
            raise RuntimeError("MCP process-group cleanup could not be confirmed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--actor", required=True, help="Calling agent identity; provenance label, not authentication")
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--maximum-calls", type=int, default=80)
    args = parser.parse_args()
    if args.timeout <= 0 or args.maximum_calls <= 0:
        parser.error("Limits must be positive")
    def cancelled(signum, frame):
        raise KeyboardInterrupt("Relay terminated")

    signal.signal(signal.SIGTERM, cancelled)
    relay = McpRelay(args.binary, args.session, args.actor, args.timeout, args.maximum_calls)
    print(json.dumps({"ready": True, "session": str(relay.directory)}), flush=True)
    try:
        for line in sys.stdin:
            if not line.strip():
                continue
            envelope = json.loads(line)
            if envelope == {"stop": True}:
                break
            print(json.dumps(relay.call(envelope)), flush=True)
    finally:
        relay.close()


if __name__ == "__main__":
    main()
