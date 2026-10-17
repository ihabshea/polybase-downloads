# Polybase 0.8.2 — Smarter queries, one history

This release brings the 0.8 query planner and 0.8.2 adaptive execution together
in one free local evaluation for Apple Silicon macOS and x86-64 Linux.

## The 0.8 foundation

Declare JSON scalar equality indexes and query a bounded range of canonical
records. A usable index supplies ordered candidates; the complete typed predicate
still decides which records match. A missing, dropped, incomplete or memory-capped
index falls back to a canonical scan. The captured head stays protected throughout
planning, index construction, candidate reads and result capture.

EXPLAIN exposes the chosen path, candidates, canonical rows, index-build work and
actual elapsed time. Typed numeric equality, null versus missing fields, byte-key
ordering and historical continuation retain their existing semantics.

## New in 0.8.2

- Compare Scan and eligible indexed strategies using bounded, dimensionless work
  estimates. A broad match can choose Scan before attempting indexed execution.
- Stream a two-index AND intersection or an ordered, deduplicated OR union when
  every branch has a covering indexed necessary condition. Recheck every candidate
  against the complete predicate; an uncovered OR branch requires Scan.
- Restart an unexpectedly expensive indexed attempt once as Scan. Discard partial
  results, keep the original captured head and restart from the original range
  boundary, preserving deterministic pages and zero duplicates.
- Inspect additive optimizer diagnostics: considered alternatives, estimated work,
  statistics epoch, actual posting/canonical work, measured phase timings and the
  reason for a restart. Existing public Rust result structs, enum variants and
  HTTP fields remain compatible; richer Rust diagnostics are opt-in.
- Optionally calibrate costs from actual warm local measurements. Calibration is
  bounded, process-local, disabled by default and reset after reopening.

## Measured evidence, including the awkward cases

The recorded Linux qualification covers 60 cases: 1K, 10K and 100K records, five
selectivities, four predicate families, five cold and 21 warm samples per path.
Every measured Auto result matched forced Scan in complete byte-key order with
zero duplicates. These are native-engine measurements, excluding HTTP and
concurrent writers; they are not predictions for other machines or workloads.

At 100K records and 1% equality, warm Auto measured 1.156 ms median versus
53.402 ms forced Scan, a 46.21× ratio. At 90%, Auto chose Scan initially. Perfectly
correlated 50% AND was a counterexample: an intersection restarted and took
71.726 ms versus 45.458 ms Scan, or 1.58× longer. Cold index construction can
dominate latency even when Scan is ultimately selected. Full samples, source and
executable hashes, work counters, p50/p95 and limits accompany the evidence.

[Adaptive execution reference](https://base.polymathlabs.xyz/preview-0-8-2.html)
· [Original planner reference](https://base.polymathlabs.xyz/preview-0-8.html)
· [Raw qualification](https://base.polymathlabs.xyz/preview-0-8-2-validation.json)

## Compatibility and limits

WAL, checkpoints, cursor formats, subscription transaction deltas, retained history
and corruption handling keep their existing contracts. Disposable postings and
statistics rebuild from canonical state. Back up a closed database directory as
a unit before upgrading; in-flight writes with an unknown outcome still require
reconciliation.

This remains a bounded local database evaluation, not SQL or a production service.
There are no joins, compound/range indexes, persistent optimizer statistics or
background index builders. Queries can delay writer publication; no hard latency
or process-RSS bound is promised. Use disposable data and loopback interfaces.
Hosted SaaS is coming soon, with no announced launch date.

Mac: Apple Silicon, macOS 15+, ad-hoc signed and not notarized.
Linux: x86-64, glibc 2.35+ (Ubuntu 22.04+), unsigned.
Source remains private; binaries are free for the uses in the included evaluation
license. Checksums and per-platform qualification receipts accompany the downloads.
Hosted GitHub CI is unavailable because its runners are blocked by account billing;
local checks and extracted-runtime results are reported separately.
