#!/usr/bin/env python3
"""Run once on a disposable workspace to evaluate a named write and query resume."""
import argparse
import json
from pathlib import Path

from local_client import LocalClient, apply_page, hex_bytes, save_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:7340")
    parser.add_argument("--state-dir", type=Path, default=Path("./client-state"))
    args = parser.parse_args()
    args.state_dir.mkdir(parents=True, exist_ok=True)
    pending = args.state_dir / "pending-request.json"
    state_file = args.state_dir / "task-result.json"
    if pending.exists() or state_file.exists():
        raise SystemExit("existing client state was preserved; inspect its original request/view before a new run")
    client = LocalClient(args.base)
    snapshot = client.query("tasks/")
    rows = {row["key"]: row["value"] for row in snapshot["rows"]}
    token = snapshot["token"]
    save_json(state_file, {"rows": rows, "token": token})
    print(f"Task snapshot at #{snapshot['position']}: {len(rows)} rows")

    task_key, note_key = "tasks/stream-demo", "notes/stream-demo"
    if client.read(task_key)["value"] is not None or client.read(note_key)["value"] is not None:
        raise SystemExit("demo keys already exist; this example does not replace existing records")
    task = json.dumps({"title": "Follow live changes", "done": False}, separators=(",", ":"))
    exact = client.request([(task_key, None), (note_key, None)],
                           [(task_key, task), (note_key, "One request, two collections")])
    save_json(pending, exact)
    # If this call loses its reply, the exact submitted request stays in pending.
    receipt = client.commit(exact)
    print(f"Committed task and note together at #{receipt['position']}")
    observed = client.outcome(exact["request_token"])
    if observed["position"] != receipt["position"]:
        raise ValueError("original outcome did not match the received position")
    repeated = client.commit(exact)
    if not repeated["replayed"] or repeated["position"] != receipt["position"]:
        raise ValueError("same request did not return its original outcome")
    print("Original request replayed without a second write")

    while True:
        page = client.poll(snapshot, token)
        rows = apply_page(rows, page)
        token = page["token"]
        save_json(state_file, {"rows": rows, "token": token})
        if int(page["position"]) >= int(receipt["position"]):
            break
    if rows.get(hex_bytes(task_key)) != hex_bytes(task):
        raise ValueError("task query did not apply the committed task")
    if hex_bytes(note_key) in rows:
        raise ValueError("task query included a different collection")
    client.unsubscribe(snapshot, token)

    saved = json.loads(state_file.read_text(encoding="utf-8"))
    resumed = client.resume(saved["token"])
    next_page = client.poll(resumed, saved["token"])
    continued = apply_page(saved["rows"], next_page)
    save_json(state_file, {"rows": continued, "token": next_page["token"]})
    client.unsubscribe(resumed, next_page["token"])
    print(f"Saved task result resumed at #{next_page['position']}")
    print(f"Original outcome: #{observed['position']}; pending request kept for inspection")


if __name__ == "__main__":
    main()
