# Polybase 0.9 — Project Janus candidate

Janus answers what a local database knew at an exact retained commit position.
Read-only historical point, range, typed JSON and whole-word queries preserve
atomic batches, byte-key ordering and explicit retention errors. Additive explain
diagnostics identify the captured position, plan, estimates, actual work and
fallback reason. Existing storage, WAL and cursor formats remain unchanged.

The [historical query contract](JANUS_0_9.md) documents APIs and limits. Cold
execution builds a bounded, disposable verified version cache; warm queries reuse
it. Historical JSON can use one necessary equality under a valid definition at
the requested position. Other expressions use bounded canonical scans or scoped
replay. Historical compound intersection/union and adaptive restart are not
implemented. Captured immutable files let admitted reads finish across concurrent
publication and compaction; later calls can explicitly expire.

## Actual qualification

Engine source: `6a123302edad0ed49cac541615b9719bb007d188`.
The Rust 1.99.1 measurement executables and hashes are recorded in the reports;
native distribution packages separately pin Rust 1.99.0.

- Formatting, strict Clippy, Rust 1.89 compatibility and documentation passed.
  All 227 workspace tests and 181 default-feature tests passed without ignored
  tests. [Engineering evidence](qualification/0.9.0/engineering.json).
- Eight seeds exercised 1,600 operations, 836 historical checks and 11 expired
  cursors. All 37 injected process-crash scenarios passed. Mismatches retain
  seed/version/history and a deletion-minimized replay workload, with explicit
  minimization limits. [Verification evidence](qualification/0.9.0/verification/README.md).
- All 36 historical cases matched a simple reference and forced Scan byte for
  byte. All 93 retained reads racing 24 atomic commits passed. Every warm
  historical target was met on this host. Cold reconstruction reached 1.996 s;
  cumulative peak RSS reached 200,524 KiB.
- **Seven of 12 current-head cases missed the 10% performance goal.** The fixed
  workload, all raw pairs and every counterexample are published. Shared-host
  variability prevents a causal regression conclusion or a general performance
  guarantee. The first run was rejected for a changed source fingerprint and is
  preserved separately. [Measured results and limitations](benchmarks/0.9.0/README.md).

The matrix uses 1K/10K/100K records, 128 retained commits, three historical
positions, five cold and 31 warm samples per historical case, and 31 alternating
old/new sample pairs per current-head case. These are direct engine calls, not
HTTP latency. Cache state, logical memory budgets and hardware are recorded;
OS caches and shared-host scheduling were uncontrolled. SIGKILL qualification is
not hardware power-loss evidence.

## Publication status

This is candidate source and measured evidence, not a claim that Janus is
downloadable or deployed. Matching native Apple Silicon Mac and Linux archives,
runtime receipts, public byte verification and website deployment must complete
before declaring the release published. Hosted CI currently fails before runner
steps. npm/crates.io publication lacks usable registry credentials, and this
environment has no Sites deployment capability.

The live database remains 0.8.2 and live SDKs remain 0.8.3. The separately
MIT-licensed SDK source in this branch prepares 0.9.0; new historical methods
require a 0.9 server. The engine/server source remains private.
