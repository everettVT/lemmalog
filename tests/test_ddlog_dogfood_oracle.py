"""Run with: python3 -m unittest discover -s tests -p test_ddlog_dogfood_oracle.py"""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ddlog_dogfood_oracle.py"
SPEC = importlib.util.spec_from_file_location("ddlog_dogfood_oracle", SCRIPT)
oracle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(oracle)


def change(predicate, values, op="insert"):
    return {"op": op, "predicate": predicate, "values": values}


class FactOracleTests(unittest.TestCase):
    def setUp(self):
        self.facts = oracle.FactOracle({
            "revision": [[1, 7]],
            "finding": [[1, 7, 10, 2]],
            "support": [[1, 7, 10, 100], [1, 7, 10, 200]],
        })

    def test_alternative_support_then_final_support_retraction(self):
        self.assertEqual(self.facts.expected(2), {(1, 10)})
        self.facts.apply([change("support", [1, 7, 10, 100], "delete")])
        self.assertEqual(self.facts.expected(2), {(1, 10)})
        self.facts.apply([change("support", [1, 7, 10, 200], "delete")])
        self.assertEqual(self.facts.expected(2), set())

    def test_duplicates_are_sets_and_missing_delete_is_noop(self):
        item = change("support", [1, 7, 10, 100])
        self.facts.apply([item, item, change("support", [1, 7, 10, 999], "delete")])
        self.assertEqual(len(self.facts.snapshot()["support"]), 2)
        self.facts.apply([change("support", [1, 7, 10, 100], "delete"),
                          change("support", [1, 7, 10, 200], "delete")])
        self.assertEqual(self.facts.expected(2), set())
        constructed = oracle.FactOracle({"revision": [[1, 7], [1, 7]]})
        self.assertEqual(constructed.snapshot()["revision"], [[1, 7]])

    def test_stale_revision_and_join_keys_do_not_leak_support(self):
        self.facts.apply([
            change("finding", [1, 6, 11, 1]), change("support", [1, 6, 11, 100]),
            change("finding", [1, 7, 12, 1]), change("support", [2, 7, 12, 100]),
            change("finding", [1, 7, 13, 1]), change("support", [1, 6, 13, 100]),
        ])
        self.assertEqual(self.facts.expected(2), {(1, 10)})
        self.facts.apply([change("revision", [1, 7], "delete"), change("revision", [1, 6])])
        self.assertEqual(self.facts.expected(2), {(1, 11)})

    def test_multiple_revisions_and_findings_are_existential_not_upserts(self):
        self.facts.apply([
            change("revision", [1, 8]), change("finding", [1, 8, 10, 1]),
            change("support", [1, 8, 10, 300]), change("finding", [1, 7, 10, 5]),
        ])
        self.assertEqual(self.facts.expected(2), {(1, 10)})
        self.facts.apply([change("revision", [1, 7], "delete")])
        self.assertEqual(self.facts.expected(2), {(1, 10)})
        self.facts.apply([change("revision", [1, 8], "delete")])
        self.assertEqual(self.facts.expected(2), set())

    def test_threshold_changes_reuse_retained_facts(self):
        self.facts.apply([change("finding", [1, 7, 11, 3]),
                          change("support", [1, 7, 11, 100])])
        before = self.facts.snapshot()
        self.assertEqual(self.facts.expected(2), {(1, 10)})
        self.assertEqual(self.facts.expected(3), {(1, 10), (1, 11)})
        self.assertEqual(self.facts.expected(1), set())
        self.assertEqual(self.facts.snapshot(), before)

    def test_int64_extremes_and_detached_snapshot(self):
        low, high = oracle.MIN_I64, oracle.MAX_I64
        facts = oracle.FactOracle({"revision": [[low, high]],
                                   "finding": [[low, high, high, low]],
                                   "support": [[low, high, high, low]]})
        self.assertEqual(facts.expected(low), {(low, high)})
        snapshot = facts.snapshot()
        snapshot["revision"].clear()
        self.assertEqual(facts.expected(low), {(low, high)})

    def test_bad_batch_is_rejected_atomically(self):
        bad_changes = [
            change("missing", [1, 2]), change("actionable", [1, 2]),
            change("revision", [1, 7], "update"), change("revision", [1]),
            change("revision", [1, 7, 8]), change("revision", (1, 7)),
            {"op": "insert", "predicate": "revision"},
            {**change("revision", [1, 7]), "extra": 1},
            change([], [1, 2]), None,
        ]
        bad_changes.extend(change("revision", [1, value]) for value in
                           [True, False, 1.0, "1", None, [], {}, oracle.MIN_I64 - 1,
                            oracle.MAX_I64 + 1])
        original = self.facts.snapshot()
        for invalid in bad_changes:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    self.facts.apply([change("revision", [1, 7], "delete"), invalid])
                self.assertEqual(self.facts.snapshot(), original)
        for invalid in (None, {}, (), ""):
            with self.assertRaises(ValueError):
                self.facts.apply(invalid)

    def test_bad_initial_facts_and_thresholds_are_rejected(self):
        for facts in ([], {"unknown": []}, {"revision": {}}, {"revision": [[True, 1]]}):
            with self.subTest(facts=facts), self.assertRaises(ValueError):
                oracle.FactOracle(facts)
        for threshold in (True, 2.0, "2", None, oracle.MAX_I64 + 1):
            with self.subTest(threshold=threshold), self.assertRaises(ValueError):
                self.facts.expected(threshold)


