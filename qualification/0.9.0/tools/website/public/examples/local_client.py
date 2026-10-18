#!/usr/bin/env python3
"""A standard-library evaluation client for the local Polybase console."""
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request


class ApiError(RuntimeError):
    def __init__(self, status, body):
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status}: {body.get('code', 'error')}: {body.get('message', '')}")


def save_json(path, value):
    """Save one complete client state object, not separate result/token files."""
    path = Path(path)
    temporary = path.with_name(path.name + ".next")
    with temporary.open("x", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write("\n")
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def hex_bytes(value):
    if isinstance(value, str):
        value = value.encode("utf-8")
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise TypeError("encode application values as text or bytes first")
    return bytes(value).hex()


class LocalClient:
    def __init__(self, base="http://127.0.0.1:7340"):
        self.base = base.rstrip("/")
        parsed = urllib.parse.urlsplit(self.base)
        if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1"
                or parsed.port is None or parsed.path or parsed.query or parsed.fragment
                or parsed.username or parsed.password):
            raise ValueError("use the console's exact http://127.0.0.1:PORT origin")
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def call(self, route, body=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(self.base + "/api/" + route, data=data,
            headers={"Content-Type": "application/json", "Origin": self.base})
        try:
            with self.opener.open(request, timeout=10) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            with error:
                raise ApiError(error.code, json.load(error)) from error

    def health(self):
        return self.call("health")

    def read(self, key):
        return self.call("read", {"key": hex_bytes(key)})

    def query(self, prefix="", predicate="any", value=""):
        return self.call("query", {"key_prefix": hex_bytes(prefix),
                                  "predicate": predicate, "value": hex_bytes(value)})

    def request(self, expected, mutations):
        token = self.call("request", {})["request_token"]
        def entry(item):
            key, value = item
            return {"key": hex_bytes(key), "value": None if value is None else hex_bytes(value)}
        return {"request_token": token, "reads": [entry(item) for item in expected],
                "mutations": [entry(item) for item in mutations]}

    def commit(self, exact_request):
        return self.call("commit", exact_request)

    def outcome(self, token):
        return self.call("outcome", {"token": token})

    def poll(self, session, token):
        return self.call("poll", {"id": session["id"], "instance": session["instance"], "token": token})

    def resume(self, token):
        return self.call("resume", {"token": token})

    def unsubscribe(self, session, token):
        return self.call("unsubscribe", {"id": session["id"], "instance": session["instance"], "token": token})


def apply_page(rows, page):
    """Validate and apply all changes before publishing a new client result."""
    updated = dict(rows)
    for commit in page["commits"]:
        for change in commit["changes"]:
            key = change["key"]
            if updated.get(key) != change["before"]:
                raise ValueError("saved result does not match this cursor; obtain a fresh query")
            if change["after"] is None:
                updated.pop(key, None)
            else:
                updated[key] = change["after"]
    return updated
