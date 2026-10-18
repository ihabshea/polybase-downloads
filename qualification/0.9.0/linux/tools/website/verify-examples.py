#!/usr/bin/env python3
"""Run documentation examples against the actual extracted evaluation executables."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_verifier", ROOT / "scripts/verify-release.py")
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    manifest, contents, digest = verifier.verify(args.package)
    client_env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    cases = []
    with tempfile.TemporaryDirectory(prefix="polybase-documentation-") as temporary:
        stage = Path(temporary)
        for name, (data, mode) in contents.items():
            file = stage / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(data)
            file.chmod(mode)
        cli = stage / "bin/polybase"
        def run(*arguments):
            return subprocess.check_output([str(cli), *map(str, arguments)], text=True, timeout=20)
        db = stage / "learning-db"
        assert run("init", db) == "initialized head=0\n"
        assert run("put", db, "tasks/1", '{"title":"Write a note","done":false}') == "committed 1\n"
        assert run("get", db, "tasks/1") == '{"title":"Write a note","done":false}\n'
        assert run("batch", db, "put", "notes/1", "A first note", "put", "sensors/room-a",
                   '{"temperature":21.5,"unit":"C"}') == "committed 2\n"
        assert "snapshot 2" in run("snapshot", db)
        assert run("batch", db, "put", "tasks/1", '{"title":"Write a note","done":true}',
                   "put", "notes/1", "The task is complete") == "committed 3\n"
        assert "next=3 head=3" in run("events", db, 2, 10)
        cases.append("tutorial CLI commands, exact output, cross-collection batch and event boundary")
        with verifier.console(stage, db) as base:
            stdout = subprocess.check_output(["python3", str(ROOT / "website/public/examples/live-workspace.py"),
                "--base", base, "--state-dir", str(stage / "client-state")], text=True, timeout=90, env=client_env)
            assert "Committed task and note together at #4" in stdout
            assert "Original request replayed without a second write" in stdout
            assert "Saved task result resumed at #4" in stdout
            saved = json.loads((stage / "client-state/task-result.json").read_text())
            exact = json.loads((stage / "client-state/pending-request.json").read_text())
            assert "7461736b732f73747265616d2d64656d6f" in saved["rows"]
            assert verifier.api(base, "/api/outcome", {"token": exact["request_token"]})["position"] == "4"
            # A second run must not overwrite the saved submitted request or view.
            before = (stage / "client-state/pending-request.json").read_bytes()
            repeated = subprocess.run(["python3", str(ROOT / "website/public/examples/live-workspace.py"),
                "--base", base, "--state-dir", str(stage / "client-state")], capture_output=True, text=True, timeout=20, env=client_env)
            assert repeated.returncode != 0 and "preserved" in repeated.stderr
            assert (stage / "client-state/pending-request.json").read_bytes() == before
            verifier.api(base, "/api/close", {})
        assert "snapshot 4" in run("snapshot", db)
        cases.append("runnable Python client, exact-request replay, one-file result/cursor resume and existing-state refusal")

        reference = stage / "reference-db"
        run("init", reference)
        assert run("batch", reference, "put", "tasks/1", "open", "put", "notes/1", "A first note") == "committed 1\n"
        assert run("batch", reference, "put", "tasks/1", "done", "delete", "notes/1") == "committed 2\n"
        assert "snapshot 2" in run("snapshot", reference)
        assert run("get", reference, "notes/1") == "(absent)\n"
        run("put", reference, "settings/theme", '{"name":"paper","contrast":"normal"}')
        run("batch", reference, "put", "tasks/view-demo", '{"title":"Try a view","done":false}',
            "put", "views/open-tasks/view-demo", '{"title":"Try a view","done":false}')
        run("batch", reference, "put", "tasks/view-demo", '{"title":"Try a view","done":true}',
            "delete", "views/open-tasks/view-demo")
        assert run("get", reference, "views/open-tasks/view-demo") == "(absent)\n"
        cases.append("CLI reference, JSON replacement, deletion and application-maintained view")
        with verifier.console(stage, reference) as base:
            def curl(route, body=None):
                command = ["curl", "--disable", "-fsS", "--http1.1", "-H", "Content-Type: application/json", "-H", "Origin: " + base]
                if body is not None:
                    command += ["--data", json.dumps(body)]
                return json.loads(subprocess.check_output([*command, base + "/api/" + route], text=True, timeout=20))
            assert curl("health")["head"] == "5"
            assert curl("read", {"key": "7461736b732f31"})["value"] == "646f6e65"
            snapshot = curl("query", {"key_prefix": "7461736b732f", "predicate": "any", "value": ""})
            assert len(snapshot["rows"]) == 2
            curl("unsubscribe", {key: snapshot[key] for key in ["id", "instance", "token"]})
            assert curl("checkpoint", {})["floor"] == "0"
            verifier.api(base, "/api/close", {})
        cases.append("copyable curl health/read/query/checkpoint examples with exact Origin")
        backup = stage / "reference-db-backup"
        # Linux and macOS both support the documented cp -a operation.
        subprocess.run(["cp", "-a", str(reference), str(backup)], check=True, timeout=20)
        assert run("get", backup, "tasks/1") == "done\n"
        assert "snapshot 5" in run("snapshot", backup)
        cases.append("closed-directory backup and reopened record/history verification")
    report = {"passed": True, "target": manifest["target"], "source_commit": manifest["source_commit"],
              "package_sha256": digest, "cases": cases}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
