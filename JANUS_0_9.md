# Polybase 0.9 — Project Janus

Historical queries, trustworthy planning and deterministic execution. Ask what the database knew at a retained commit position, inspect the work behind its answer and reproduce the same ordered result.

## Read one committed past

A read-only `as_of` handle captures an exact retained commit position. Point reads, key ranges, typed JSON scalar predicates and whole-word queries use that same position. A multi-key commit is visible as a complete transaction. Querying the past never writes a new commit.

Positions are commit positions, not timestamps. Future positions, nonexistent commit positions and positions older than the verified retention floor are errors. A retained position with no matching records returns an empty result. An empty result never substitutes for unavailable history.

Position zero is the initial empty database when that position remains retained. Byte keys retain deterministic lexicographic ordering. Typed JSON equality preserves numeric equivalence such as `1` and `1.0`, and distinguishes missing fields from explicit `null`.

## Bounded reconstruction

Historical execution uses a disposable in-memory generation built from the verified retained baseline and checked WAL. It captures complete transactions and their versions before answering a query. Warm reads reuse the captured generation instead of replaying the entire database for every request.

The cache is an optimization, not another source of truth. It is bounded, process-local and rebuilt after restart. Default historical cache and scoped replay budgets are 64 MiB each, with at most 200,000 retained versions. Disabling the cache uses bounded per-query replay. It is not persisted and does not add work to the current-head writer’s publication path. A cold generation can be expensive; historical predicates may require a bounded scan rather than a historical secondary index.

At most four historical operations run concurrently; additional requests receive backpressure. Derived historical postings have a separate logical index budget and may include keys from several retained versions. Canonical rechecks at the requested position remove stale candidates. An unusable or over-budget derived index falls back to bounded canonical execution. Cache and index charges are logical accounting, not a hard process-RSS limit; admitted readers may retain older immutable generations while another is captured.

History protection captures immutable verified generation files and an exact admissible position. Replay and warm reads use those captured inputs after releasing the publication gate, so a concurrent writer cannot mix logical positions and does not wait for the full historical query. Candidate records still require canonical predicate evaluation at the requested position.

## Local HTTP and clients

All new local routes use POST, the console’s exact loopback Origin and decimal-string positions. Keys and values are hexadecimal bytes. The console defaults to `http://127.0.0.1:7340`; start it on an existing database and use its actual retained positions.

```json
POST /api/as-of-get
{"position":"1","key":"646f63732f61"}

POST /api/as-of-query
{"position":"1","query":{"key_prefix":"646f63732f","predicate":"json","value":"","json":{"op":"eq","path":["n"],"value":1}},"cursor":null,"limit":128}

POST /api/as-of-search
{"position":"1","query":{"kind":"text","key_prefix":"646f63732f","text":"quick fox"},"limit":128}
```

The point response has `position`, a hex `value` or `null`, and `explain`. Query and search responses have `position`, ordered `rows`, `next` and `explain`. `/api/as-of-explain` accepts the same body and executes the same planner as `/api/as-of-query`.

An optional query `range` overrides the prefix bounds with explicit byte bounds: `{"start":{"included":"646f63732f61"},"end":{"excluded":"646f63732f7a"}}`. Either bound may instead be `null` for unbounded or use `excluded` / `included` respectively. Continuations bind database identity, query and original position. Reuse the returned cursor with the same query and position.

Historical whole-word search returns a complete result, with `next: null`; exceeding its result limit is an error. It does not silently return a partial unresumable result. JSON scalar search keeps the existing search API’s exact scalar encoding; use `JsonPredicate` queries for typed numeric equivalence.

| Condition | Local HTTP result |
| --- | --- |
| Malformed decimal, leading zero or overflow | `400 nonexistent_position` |
| Position greater than the captured head | `400 future_position` |
| Position below the verified floor | `410 history_expired` |
| Retained position, missing key or no matches | `200` with `null` or empty `rows` |
| Gap or corruption in verified retained history | Corruption error, fail closed |

