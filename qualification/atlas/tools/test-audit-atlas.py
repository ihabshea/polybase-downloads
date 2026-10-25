#!/usr/bin/env python3
"""Synthetic negative controls for the independent public Atlas QA tools."""
import argparse
import copy
import gzip
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("atlas_audit", HERE / "audit-atlas-traces.py")
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)
SOURCE = "1" * 40
VERSION = "1.5.0-preview.1"
CHECKER = None


def fixture():
    left, right = list(b"pair/left"), list(b"pair/right")
    pair = [[left, [7]], [right, [7]]]
    intent = {"expected": [{"key": left, "value": None}, {"key": right, "value": None}],
              "mutations": [{"mutation": "put", "key": left, "value": [7]},
                            {"mutation": "put", "key": right, "value": [7]}]}
    operations = [
        {"id": 1, "client": 1, "node": 1, "invocation": 2, "response": 3,
         "call": {"call": "write", "request_id": "named-a", "intent": intent},
         "outcome": {"outcome": "receipt", "position": {"index": 1, "term": 1},
                     "status": "applied", "replayed": False}},
        {"id": 2, "client": 2, "node": 1, "invocation": 4, "response": 5,
         "call": {"call": "read", "mode": "quorum", "minimum": None,
                  "query": {"query": "range", "start": None, "end": None}},
         "outcome": {"outcome": "snapshot", "position": {"index": 2, "term": 1}, "rows": pair}},
        {"id": 3, "client": 3, "node": 3, "invocation": 6, "response": 7,
         "call": {"call": "read", "mode": "local", "minimum": None,
                  "query": {"query": "range", "start": None, "end": None}},
         "outcome": {"outcome": "snapshot", "position": {"index": 0, "term": 0}, "rows": []}},
    ]
    history = {"schema": 1, "engine_version": VERSION, "seed": 1, "history_id": 0,
               "profile": "loss-delay-reorder", "cluster_id": "a7" * 16,
               "membership_generation": 0, "failure_point": None, "replay_command": "synthetic-control",
               "initial": {"position": {"index": 0, "term": 0}, "rows": [], "requests": []},
               "operations": operations}
    schedule = [{"event": "cluster_configuration", "tick": 1}]
    for op in operations:
        schedule.extend([
            {"event": "client_invocation", "tick": op["invocation"], "operation": op["id"],
             "node": op["node"], "client": op["client"], "monotonic_nanos": op["invocation"] * 10,
             "call": op["call"]},
            {"event": "client_response", "tick": op["response"], "operation": op["id"],
             "monotonic_nanos": op["response"] * 10, "outcome": op["outcome"]},
        ])
    schedule.append({"event": "historical_parity", "tick": 8, "node": 1,
                     "position": {"index": 1, "term": 1},
                     "points": [[left, [7]], [right, [7]], [list(b"absent"), None]],
                     "all_paginated_rows": pair, "bounded_range_rows": pair,
                     "typed_json_n_equals_1_float": [], "text_all_atlas_shared": []})
    counts = {"client_operations": 3, "quorum_reads": 1, "local_reads": 1,
              "historical_positions": 1, "historical_point_reads": 3,
              "historical_searches": 1, "historical_pages": 3,
              "message_reorders": 0, "named_retries": 0, "unknown_writes": 0}
    return {"schema": 1, "source_sha": SOURCE, "checker": {"status": "linearizable"},
            "record": {"history": history, "spec": {"seed": 1, "history_id": 0,
                       "profile": "loss-delay-reorder"}, "schedule": schedule, "counts": counts}}


