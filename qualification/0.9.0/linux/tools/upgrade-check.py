#!/usr/bin/env python3
"""Deterministic extracted-package upgrade/downgrade fixture; no engine source needed."""
import argparse
import importlib.util
import json
from pathlib import Path
import platform
import subprocess
import tempfile

OLD_SHA = "dbec2441bde1cb880c931459ff8b23c14aa68accb5fcb154d587ede00a88eb10"
OLD_SOURCE = "2a8fd5c95ade14b05be9cfd66c419c0d68b6500f"


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-package", required=True, type=Path)
    parser.add_argument("--new-package", required=True, type=Path)
    parser.add_argument("--old-verifier", required=True, type=Path)
    parser.add_argument("--new-verifier", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    old = module("old_release_verifier", args.old_verifier)
    new = module("new_release_verifier", args.new_verifier)
    old_manifest, old_files, old_hash = old.verify(args.old_package, OLD_SHA)
    new_manifest, new_files, new_hash = new.verify(args.new_package)
    assert old_manifest["source_commit"] == OLD_SOURCE and old_manifest["version"] == "0.8.2"
    assert new_manifest["version"] == "0.9.0" and new_manifest["source_dirty"] is False
    checks = []
    with tempfile.TemporaryDirectory(prefix="polybase-janus-upgrade-") as temporary:
        root = Path(temporary)
        stages = []
        for name, contents in [("old", old_files), ("new", new_files)]:
            stage = root / name
            for path, (data, mode) in contents.items():
                file = stage / path
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(data)
                file.chmod(mode)
            stages.append(stage)
        before, after = stages
        db = root / "database"

        def cli(stage, *arguments):
            return subprocess.check_output([str(stage / "bin/polybase"), *map(str, arguments)],
                                           text=True, timeout=20)

        key = lambda value: value.encode().hex()
        cli(before, "init", db)
        values = {}
        for start in range(0, 100, 32):
            batch = []
            for i in range(start, min(100, start + 32)):
                number = (1.0 if i % 20 else 1) if i % 10 == 0 else 2
                value = json.dumps({"n": number})
                values[f"upgrade/{i:03}"] = value
                batch += ["put", f"upgrade/{i:03}", value]
            cli(before, "batch", db, *batch)
        query = {"key_prefix": key("upgrade/"), "predicate": "json", "value": "",
                 "json": {"op": "eq", "path": ["n"], "value": 1}}
        body = {"query": query, "cursor": None, "limit": 128}
        with old.console(before, db) as base:
            old.api(base, "/api/index-create", {"name": "upgrade-number", "prefix": list(b"upgrade/"), "path": ["n"]})
            reference = old.api(base, "/api/query-page", body)
            first = old.api(base, "/api/query-page", {**body, "limit": 3})
            session = old.api(base, "/api/query", query)
            old_revision = old.api(base, "/api/read-revision", {"key": key("upgrade/010")})["revision"]
            token = old.api(base, "/api/request", {})["request_token"]
            intent = {"request_token": token,
                      "reads": [{"key": key(k), "value": key(values[k])} for k in ["upgrade/030", "upgrade/099"]],
                      "mutations": [{"key": key("upgrade/030"), "value": key('{"n":2}')},
                                    {"key": key("upgrade/099"), "value": key('{"n":1.0}')}]}
            # The application discards this acknowledgment, then reconciles under 0.9.
            old.api(base, "/api/commit", intent)
            assert len(reference["rows"]) == 10 and first["next"]
        with new.console(after, db) as base:
            current = new.api(base, "/api/query-page", body)
            forced = new.api(base, "/api/query-page", {**body, "force_scan": True})
            assert current["rows"] == forced["rows"] and len(current["rows"]) == 10
            at = new.api(base, "/api/as-of-query", {**body, "position": reference["position"]})
            assert at["rows"] == reference["rows"] and at["position"] == reference["position"]
            continued = new.api(base, "/api/query-page", {**body, "cursor": first["next"]})
            assert continued["rows"] == reference["rows"][3:] and continued["position"] == first["position"]
            checks.append("0.9 reads published 0.8.2 WAL/index definitions, typed numeric results and historical cursor without drift")
            outcome = new.api(base, "/api/outcome", {"token": token})
            retry = new.api(base, "/api/commit", intent)
            assert retry["replayed"] and retry["position"] == outcome["position"] == current["position"]
            assert new.api(base, "/api/health")["head"] == current["position"]
            checks.append("discarded 0.8.2 named acknowledgment reconciles and retries under 0.9 without a second commit")
            resumed = new.api(base, "/api/resume", {"token": session["token"]})
            delta = new.api(base, "/api/poll", {**resumed, "token": session["token"]})
            assert len(delta["commits"]) == 1 and len(delta["commits"][0]["changes"]) == 2
            changes = delta["commits"][0]["changes"]
            assert [c["key"] for c in changes] == [key("upgrade/030"), key("upgrade/099")]
            assert changes[0]["after"] is None and changes[1]["before"] is None
            resume_after = delta["token"]
            new.api(base, "/api/unsubscribe", {**resumed, "token": resume_after})
            checks.append("0.8.2 subscription resumes the complete ordered two-key transaction under 0.9")
            new.api(base, "/api/write-revision", {"revision": old_revision, "value": key('{"n":7}')})
            new.api(base, "/api/write-revision", {"revision": old_revision, "value": key('{"n":8}')}, expected=409)
            latest = new.api(base, "/api/query-page", body)
            assert len(latest["rows"]) == 9
            assert new.api(base, "/api/as-of-query", {**body, "position": current["position"]})["rows"] == current["rows"]
            new.api(base, "/api/checkpoint", {})
            checks.append("old revision tokens preserve stale-write rejection and 0.9 checkpoint retains the original historical answer")
        with old.console(before, db) as base:
            assert old.api(base, "/api/query-page", body)["rows"] == latest["rows"]
            assert old.api(base, "/api/query-page", {**body, "cursor": first["next"]})["rows"] == reference["rows"][3:]
            assert old.api(base, "/api/commit", intent)["position"] == current["position"]
            resumed = old.api(base, "/api/resume", {"token": resume_after})
            delta = old.api(base, "/api/poll", {**resumed, "token": resume_after})
            assert len(delta["commits"]) == 1 and len(delta["commits"][0]["changes"]) == 1
            assert delta["commits"][0]["changes"][0]["key"] == key("upgrade/010")
            old.api(base, "/api/unsubscribe", {**resumed, "token": delta["token"]})
            revision = old.api(base, "/api/read-revision", {"key": key("upgrade/020")})["revision"]
            old.api(base, "/api/write-revision", {"revision": revision, "value": key('{"n":8}')})
            old.api(base, "/api/checkpoint", {})
            checks.append("0.8.2 reopens 0.9 checkpoint/WAL, retries the original request, resumes a 0.9 cursor and writes normally")
        assert cli(before, "events", db, 0, 32) == cli(after, "events", db, 0, 32)
        checks.append("old and new CLI expose exactly identical ordered commit events after bidirectional writes")
        with new.console(after, db) as base:
            assert len(new.api(base, "/api/query-page", body)["rows"]) == 8
            assert new.api(base, "/api/as-of-query", {**body, "position": reference["position"]})["rows"] == reference["rows"]
            new.api(base, "/api/compact", {"position": reference["position"]})
            assert new.api(base, "/api/as-of-query", {**body, "position": reference["position"]})["rows"] == reference["rows"]
            new.api(base, "/api/compact", {"position": current["position"]})
            assert new.api(base, "/api/as-of-query", {**body, "position": reference["position"]}, expected=410)["code"] == "history_expired"
            assert new.api(base, "/api/query-page", {**body, "cursor": first["next"]}, expected=410)["code"] == "history_expired"
        with old.console(before, db) as base:
            assert old.api(base, "/api/query-page", {**body, "cursor": first["next"]}, expected=410)["code"] == "history_expired"
            assert len(old.api(base, "/api/query-page", body)["rows"]) == 8
        checks.append("compaction preserves the retained floor answer and both versions explicitly reject expired old cursors")
    report = {"passed": True, "fixture": "deterministic 100-record bidirectional upgrade", "platform": platform.platform(),
              "old_source": old_manifest["source_commit"], "new_source": new_manifest["source_commit"],
              "old_archive_sha256": old_hash, "new_archive_sha256": new_hash, "checks": checks}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