class ParserTests(unittest.TestCase):
    ROW = "R_actionable{.f0 = 1, .f1 = 10}"

    def test_rows_and_deltas_select_only_actionable(self):
        self.assertEqual(oracle.parse_rows(""), set())
        self.assertEqual(oracle.parse_deltas(""), {})
        self.assertEqual(oracle.parse_rows(self.ROW + "\n"), {(1, 10)})
        self.assertEqual(oracle.parse_rows(self.ROW + "\nR_eligible{.f0 = 1, .f1 = 7, .f2 = 10}\n"),
                         {(1, 10)})
        dump = ("Evidence0:\nEvidence0{.v_F = 10, .v_P = 1, .v_R = 7}: -1\n"
                "R_eligible:\nR_eligible{.f0 = 1, .f1 = 7, .f2 = 10}: -1\n"
                f"R_actionable:\n{self.ROW}: -1\n"
                "R_actionable_extra:\nR_actionable_extra{.f0 = 2}: +1\n")
        self.assertEqual(oracle.parse_deltas(dump), {(1, 10): -1})
        self.assertEqual(oracle.parse_deltas("Evidence1:\nEvidence1{.v_Source = 2}: -1\n"), {})

    def test_signed_extremes_and_string_in_ignored_relation(self):
        row = f"R_actionable{{.f0 = {oracle.MIN_I64}, .f1 = {oracle.MAX_I64}}}"
        self.assertEqual(oracle.parse_rows(row), {(oracle.MIN_I64, oracle.MAX_I64)})
        self.assertEqual(oracle.parse_deltas('Evidence0:\nEvidence0{.v_S = "a, \\\"b\\\""}: +2\n'), {})

    def test_malformed_noncanonical_and_duplicate_rows_fail_closed(self):
        invalid = [
            self.ROW + "\n" + self.ROW, self.ROW + " garbage", " " + self.ROW,
            self.ROW + " ", self.ROW + ": +1", "R_actionable:", "garbage",
            "R_actionable{.f1 = 10, .f0 = 1}", "R_actionable{.f0 = 1}",
            "R_actionable{.f0 = 1, .f1 = 10, .f2 = 0}",
            "R_actionable{.f0 = 1, .f0 = 10}", "R_actionable{.f0=1, .f1 = 10}",
            "R_actionable{.f0 = 1, .f1 = 10, }", "R_actionable{}", "\n", self.ROW + "\n\n",
            self.ROW + "\r\n", "Unknown{.f0 = 1}", "Evidence0{broken}",
        ]
        invalid.extend(f"R_actionable{{.f0 = {value}, .f1 = 10}}" for value in
                       ["01", "-0", "+1", "1.0", '"1"', "true", str(oracle.MAX_I64 + 1)])
        for text in invalid:
            with self.subTest(text=text), self.assertRaises(ValueError):
                oracle.parse_rows(text)
        with self.assertRaises(ValueError):
            oracle.parse_rows(None)

    def test_delta_sections_unit_weights_and_uniqueness_are_strict(self):
        valid = f"R_actionable:\n{self.ROW}: +1\n"
        self.assertEqual(oracle.parse_deltas(valid), {(1, 10): 1})
        invalid = [
            f"{self.ROW}: +1", "R_actionable:\n", valid + f"{self.ROW}: -1\n",
            valid + f"{self.ROW}: +1\n", valid + valid,
            f"Evidence0:\n{self.ROW}: +1\n", f"R_actionable:\n{self.ROW}\n",
            "Evidence0:\ninvalid\n", "R_eligible:\nR_actionable:\n" + self.ROW + ": +1\n",
        ]
        invalid.extend(f"R_actionable:\n{self.ROW}: {weight}\n" for weight in
                       ["+2", "-2", "+0", "-0", "1", "+01", "+1 ", "1.0"])
        for text in invalid:
            with self.subTest(text=text), self.assertRaises(ValueError):
                oracle.parse_deltas(text)


class CommandLineTests(unittest.TestCase):
    def test_check_reports_success_exact_mismatch_and_parse_error(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            facts, rows, previous, deltas = [base / name for name in
                                            ("facts.json", "rows.txt", "previous.json", "delta.txt")]
            facts.write_text(json.dumps({"revision": [[1, 7]], "finding": [[1, 7, 10, 2]],
                                        "support": [[1, 7, 10, 9]]}))
            rows.write_text(ParserTests.ROW + "\n")
            previous.write_text("{}")
            deltas.write_text("R_actionable:\n" + ParserTests.ROW + ": +1\n")
            command = [sys.executable, str(SCRIPT), "check", "--facts", str(facts),
                       "--threshold", "2", "--rows", str(rows), "--previous-facts", str(previous),
                       "--deltas", str(deltas)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["expected_deltas"], [[1, 10, 1]])
            deltas.write_text("")
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertFalse(json.loads(result.stdout)["ok"])
            rows.write_text("garbage")
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("Malformed DDlog record", result.stderr)
            facts.write_text('{"revision": [], "revision": []}')
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("Duplicate JSON key", result.stderr)


if __name__ == "__main__":
    unittest.main()
