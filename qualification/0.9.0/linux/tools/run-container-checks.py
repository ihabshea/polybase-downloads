#!/usr/bin/env python3
"""Execute package/HTTP acceptance on native x86-64 Ubuntu 22.04 with no egress."""
import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--new-package", required=True, type=Path)
parser.add_argument("--old-package", required=True, type=Path)
parser.add_argument("--report-dir", required=True, type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parent
args.report_dir.mkdir(parents=True, exist_ok=True)
glibc = subprocess.check_output(["getconf", "GNU_LIBC_VERSION"], text=True).strip()
assert glibc == "glibc 2.35" and platform.machine() == "x86_64"
release = dict(line.split("=", 1) for line in Path("/etc/os-release").read_text().splitlines() if "=" in line)
assert release["VERSION_ID"].strip('"') == "22.04"
environment = {"platform": platform.platform(), "machine": platform.machine(), "glibc": glibc,
               "os_release": release, "python": sys.version,
               "scope": "native x86-64 container userspace on the host Linux kernel; no emulation; --network=none"}
(args.report_dir / "environment.json").write_text(json.dumps(environment, indent=2) + "\n")


def run(name, command):
    reply = subprocess.run(command, capture_output=True, text=True, timeout=180)
    (args.report_dir / f"{name}.stdout.txt").write_text(reply.stdout)
    (args.report_dir / f"{name}.stderr.txt").write_text(reply.stderr)
    if reply.returncode:
        raise RuntimeError(f"{name} failed ({reply.returncode}): {reply.stderr}")
    print(json.dumps({"check": name, "passed": True}), flush=True)


run("runtime", [sys.executable, str(root / "scripts/verify-release.py"), str(args.new_package),
                "--expected-sha256", "81b2fefea6e36dfcb726edbad5e4e502018fbd5a67611a23c0bac06f8e0ce83c",
                "--runtime", "--report", str(args.report_dir / "acceptance.json")])
run("archive-safety", [sys.executable, str(root / "scripts/test-release-package.py"), str(args.new_package)])
run("documentation", [sys.executable, str(root / "website/verify-examples.py"), str(args.new_package),
                      "--report", str(args.report_dir / "documentation-examples.json")])
run("upgrade", [sys.executable, str(root / "upgrade-check.py"),
                "--old-package", str(args.old_package), "--new-package", str(args.new_package),
                "--old-verifier", str(root / "verify-release-0.8.2.py"),
                "--new-verifier", str(root / "scripts/verify-release.py"),
                "--report", str(args.report_dir / "upgrade-compatibility.json")])
(args.report_dir / "passed.json").write_text(json.dumps({"passed": True,
    "checks": ["runtime", "archive-safety", "documentation", "upgrade"], "environment": environment}, indent=2) + "\n")