class AuditControls(unittest.TestCase):
    def test_valid_recorded_observations_and_local_prefix(self):
        _, counts, unverified = AUDIT.audit_record(fixture(), SOURCE, VERSION)
        self.assertEqual(counts["historical_positions"], 1)
        self.assertEqual(unverified, ["historical_pages", "message_reorders"])

    def test_wrong_historical_version(self):
        value = fixture()
        value["record"]["schedule"][-1]["all_paginated_rows"][0][1] = [9]
        with self.assertRaises(AUDIT.AuditError):
            AUDIT.audit_record(value, SOURCE, VERSION)

    def test_wrong_point_and_wrong_term(self):
        for field in ("point", "term"):
            value = fixture()
            event = value["record"]["schedule"][-1]
            if field == "point":
                event["points"][0][1] = [9]
            else:
                event["position"]["term"] = 2
            with self.assertRaises(AUDIT.AuditError):
                AUDIT.audit_record(value, SOURCE, VERSION)

    def test_forged_counters_and_inconclusive(self):
        value = fixture()
        value["record"]["counts"]["client_operations"] += 1
        with self.assertRaises(AUDIT.AuditError):
            AUDIT.audit_record(value, SOURCE, VERSION)
        value = fixture()
        value["checker"]["status"] = "inconclusive"
        with self.assertRaises(AUDIT.AuditError):
            AUDIT.audit_record(value, SOURCE, VERSION)

    def test_interval_and_unrecorded_call(self):
        for mode in ("interval", "missing"):
            value = fixture()
            if mode == "interval":
                value["record"]["history"]["operations"][0]["response"] += 1
            else:
                value["record"]["schedule"].pop(1)
            with self.assertRaises(AUDIT.AuditError):
                AUDIT.audit_record(value, SOURCE, VERSION)

    def test_duplicate_json_nan_bytes_ordering(self):
        for malformed in (b'{"x":1,"x":2}', b'{"x":NaN}'):
            with self.assertRaises(ValueError):
                AUDIT.strict_json(malformed)
        for invalid in ([True], [256], [-1], [1.0]):
            with self.assertRaises(AUDIT.AuditError):
                AUDIT.byte_string(invalid)
        with self.assertRaises(AUDIT.AuditError):
            AUDIT.rows([[[1], [2]], [[1], [3]]])

    def test_streaming_public_cli_and_plain_gzip(self):
        if CHECKER is None:
            self.skipTest("supply --checker to exercise persistent public CLI")
        with tempfile.TemporaryDirectory(prefix="atlas-public-qa-") as tmp:
            root = Path(tmp)
            for compressed in (False, True):
                path = root / ("input.jsonl.gz" if compressed else "input.jsonl")
                payload = json.dumps(fixture()).encode() + b"\n"
                path.write_bytes(gzip.compress(payload, mtime=0) if compressed else payload)
                report = root / ("gzip-report.json" if compressed else "plain-report.json")
                result = subprocess.run([sys.executable, str(HERE / "audit-atlas-traces.py"), str(path),
                                         "--checker", CHECKER, "--expected-source", SOURCE,
                                         "--expected-version", VERSION, "--expected-count", "1",
                                         "--report", str(report)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                saved = json.loads(report.read_text())
                self.assertTrue(saved["all_recorded_observations_consistent"])
                self.assertFalse(saved["claims"]["actual_engine_execution_verified"])

    def test_streaming_negative_count_hash_truncated_gzip_and_duplicates(self):
        if CHECKER is None:
            self.skipTest("supply --checker to exercise persistent public CLI")
        with tempfile.TemporaryDirectory(prefix="atlas-public-qa-negative-") as tmp:
            root = Path(tmp)
            payload = json.dumps(fixture()).encode() + b"\n"
            cases = [
                ("count", payload, ["--expected-count", "2"]),
                ("hash", payload, ["--sha256", "0" * 64]),
                ("duplicate", payload + payload, ["--expected-count", "2"]),
                ("truncated", gzip.compress(payload, mtime=0)[:-5], []),
            ]
            for label, data, extra in cases:
                path = root / f"{label}.jsonl"
                path.write_bytes(data)
                report = root / f"{label}-report.json"
                result = subprocess.run([sys.executable, str(HERE / "audit-atlas-traces.py"), str(path),
                                         "--checker", CHECKER, "--expected-source", SOURCE,
                                         "--expected-version", VERSION, "--expected-count", "1",
                                         "--report", str(report), *extra], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(json.loads(report.read_text())["all_recorded_observations_consistent"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--checker")
    args, rest = parser.parse_known_args()
    CHECKER = str(Path(args.checker).resolve()) if args.checker else None
    unittest.main(argv=[sys.argv[0], *rest])
