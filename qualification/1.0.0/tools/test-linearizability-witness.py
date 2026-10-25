#!/usr/bin/env python3
"""Deterministic controls for the independent successful-witness validator.

Run with: python3 -B test-linearizability-witness.py
These synthetic controls are not engine workloads or measured challenge cases.
"""
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
MODULE = Path(__file__).with_name("verify-linearizability-traces.py")
SPEC = importlib.util.spec_from_file_location("witness_validator", MODULE)
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def byte_string(value):
    return list(value.encode())


def put(key, value):
    return {"step": "put", "key": byte_string(key), "value": byte_string(value)}


def point(key, value):
    return {"step": "point", "key": byte_string(key),
            "value": None if value is None else byte_string(value)}


def operation(identity, invocation, response, position, steps, wrote=None):
    receipt = {"outcome": "committed", "position": position}
    if wrote is not None:
        receipt["wrote"] = wrote
    return {"id": identity, "client": 0, "invocation": invocation,
            "response": response, "steps": steps, "outcome": receipt}


def record(seed=7):
    mutations = [put("a", "one"), put("b", "one")]
    return {
        "schema": 1, "engine_version": "1.0.0", "source_sha": "a" * 40,
        "workload": {"spec": {"seed": seed, "operations": 4, "threads": 1}},
        "initial": {"position": 0, "rows": []},
        "operations": [operation(90, 1, 2, 1, mutations, True),
                       operation(10, 3, 4, 1, [point("a", "one"), point("b", "one")], False)],
        "linearizability": {"status": "linearizable", "witness": [90, 10], "explored": 2},
        "failure": None, "failed_audit": None,
        "visible": [{"phase": "after_operations", "expected_head": 1, "position": 1,
                     "floor": 0, "invocation": 5, "response": 6,
                     "rows": [[byte_string("a"), byte_string("one")],
                              [byte_string("b"), byte_string("one")]],
                     "events": [{"position": 1, "mutations": copy.deepcopy(mutations)}]}],
        "counts": {"operations": 2, "acknowledged_writes": 1,
                   "definite_aborts": 0, "readonly_commits": 1},
    }


