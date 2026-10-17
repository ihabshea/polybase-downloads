# 0.8.2 Linux candidate qualification

Archive: `polybase-0.8.2-x86_64-unknown-linux-gnu.tar.gz` (2,870,679 bytes).
SHA-256: `63e1754e3662a3ab6c33c583b8c5c5d4a36fe6f241f1730ba86f8c0f8298157e`.
Clean package source: `a185068703de2b65c24ed696e87b1d35c146d124`.
Release Rust: 1.99.0. Native runtime host: x86-64 Linux 6.18.44, glibc 2.41.
This is a local candidate, not a published downloadable 0.8.2 release.

The [runtime receipt](acceptance.json) passes all 19 checks on the actual
extracted archive. It covers all four executable version/help paths, persistence,
corruption handling, local/replicated recovery, uncertain receipt replay,
subscription deltas, typed query planning, AND/OR plans and historical
continuation across restart. Ten altered/unsafe archives are rejected; the real
builder refuses a dangling checksum symlink without writing outside staging.
All five [runnable documentation cases](documentation-examples.json) pass.

[ELF symbol inspection](glibc-symbols.json) finds a maximum GLIBC_2.34 requirement
in each executable, below the declared 2.35 minimum. The runtime test above ran
on glibc 2.41; it does not claim a separate native Ubuntu 22.04 runtime run.
Executables are unsigned. Hardware power loss remains unqualified.

[Cross-version qualification](upgrade-compatibility.json) uses the independently
verified published 0.8 Linux archive (source `97765a3`, hash `f8c3f5a8…ee0c7fa5`).
The 0.8.2 archive reads its WAL and definitions, preserves an old historical
cursor through a two-key update, and resumes the old subscription token with
one complete two-key transaction delta. The old executable then reopens the
0.8.2 checkpoint/WAL and reads identical current and retained historical rows.
The helper and local raw logs are retained under
`target/evaluation-release-0.8.2/upgrade-check.py` and `target/adaptive-082-*`.

## Reproduce

From the recorded clean source, activate the installed Rust environment and run:

```sh
RUSTUP_TOOLCHAIN=1.99.0 python3 scripts/package-release.py --target x86_64-unknown-linux-gnu --output target/new-082-linux
python3 scripts/verify-release.py target/new-082-linux/polybase-0.8.2-x86_64-unknown-linux-gnu.tar.gz --runtime --report target/new-082-linux/acceptance.json
python3 scripts/test-release-package.py target/new-082-linux/polybase-0.8.2-x86_64-unknown-linux-gnu.tar.gz
RUSTUP_TOOLCHAIN=1.99.0 python3 scripts/test-release-staging.py --target x86_64-unknown-linux-gnu
python3 website/verify-examples.py target/new-082-linux/polybase-0.8.2-x86_64-unknown-linux-gnu.tar.gz --report target/new-082-linux/documentation-examples.json
```

Native macOS qualification must use the same clean source and pinned release
toolchain, or both packages must be rebuilt from a newer common source. Prepare
release metadata at the matching package source. Subsequent website builds
verify that all binary/build/bundled-guide inputs still match that source.

The preparation guard was exercised with this Linux-only staging directory:
it rejects the missing Mac artifact before modifying public release metadata.
Production build also rejects the unqualified inputs. Hosted CI has not executed
runner steps, and no Sites deployment tool is available in this environment.
The existing qualified 0.8 website and packages remain published.
