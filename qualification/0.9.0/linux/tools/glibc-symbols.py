#!/usr/bin/env python3
"""Inspect versioned glibc dependencies from a strictly verified Linux package."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("archive", type=Path)
parser.add_argument("--verifier", required=True, type=Path)
parser.add_argument("--report", required=True, type=Path)
args = parser.parse_args()
spec = importlib.util.spec_from_file_location("release_verifier", args.verifier)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)
manifest, contents, digest = verifier.verify(args.archive)
assert manifest["target"] == "x86_64-unknown-linux-gnu"
binaries = []
with tempfile.TemporaryDirectory(prefix="polybase-glibc-symbols-") as temporary:
    for binary in verifier.BINS:
        path = Path(temporary) / binary
        path.write_bytes(contents["bin/" + binary][0])
        versions = subprocess.check_output(["readelf", "--version-info", str(path)], text=True)
        names = sorted(set(re.findall(r"Name: (GLIBC_\S+)", versions)))
        assert names and all(re.fullmatch(r"GLIBC_[0-9]+(?:\.[0-9]+)+", name) for name in names), names
        maximum = max(tuple(map(int, name.removeprefix("GLIBC_").split("."))) for name in names)
        assert maximum <= (2, 35), (binary, maximum)
        binaries.append({"binary": binary, "max_glibc_symbol": ".".join(map(str, maximum)),
                         "versioned_requirements": names})
report = {"passed": True, "source_commit": manifest["source_commit"], "archive_sha256": digest,
          "declared_glibc_minimum": "2.35", "binaries": binaries,
          "scope": "ELF version-needs inspection; actual glibc 2.35 execution is recorded separately"}
args.report.parent.mkdir(parents=True, exist_ok=True)
args.report.write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
