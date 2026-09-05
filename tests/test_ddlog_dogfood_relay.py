import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/ddlog_dogfood.py"
SPEC = importlib.util.spec_from_file_location("dogfood_relay", SCRIPT)
relay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(relay)


class RelayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def binary(self, body):
        path = self.root / "server"
        path.write_text(f"#!{sys.executable}\n" + body)
        path.chmod(0o755)
        return path

    def test_records_real_transport_and_preserves_tool_error(self):
        binary = self.binary('''import json, sys
for line in sys.stdin:
    request = json.loads(line)
    print(json.dumps({"jsonrpc":"2.0", "id":request["id"],
                      "result":{"isError":True,"content":[]}}), flush=True)
''')
        client = relay.McpRelay(binary, self.root / "session", "fixture", timeout=1)
        try:
            result = client.call({"method": "tools/call", "params": {"name": "invalid"}, "stage": "repair"})
            self.assertTrue(result["result"]["isError"])
        finally:
            client.close()
        events = [json.loads(line) for line in (self.root / "session/events.jsonl").read_text().splitlines()]
        exchange = next(row for row in events if row["event"] == "exchange")
        self.assertEqual(exchange["actor"], "fixture")
        self.assertEqual(exchange["request"]["params"]["name"], "invalid")
        self.assertTrue(events[-1]["process_group_gone"])

    def test_write_timeout_includes_nonreading_child(self):
        client = relay.McpRelay(self.binary("import time; time.sleep(30)\n"), self.root / "session", "fixture", timeout=0.1)
        started = time.monotonic()
        try:
            with self.assertRaises(TimeoutError):
                client.call({"method": "tools/call", "params": {"large": "x" * 900000}})
            self.assertLess(time.monotonic() - started, 2)
        finally:
            client.close()

    def test_partial_response_times_out(self):
        client = relay.McpRelay(self.binary('''import sys,time
sys.stdin.readline()
sys.stdout.write('{"jsonrpc":'); sys.stdout.flush(); time.sleep(30)
'''), self.root / "session", "fixture", timeout=0.1)
        try:
            with self.assertRaises(TimeoutError):
                client.call({"method": "tools/list"})
        finally:
            client.close()

    def test_cleanup_kills_descendant_after_parent_exit(self):
        pid_file = self.root / "descendant.pid"
        child = f"import os,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); open({str(pid_file)!r},'w').write(str(os.getpid())); time.sleep(30)"
        binary = self.binary(f"import subprocess,sys,time\nsubprocess.Popen([sys.executable,'-c',{child!r}])\ntime.sleep(0.1)\n")
        client = relay.McpRelay(binary, self.root / "session", "fixture", timeout=1)
        client.process.wait(timeout=2)
        self.assertTrue(pid_file.exists())
        client.close()
        self.assertFalse(client.group_exists())

    def test_sigterm_cleans_separate_server_process_group(self):
        binary = self.binary("import sys\nfor line in sys.stdin: pass\n")
        proc = subprocess.Popen([sys.executable, str(SCRIPT), "--binary", str(binary),
                                 "--session", str(self.root / "session"), "--actor", "fixture"],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            self.assertTrue(json.loads(proc.stdout.readline())["ready"])
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=8)
            events = [json.loads(line) for line in (self.root / "session/events.jsonl").read_text().splitlines()]
            self.assertEqual(events[-1]["event"], "session_end")
            self.assertTrue(events[-1]["process_group_gone"])
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                stream.close()

    def test_transient_eperm_does_not_mean_gone(self):
        client = relay.McpRelay(self.binary("pass\n"), self.root / "session", "fixture")
        client.process.wait(timeout=2)
        with patch.object(os, "killpg", side_effect=[PermissionError("probe unavailable"), ProcessLookupError()]):
            self.assertTrue(client.wait_group(0.5))
        self.assertEqual(client.cleanup_observation_errors, {"probe unavailable"})
        client.close()

    def test_persistent_eperm_records_unconfirmed_cleanup_and_closes_streams(self):
        client = relay.McpRelay(self.binary("pass\n"), self.root / "session", "fixture")
        client.process.wait(timeout=2)  # No real child remains; inject observation/signal failures.
        started = time.monotonic()
        with patch.object(os, "killpg", side_effect=PermissionError("unavailable")):
            with self.assertRaisesRegex(RuntimeError, "could not be confirmed"):
                client.close()
        self.assertLess(time.monotonic() - started, 6)
        event = json.loads((self.root / "session/events.jsonl").read_text().splitlines()[-1])
        self.assertFalse(event["process_group_gone"])
        self.assertEqual(event["server_exit_code"], 0)
        self.assertEqual(event["cleanup_observation_errors"], ["unavailable"])
        self.assertEqual([row["signal"] for row in event["cleanup_signal_errors"]],
                         [signal.SIGTERM, signal.SIGKILL])
        self.assertTrue(client.events.closed and client.stderr.closed and client.process.stdout.closed)


if __name__ == "__main__":
    unittest.main()
