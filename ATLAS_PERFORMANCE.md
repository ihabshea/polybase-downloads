# Atlas 1.5 performance qualification

Atlas compares measured execution with the immutable Polybase 1.0 source commit
`54c92946abbaea30bae25e2e8178676e17cbd9e8`. The 0.8.2 measurements provide
historical context only. They are not the regression baseline. Performance
targets become release evidence only after an unchanged, clean-source paired
run; this document alone reports no improvement or passing measurement.

The fixed targets are candidate/baseline ratios of at most **1.10 for both p50
and p95 current-head latency**, and **0.50 for p95 cold historical latency**.
Cold p50 ratios are reported as diagnostics. Every workload is reported, including failures to meet those targets.
The runner never moves the baseline, adjusts predicates, excludes slow samples,
or substitutes modeled costs for measured durations after observing a result.

Run from the repository with the configured Rust toolchain, after source freeze
and after other builds finish:

```sh
python3 scripts/run-atlas-performance.py target/atlas-performance
```

The destination must be empty. A clean committed source tree is mandatory for
qualification. `--smoke` permits a development tree and uses 1,000 records, one
repeat, five warm samples and three cold samples. It never qualifies a release.
`--prepare-baseline-only` builds the pinned comparison executable and records its
provenance without making a measurement claim. No Git worktree is created.

The runner creates an isolated `/tmp` archive of the pinned commit. Only
`atlas_bench.rs` and its existing `janus_bench_support/mod.rs` helper are copied
into that archive. Engine sources, dependencies and storage behavior stay at the
pinned 1.0 revision. Both engines compile the identical recorded benchmark
source with locked dependencies, default features, the release profile, the same
Rust compiler and the same recorded Rust flags. Separate build target directories
avoid mixing candidate and baseline artifacts. Baseline cache reuse verifies the
source, harness, compiler, flags and executable hashes.

The fixed dataset matrix is:

| Parameter | Configuration |
| --- | --- |
| Live records | 1,000; 10,000; 100,000 |
| Independent repeat processes | 3 per engine and record count |
| Measured warm samples per repeat | 31 per query and position, after 3 warmups |
| Measured cold samples per repeat | 5 per query and position |
| Retained history | 128 atomic commits, 16 updated records per commit |
| Historical positions | Retained baseline plus 0, 64 and 127 commits |
| Typed JSON equality | `group == 1`, approximately 1% selectivity; exact rows recorded |
| Point | `records/{floor(records/3):06}` |
| Range | 64 consecutive byte-ordered keys starting at that point |
| Whole-word search | Both words in `amber history` |
| Historical cache / scoped replay | 64 MiB logical byte cap each; 200,000 versions |
| Search index | 256 MiB logical cap |
| Complete query result | At most 100,000 rows and 64 MiB logical bytes |
| Retained WAL cap | 256 MiB |

Every returned byte and exact position is compared with an independent simple
version model outside the query timer. The model builds expected revisions from
the known transaction history, then evaluates each workload. Baseline/candidate
row counts, framed ordered-result CRCs and positions must also agree. Complete
results are required; a continuation or resource error fails the run rather than
silently turning a full result into a smaller benchmark. Current-head point and
range measurements use the existing `query_page` API. Historical points use
`as_of(S).get`; historical JSON/ranges use `as_of(S).query_with_mode`; historical
text uses `as_of(S).search_with_mode`.

For every sample pair, only one engine executes a query at a time. The runner
alternates baseline-first and candidate-first order. The two processes remain
idle between requests, with separate fresh database directories. Each repeat
recreates both processes and seeds exactly the same committed state. Both pooled
and per-repeat p50/p95 distributions are published. P50 is the ordinary median;
p95 is nearest rank. The release target uses all measured samples pooled across
the three repeats, while per-repeat results expose variation.

“Cold history” means a newly reopened engine and an empty disposable historical
cache. Reopen and recovery occur before the timer. The timer includes `as_of`
capture, historical construction, planning and result production. The operating
system page cache is uncontrolled, so this does not claim physical cold-disk
latency. Warm history reuses the same open engine. IPC, response serialization,
checksums and reference-model validation are outside query timers. Raw EXPLAIN
fields preserve measured work and measured microsecond phase times separately
from cardinality estimates.

The memory probe starts four historical readers and one writer at one barrier.
Each reader performs eight JSON queries at the unchanged retained baseline plus
64 commits and retains its results until its eight calls finish. The writer
publishes 32 atomic 16-key commits. All historical results must match the original
position's model. The report includes read and commit latency samples, logical
version charges, current RSS, 1 ms RSS samples, sampled peak RSS and process
`VmHWM`. Overlap is controlled by the operating system scheduler. RSS includes
seeding, recovery, indexes, independent expected values and returned rows. The
sampling interval can miss shorter peaks; `VmHWM` also includes earlier phases.
This measures process memory during concurrent read work, not allocator counts,
an isolated query's allocation delta or a hard process-memory guarantee.

The throughput probe measures 64 named writes from one caller, each updating the
same two keys with identical 256-byte values. One path uses a real single-node
`Database`; the other uses three real durable `Replica` instances in fresh
directories. Each protocol effect is delivered in FIFO order through the actual
durable replica API, and all peers drain before the next write. All peers' final
states must agree with the expected final atomic pair. Overall throughput includes
token issuance and request preparation; per-commit samples exclude those steps.
This is a local synchronous replication cost comparison. It is not a TCP cluster,
distributed host, failover, parallel client or quorum-only early-acknowledgment
throughput claim. A new request/snapshot protocol is not introduced for this test.

`results.json` records source SHA and source-file hashes before and after the
run, executable hashes before and after, baseline provenance, exact configuration,
hardware and CPU affinity, Rust toolchain, flags, filesystem, load averages,
state file byte sizes and all targets. Every startup and measured sample includes
the relevant process memory observation. `raw-samples.ndjson` is flushed after
every pair, including labeled warmups, to preserve evidence if a later operation
fails. Per-repeat files retain raw sample pairs and diagnostics. The runner also
writes a final failure report when an engine response, parity assertion or
measurement step fails. A source or binary change invalidates the run. Detected
concurrent Rust builds stop measurement; shared-host interference remains a
published limitation.

`measurement_valid` means the complete matrix passed correctness and provenance
checks. `all_performance_targets_met` separately reports the measured targets.
`qualification_passed` requires both, and is always false for a smoke run. Target
misses remain in `target_misses`; a valid measurement with a slow case is useful
evidence and is never relabeled as a passing release.