class WitnessControls(unittest.TestCase):
    def rejected(self, value, reason):
        with self.assertRaisesRegex(validator.InvalidWitness, reason):
            validator.validate_record(value)

    def test_valid_witness_uses_neither_input_id_sort_nor_receipt_sort(self):
        value = record()
        value["operations"].reverse()
        actual = validator.validate_record(value)
        self.assertEqual(actual["operations"], 2)
        self.assertEqual(actual["visible_heads_checked"], 1)

    def test_false_witness_realtime_order_is_rejected(self):
        value = record()
        value["linearizability"]["witness"].reverse()
        self.rejected(value, "real-time")

    def test_duplicate_missing_and_unknown_witness_ids_are_rejected(self):
        for identities in ([90, 90], [90], [90, 999]):
            value = record()
            value["linearizability"]["witness"] = identities
            self.rejected(value, "exactly every operation ID")

    def test_lost_update_is_rejected_even_with_contiguous_receipts(self):
        value = record()
        value["initial"] = {"position": 1, "rows": [[byte_string("a"), byte_string("zero")]]}
        value["operations"] = [operation(90, 1, 9, 2, [point("a", "zero"), put("a", "one")]),
                               operation(10, 2, 8, 3, [point("a", "zero"), put("a", "two")])]
        value["visible"] = []
        value["counts"] = {}
        self.rejected(value, "point observation")

    def test_partial_batch_read_is_rejected(self):
        value = record()
        value["operations"][1]["steps"][1] = point("b", None)
        self.rejected(value, "point observation")

    def test_read_your_writes_and_expected_values_are_checked(self):
        value = record()
        value["operations"][0]["steps"].append(point("a", "wrong"))
        self.rejected(value, "point observation")
        value = record()
        value["operations"][0]["steps"].insert(0, {"step": "expect", "key": byte_string("a"),
                                                   "value": byte_string("not present")})
        self.rejected(value, "expect observation")

    def test_incorrect_wrote_flags_and_position_gaps_are_rejected(self):
        for index in (0, 1):
            value = record()
            value["operations"][index]["outcome"]["wrote"] = bool(index)
            self.rejected(value, "wrote receipt flag")
        value = record()
        value["operations"][0]["outcome"]["position"] = 2
        self.rejected(value, "receipt position")

    def test_missing_optional_wrote_flag_is_accepted(self):
        value = record()
        for item in value["operations"]:
            item["outcome"].pop("wrote")
        self.assertEqual(validator.validate_record(value)["wrote_flags_checked"], 0)

    def test_indeterminate_and_forged_abort_classifications_are_rejected(self):
        value = record()
        value["operations"][0]["outcome"] = {"outcome": "indeterminate", "reason": "CommitOutcomeUnknown"}
        self.rejected(value, "indeterminate")
        value["operations"][0]["outcome"] = {"outcome": "aborted", "reason": "CommitOutcomeUnknown"}
        self.rejected(value, "uncertain abort")

    def test_definite_abort_observations_are_provisional_noops(self):
        value = record()
        aborted = operation(50, 0, 7, 0, [point("a", "provisional nonserial bytes"), put("a", "bad")])
        aborted["outcome"] = {"outcome": "aborted", "reason": "Conflict"}
        aborted["steps"].append({"step": "range", "start": {"kind": "unbounded"},
                                 "end": {"kind": "unbounded"},
                                 "rows": [[byte_string("z"), []], [byte_string("a"), []]]})
        value["operations"].append(aborted)
        value["linearizability"]["witness"].insert(0, 50)
        value["counts"]["operations"] = 3
        value["counts"]["definite_aborts"] = 1
        self.assertEqual(validator.validate_record(value)["definite_aborts"], 1)

    def test_non_utf8_byte_range_and_initial_prefix_are_supported(self):
        value = record()
        value["initial"] = {"position": 1, "rows": [[[0], [0]], [[255], [255]]]}
        query = {"step": "range", "start": {"kind": "excluded", "key": [0]},
                 "end": {"kind": "included", "key": [255]}, "rows": [[[255], [255]]]}
        value["operations"] = [operation(90, 1, 2, 1, [query], False),
                               operation(10, 3, 4, 1, [{"step": "point", "key": [255],
                                                        "value": [255]}], False)]
        value["counts"] = {}
        value["visible"] = []
        validator.validate_record(value)
        query["end"]["kind"] = "excluded"
        self.rejected(value, "range observation")

    def test_binary_range_bounds_duplicates_and_missing_rows_are_checked(self):
        value = record()
        query = {"step": "range", "start": {"kind": "excluded", "key": byte_string("a")},
                 "end": {"kind": "included", "key": byte_string("b")},
                 "rows": [[byte_string("b"), byte_string("one")]]}
        value["operations"][1]["steps"] = [query]
        validator.validate_record(value)
        query["rows"].append(query["rows"][0])
        self.rejected(value, "range observation")
        query["rows"] = []
        self.rejected(value, "range observation")

    def test_quiescent_lost_durable_rows_and_atomic_events_are_checked(self):
        value = record()
        value["visible"][0]["rows"].pop()
        self.rejected(value, "snapshot rows")
        value = record()
        value["visible"][0]["events"][0]["mutations"].pop()
        self.rejected(value, "atomic mutation order")

    def test_model_budget_and_bool_as_integer_are_rejected(self):
        value = record()
        value["operations"][0]["steps"][0]["value"] = [0] * validator.MAX_MODEL_CHARGE
        self.rejected(value, "reference-model budget")
        value = record()
        value["operations"][0]["id"] = True
        self.rejected(value, "unsigned integer")

    def test_non_success_checker_status_cannot_pass(self):
        for status in ("inconclusive", "invalid", "violation"):
            value = record()
            value["linearizability"]["status"] = status
            self.rejected(value, "successful witness")

    def stream(self, values, compressed=False, **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            data = b"".join(json.dumps(value).encode() + b"\n" for value in values)
            payload = gzip.compress(data, mtime=0) if compressed else data
            path = Path(directory) / "trace.data"
            path.write_bytes(payload)
            answer = validator.verify_stream(path, development=True, **kwargs)
            self.assertEqual(answer["input_sha256"], hashlib.sha256(payload).hexdigest())
            return answer, data

    def test_jsonl_and_gzip_streams_have_exact_hashes_and_counts(self):
        for compressed in (False, True):
            answer, data = self.stream([record(7), record(8)], compressed,
                                       expected_sha="a" * 40, expected_version="1.0.0",
                                       expected_count=2, expected_first_seed=7)
            self.assertTrue(answer["passed"], answer)
            self.assertEqual(answer["witnesses_validated"], 2)
            self.assertEqual(answer["operations_validated"], 4)
            self.assertEqual(answer["jsonl_sha256"], hashlib.sha256(data).hexdigest())
            self.assertFalse(answer["search_performed"])
            self.assertFalse(answer["full_release_qualification_claimed"])

    def test_source_version_and_seed_drift_fail_closed(self):
        for field in ("source_sha", "engine_version", "seed"):
            second = record(8)
            if field == "seed":
                second["workload"]["spec"]["seed"] = 7
            else:
                second[field] = "b" * 40 if field == "source_sha" else "1.0.1"
            answer, _ = self.stream([record(7), second])
            self.assertFalse(answer["passed"], field)
            self.assertEqual(answer["witnesses_validated"], 1)

    def test_expected_count_and_expected_sha_are_enforced(self):
        answer, _ = self.stream([record()], expected_count=2)
        self.assertFalse(answer["passed"])
        answer, _ = self.stream([record()], expected_sha="b" * 40)
        self.assertFalse(answer["passed"])
        self.assertEqual(answer["witnesses_validated"], 0)

    def test_empty_line_limit_duplicate_fields_and_bad_gzip_fail(self):
        for data in (b"", b" " * (validator.MAX_LINE_BYTES + 1),
                     b'{"schema":1,"schema":1}\n', gzip.compress(b"{}")[0:-4]):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "trace.data"
                path.write_bytes(data)
                answer = validator.verify_stream(path)
                self.assertFalse(answer["passed"], answer)
                self.assertFalse(answer["challenge_history_count_reached"])


if __name__ == "__main__":
    unittest.main()