The Rust engine uses `db.as_of(position)?` followed by `get`, `query`, `query_page` or `search`. Candidate SDK 0.9.0 adds Rust `get_as_of`, `query_as_of`, `query_range_as_of`, `explain_as_of`, `search_as_of` and TypeScript `getAsOf`, `queryAsOf`, `explainAsOf`, `searchAsOf`. Registry availability must be verified before an install command advertises that candidate version; the [client page](https://base.polymathlabs.xyz/clients.html) names the published packages.

## Retention is part of the answer

A checkpoint must preserve the meaning of every retained historical position. Compaction may advance the verified floor; positions below that floor then return an explicit history-expired error. Cached generations cannot extend the supported horizon or make expired cursors silently valid.

An `as_of` handle is not an indefinite retention lease. Each operation checks the current horizon before capturing immutable inputs. An admitted operation can finish from those inputs while a concurrent compaction advances the floor; a later operation on the same handle may then report expiry. It never silently changes the requested position.

Existing historical continuation tokens keep their identity, query and position binding. Page limits and deterministic ordering remain part of the contract. An invalid or foreign token never becomes a fresh current-head query.

## Explain the route

Ordinary execution and EXPLAIN share planning. Existing explain fields remain available, with additive Janus diagnostics.

| Field | Meaning |
| --- | --- |
| `chosen_plan` | Index, range scan, full scan or historical replay |
| `estimated_rows` | Estimated work; never a measured duration |
| `actual_rows` | Rows examined and returned |
| `plan_reason` | Why the selected route applies |
| `fallback_reason` | Why an eligible preferred route was rejected, when applicable |
| `history_position` | Exact commit position used for the result |
| `execution_stats` | Measured timings, candidate work and bytes examined |

`actual_rows.examined` includes observed reconstruction and index-build work as well as canonical query rows. `execution_stats.query_rows_examined` isolates the query phase. `bytes_examined` counts logical canonical/index-build bytes and verified WAL bytes; it is not a measurement of physical disk I/O or process memory.

An optimizer estimate can be wrong. Actual work records what execution observed. Historical replay and a cache hit are identified honestly; no estimated cost is presented as measured microseconds.

## Deterministic verification

The seeded verification harness compares the database with a deliberately simple reference model. Workloads combine conditional transactions, expected-value conflicts, named retries, insert/update/delete and ABA cycles, retained reads, checkpoints, compaction and expired continuations. Process-fault tests challenge durability boundaries and compare recovery with the reference.

A mismatch must preserve its seed, engine version and operation history, together with a minimized reproducer. Reproducibility includes event ordering and cursor outcomes, as well as final key/value state. A passing generated workload is evidence for its tested cases, not a proof of every possible schedule or hardware failure.

Run the source-checkout harness into a new empty evidence directory:

```sh
python3 scripts/run-janus-verify.py target/janus-verify-0.9 --seed 20261018 --seeds 8 --operations 200
```

The runner builds and hashes its release executable, executes the seeded workload and the 37-case injected-process-fault suite, then retains `results.json`, per-seed reports and fault receipts. The final clean-source run used seeds 20261018 through 20261025, 1,600 generated operations, 836 historical checks and eleven expired-page-cursor checks. All 37 injected crash cases passed: seven commit, six named-write, twenty maintenance and four recovery boundaries. `--skip-faults` is a partial development run and cannot qualify crash recovery. Failure artifacts retain original and deletion-minimized operations, failure category, source SHA and a replay command. Minimization is local to the observed mismatch; it does not prove a globally shortest failing sequence.

## Qualification

The Janus matrix fixes record count, retained history depth, cache state and concurrency before comparing historical execution with current-head queries. It separates cold reconstruction from warm historical point, narrow range and JSON equality reads. Reports retain raw samples, p50/p95, resource measurements where available, source and executable hashes, host and toolchain.

The provisional challenge targets are warm historical point p95 below 10 ms, historical JSON equality p95 below 50 ms, narrow historical range p95 below 30 ms and current-head regression no greater than 10%. They are goals, not correctness invariants. The clean-source matrix passed all warm historical targets, while seven of twelve current-head cases missed the 10% target at p50 or p95. Those regressions remain part of the release evidence.

```sh
python3 scripts/run-historical-bench.py target/janus-09-qualification
```

The qualification uses 1K, 10K and 100K records, 128 retained updates and three historical positions per dataset. Point, 1%-equality JSON, 64-key range and whole-word queries produce 36 historical cases, each with five cold and 31 warm samples. Current-head execution uses 31 alternating 0.8.2/0.9 sample pairs over 12 cases. The historical cache and replay budgets stay at 64 MiB with 200,000 versions; the search-index budget is explicitly raised to 256 MiB. Concurrent qualification interleaves 31 historical reads with eight atomic 16-key writes per dataset. The raw report records the actual machine and all limits; do not compare targets without those conditions.

## Recorded historical measurements

[Download every raw Janus sample and its exact provenance](benchmarks/0.9.0/results.json). The valid matrix ran on clean source `6a123302edad0ed49cac541615b9719bb007d188`, executable SHA-256 `d3fd4148aacff9e22de17651d569fd9fc7becace1f82769cc27da1b17a899f6c`. Its source-tree fingerprint remained `bf9d6fac9088c0546b9f1934318da38828eb8521e113f9d7b4ded3db4d8e2f28` before and after measurement.

All 36 historical cases matched the simple reference and forced Scan in complete ordered bytes. Ninety-three historical reads interleaved with 24 atomic 16-key writes also matched the reference. No partial commits or snapshot anomalies were observed in those tested workloads.

The following values are the largest warm p95 across the three retained positions at 100K records, measured in microseconds. Each position has 31 warm samples. These are native engine calls, without HTTP or SDK overhead.

| Historical workload | Warm p95, µs | Challenge target, µs |
| --- | --- | --- |
| Point lookup | 0.647 | 10,000 |
| 1% typed JSON equality | 3,635.778 | 50,000 |
| Narrow 64-key range | 9.280 | 30,000 |
| Whole-word text | 964.940 | No target |

Cold execution is a different cost: the largest recorded cold p95 was 1,996,456.601 µs, approximately 1.996 seconds. The cumulative process peak reached 200,524 KiB RSS, including seeding, recovery, reference values, returned data and derived indexes. Neither number is a per-query allocation measurement. Cold means an empty historical cache after reopen; reopen/recovery is excluded from the timer, and OS/page caches are uncontrolled.

Hardware was a shared x86-64 Intel Xeon Platinum 8573C Linux host, five available CPUs and 35,743,760,384 bytes of RAM, with Rust 1.99.1 and glibc 2.41. CPU pinning, scheduler contention and shared-host load were uncontrolled. Per-dataset limits, complete raw timings, work counters and baseline hashes remain in the report. These measurements do not establish results on another machine.

## Current-head counterexamples

The current-head 10% target was not met in seven of twelve cases. Both p50 and p95 must be at most 1.10 times the measured 0.8.2 baseline. The table preserves every miss from the valid run; a ratio above 1 means that the measured 0.9 path took longer.

| Records | Workload | 0.9 / 0.8.2 p50 | 0.9 / 0.8.2 p95 |
| --- | --- | --- | --- |
| 1,000 | narrow range | 1.149× | 1.885× |
| 1,000 | text | 1.013× | 1.300× |
| 10,000 | point | 1.268× | 1.235× |
| 10,000 | json equality | 1.554× | 1.542× |
| 10,000 | narrow range | 1.290× | 1.214× |
| 10,000 | text | 1.437× | 1.606× |
| 100,000 | json equality | 0.964× | 2.087× |

The baseline uses the recorded 0.8.2 engine at `ce4daf3db59b570895022b136ebdfbae1665ffec`, built with the same toolchain and matching benchmark driver. Thirty-one alternating old/new pairs reduce ordering bias; they do not isolate the cause of a regression. These shared-host observations are counterexamples to the target, not proof that one implementation change caused the difference. We have retained the workload and targets.

An earlier complete run was rejected because generated SDK distribution files changed during its source-provenance window. Its incomplete original before/after digests remain explicitly unavailable, and its observations are preserved as unqualified supporting evidence. They are excluded from the valid qualification and target claims. No rejected sample was substituted into the valid matrix.

The prior [0.8.2 measurements](https://base.polymathlabs.xyz/preview-0-8-2-validation.json) remain versioned evidence for adaptive current-head execution. They do not qualify Janus historical performance.

## Explicit limitations

History is finite. Reads outside the verified retention horizon are refused. Historical positions are local commit positions, not wall-clock timestamps or cross-partition snapshots. SQL, joins and arbitrary historical compound indexes are not provided.

Cold verified generation construction can dominate historical latency. Capturing the verified generation briefly holds snapshot protection; replay proceeds from captured immutable files after releasing the publication gate. Bounded work can reject a query rather than exceed configured row, byte, memory or history limits. No hard wall-clock or process-RSS bound is promised.

Process crash qualification exercises software durability boundaries. It does not establish power-loss behavior on every filesystem or hardware device. Checksummed corruption fails closed; unavailable history is never repaired by inventing values.

The local database remains a free evaluation with a private engine and separately MIT-licensed client SDKs. Hosted SaaS is coming soon. A downloadable Janus build requires matching clean-source native Mac and Linux artifacts, extracted-runtime receipts and verified publication.

Source-checkout reproduction commands require access to the private engine repository. The public SDK tree contains clients only; synthetic workloads, configuration, receipts and raw measurements are published alongside this guide.
