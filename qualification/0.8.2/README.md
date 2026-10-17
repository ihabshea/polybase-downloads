# Polybase 0.8.2 release qualification

The release combines the original 0.8 query planner with 0.8.2 adaptive execution.
Both distribution targets must name clean source
`2a8fd5c95ade14b05be9cfd66c419c0d68b6500f` and pinned Rust 1.99.0.
The source remains private; this repository distributes evaluation binaries,
documentation and synthetic qualification receipts.

## Platforms and actual checks

| Target | Archive SHA-256 |
| --- | --- |
| aarch64-apple-darwin | `688d0d9296a052c1fd6862547a11fde233220b4274bec3c59f30daeb5ecc0d9c` |
| x86_64-unknown-linux-gnu | `dbec2441bde1cb880c931459ff8b23c14aa68accb5fcb154d587ede00a88eb10` |

The Apple Silicon build and runtime checks ran natively on macOS 15.1 arm64.
The Linux build and runtime checks use x86-64 Ubuntu 22.04, glibc 2.35, in Docker
under Rosetta emulation on that Mac. This is actual extracted Linux execution,
not a separate bare-metal Linux qualification. The cached release image is
`sha256:f4a7f6555791706a5a10bd32f6b2340bf3baa9bc2f6e4297645f334aebbad614`.

The [Mac runtime receipt](mac/acceptance.json) and
[Linux runtime receipt](linux/acceptance.json) bind checks to each archive hash.
Each target passes 19 extracted-runtime checks, ten altered/unsafe archive cases,
the actual builder's dangling-checksum-symlink test and five runnable documentation
examples. The checks cover all four executables, persistence, corruption refusal,
query deltas, uncertain write reconciliation, three-node failover, typed planning,
forced-scan parity, AND/OR execution and historical continuation after restart.

The [Mac upgrade receipt](mac/upgrade-compatibility.json) and
[Linux upgrade receipt](linux/upgrade-compatibility.json) exercise published 0.8
and new 0.8.2 executables against one synthetic database. Each archive is verified
with its version's bounded file inventory before extraction. In both directions,
WAL/checkpoints reopen, historical page positions remain stable, subscriptions
resume complete transaction deltas and existing record revision tokens still
write. The final canonical records agree. Receipts include both archive hashes;
this bounded fixture does not establish every possible upgrade workload.

Mac binaries are ad-hoc signed and not notarized. Linux executables are unsigned.
The [ELF inspection](linux/glibc-symbols.json) checks required GLIBC versions
against the declared 2.35 minimum. Hardware power loss remains unqualified.

## Engine, clients and measured evidence

Local formatting and all-target/all-feature Clippy with warnings denied pass.
There are 198 passing all-feature workspace tests and 187 passing default-feature
workspace tests, including 168 default engine tests. Rust 1.89 compatibility,
API documentation with warnings denied, 48 console/release-input checks,
TypeScript checking and two real-server TypeScript tests pass.
Five fresh adaptive smoke cases verify lookup, initial Scan, one restart,
intersection and union with ordered forced-Scan parity and zero duplicates.

The [60-case benchmark](../../benchmarks/0.8.2/README.md) retains its original
host, toolchain and measured-source provenance. It was not rerun on this Mac.
Its raw SHA-256 is
`b7617e427b109cebd2412c170e0d44600655419b3b428773ab95115cbdb95913`.
Both favorable results and measured counterexamples remain published.

Hosted GitHub CI did not execute runner steps: the account's billing/spending
limit blocked job startup. These are local qualification results, not a CI pass.
The [earlier Linux-only candidate](../0.8.2-linux/README.md) is historical evidence
from another package source and is not the artifact distributed by this release.

The production website passes 84 responsive checks across 12 pages and seven
widths, plus 24 automated accessibility scans with zero violations, browser errors
or external requests in the local suite. Keyboard navigation, reduced motion and
JavaScript-disabled navigation pass. Browser automation uses the installed Chrome
with an isolated profile; it is not a product dependency.

The Linux staging test initially reached its 120-second build timeout before
assertions. A rerun passed with a 600-second allowance for the emulated build;
the source builder and staging-boundary assertions were unchanged.
