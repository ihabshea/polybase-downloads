# Polybase 0.8.2 — Adaptive Query Execution

The current-head JSON planner compares indexed work with a bounded scan. It can
combine eligible equality indexes and restart expensive indexed execution while
holding the same captured head. Every path evaluates the complete typed
predicate against canonical values. The existing 0.7 historical continuation
path remains unchanged.

## Supported strategies

| Strategy | Eligibility | Execution |
| --- | --- | --- |
| Scan | Forced scan, unavailable optimization, incomplete coverage or lower estimated work | Ordered merge of canonical shard rows |
| IndexLookup | Necessary scalar equality with a covering definition | Ordered borrowed postings and canonical verification |
| IndexIntersection | Two necessary indexed equalities inside AND | Ordered intersection of two posting streams, followed by canonical verification |
| IndexUnion | Every OR branch has an eligible indexed necessary condition | Ordered merge with duplicate suppression, followed by complete predicate evaluation |

A definition must cover the entire requested key range. An equality below NOT
is not a necessary condition. An indexed condition inside AND may narrow a
branch even when its other conditions cannot use indexes. An OR with an uncovered
branch cannot safely use only the remaining indexed branches and therefore scans.
The optimizer retains full residual predicate evaluation, including all equality
conditions used to derive candidates.

Plan search is deliberately bounded. An AND intersection uses the two smallest
eligible distinct posting terms, rather than enumerating every index combination.
An OR branch selected as an intersection may be widened to the union of those
terms; canonical residual checks remove the extra candidates. At most 128
considered alternatives are retained for diagnostics. No compound/range index,
join, persistent statistics or background builder is implemented.

Typed numeric equality is unchanged: 1, 1.0 and 1e0 compare equal; signed zeroes
compare equal; large i64/u64 integers are not converted to f64. Numeric 1, string
`"1"` and boolean true are distinct. Explicit null differs from a missing field.
Malformed JSON does not match, including under NOT. Fractional values retain
serde_json's existing finite IEEE-754 parsing semantics.

## Cost estimates and statistics

The bounded estimator compares posting cardinality, the estimated number of
records in the requested range, canonical lookup work and residual predicate
work. Estimated work uses dimensionless units. It does not predict microseconds,
allocations or physical I/O. Considered alternatives and their assumptions are
visible in EXPLAIN so a mistaken choice can be diagnosed.

Index statistics are disposable process memory: total live records, per-term
posting cardinality, definition coverage and a statistics epoch. The epoch names
the canonical head captured by the query. There is no new index file, WAL record,
manifest schema, storage format or durable optimizer state. A cold build records
its actual rows and time separately from warm query execution. A failed or
memory-capped build discards partial optimization state and scans.

Range cardinality and overlapping predicates need estimates; correlated AND
conditions can invalidate an independence assumption. Estimates influence the
amount of work attempted, never candidate coverage or the query predicate.
Measured runtime counters expose such counterexamples rather than hiding them.

The default model charges one unit per posting step, four per canonical lookup,
and two per predicate node. A scan charges one sequential-row unit plus predicate
work. The range estimate uses the smallest covering definition record count, or
total live records when none is available. Posting estimates are capped by the
range estimate. Intersections use an independence estimate; unions use a capped
sum. These are bounded planning assumptions, not measured costs.

## Adaptive restart and one captured head

An indexed strategy may exceed its observed-work threshold and restart as Scan.
The observed index-work threshold is the larger of half the estimated Scan work
and 125% of the selected indexed plan estimate, with a minimum of one work unit.
This allows a correctly predicted plan to finish while bounding work wasted on
a mistaken estimate. A separate posting-step bound is twice the configured
storage key limit. Crossing either threshold permits one restart. Posting lookahead can exceed
the threshold by one bounded merge step (at most 64 inputs). Each canonical
phase remains bounded by the storage key cap; total actual row counts include
both phases. The executor clears its partial page and match state,
then scans from the original
range start at the original captured position. Restart happens at most once.
Discarding the partial page avoids duplicate rows, ordering changes and page
boundaries that depend on the first strategy.

The history read gate remains held throughout definition/statistics capture,
posting traversal, canonical reads, restart and final result capture. The writer
can install new MVCC versions but cannot publish changes to postings or the head
until it obtains the history write gate. Reads at the captured position ignore
those unpublished versions. Replanning never releases this protection. Candidate
rechecking alone would not establish this invariant.

A query may delay writer publication for its bounded duration. There is no hard
latency guarantee or background index builder. A stale or unusable cache cannot
authorize omissions: the query uses a canonical scan instead.

## Bounds and pagination

Posting streams borrow existing ordered keys. A two-index intersection and OR
merge use bounded cursor state and do not construct a set containing all
candidates. Duplicate keys contributed by multiple OR branches are suppressed
before canonical evaluation. Result order remains byte-key order for every plan.

Storage key limits, index-memory charges, metadata read bounds, predicate depth
and node bounds, page rows and returned byte limits remain enforced. Defaults
remain a 16 MiB logical derived-index budget, 4,096 rows per page and 2 MiB of
logical returned row bytes. Predicate bounds remain depth eight, 64 nodes and
32 KiB encoding. Logical charges are not allocator or RSS guarantees.

Continuation tokens keep the original query, position and last key. A continuation
uses the verified 0.7 baseline/WAL reconstruction path even when its position
happens to equal the current head. Current postings and local optimizer choices
do not affect historical cursor semantics or retention expiry.

## API and explain

`/api/query-page` and `/api/explain` share the same planner and executor. EXPLAIN
executes the query. Existing requests and clients remain valid. The optional
`force_scan` request field remains available for differential comparisons.

```json
{"query":{"key_prefix":"646f63732f","predicate":"json","value":"","json":{"op":"eq","path":["status"],"value":"open"}},"cursor":null,"limit":128,"force_scan":false}
```

Rust retains `query_page_with_mode(..., QueryMode::ForceScan)` and HTTP client
`page_with_scan(..., true)`. Existing `QueryExplain` and `PaginatedQuery` struct
shapes and method return types remain unchanged, including external struct
literal construction. In-process callers opt into richer diagnostics with
`query_page_diagnostics(...)` or `query_page_diagnostics_with_mode(...)`, which
return `AdaptiveQueryPage`. Its explain object contains the existing query
explanation and `optimizer`; it dereferences to `QueryExplain` for existing field
reads. HTTP uses this diagnostic executor and flattens the same existing fields
alongside `optimizer`, retaining the additive wire response. TypeScript retains
`client.page(query, cursor, limit, true)`. The public `ExecutionPlan` representation
continues to use Scan or IndexLookup; the existing `plan` string remains
`index_lookup` for intersections and unions. Additive optimizer diagnostics
describe the detailed strategy. After restart the completed plan is Scan and
`optimizer.initial_strategy` records the abandoned indexed strategy.

All existing EXPLAIN fields are preserved. The additive `optimizer` object has
the following fields.

| Field | Meaning |
| --- | --- |
| `strategy`, `initial_strategy` | Completed and originally selected strategy; they differ after restart |
| `index_names` | Definitions supplying candidates |
| `alternatives` | Considered strategies, index names, estimated candidates and estimated work |
| `estimated_work`, `estimated_range_rows` | Initial selected work estimate in units and bounded range-row estimate |
| `statistics_epoch`, `total_live_records` | Captured statistics position and canonical live-record count |
| `statistics_rows` | Existing cache key entries visited to refresh definition coverage; no canonical value reads are implied |
| `definition_coverage`, `term_cardinalities` | Prefix coverage counts and complete posting cardinalities identified by index, path and typed value |
| `actual_work` | Posting steps, canonical lookups, predicate evaluations, scan rows and restart count |
| `phase_timings_micros` | Measured planning, indexed execution and scan execution elapsed time |
| `replan_reason` | Runtime restart reason, or null |
| `calibration` | Local enablement, sample count and estimated lookup weight |

 Existing `elapsed_micros`, cold-build timings and
new phase timings are measured elapsed values. Estimated work is explicitly
labelled as units. Counters include abandoned indexed work when execution restarts;
final match and page counts describe the completed strategy.
`total_rows_examined` includes execution rows, definition reads, cold-build rows
and statistics refresh rows, including repeated examinations.

Existing HTTP position fields remain decimal strings. The additive optimizer
statistics epoch is a diagnostic numeric field; cursor and transaction positions
retain their existing exact string representation. Rust HTTP clients retain explain as JSON;
TypeScript treats the new optimizer object as optional so older server responses
remain readable. Neither client package is published to a package registry.

## Local calibration

Optional process-local calibration can update the canonical lookup weight from
measured workloads. In-process Rust enables it with
`database.set_optimizer_calibration(true)?`; it is disabled by default and is
not enabled implicitly by HTTP requests. Calling the method resets measurements.
Only successful complete warm scan/lookup pairs for the same query signature
and captured position train it. Cold builds, historical reads and adaptive
restarts do not supply calibration samples. It stores at most 16 pending pairs
and learns at most 64 pairs, using fixed-point arithmetic and lookup weights
bounded from one to 16. EXPLAIN reports whether calibration is enabled, its sample
count and current lookup weight in estimated units. Measurements remain local
to the process; reopen starts from safe defaults. Calibration changes planning
hints, never index coverage, the snapshot boundary, canonical verification,
ordering or cursor contents. Query results remain independent of calibration.

## Recovery and compatibility

WAL synchronization, durable frontier publication, generation selection, checksum
handling, checkpoint and compaction retain their existing paths. Index postings
and optimizer statistics rebuild from canonical recovered state. Failed
optimization never relaxes corruption handling or causes an incomplete index to
stand in for canonical records.

Live subscriptions keep complete commit-derived transaction deltas, checked poll
and resume behavior. Adaptive planning does not split transactions, silently skip
commits or advance a subscription cursor. Snapshot-at, verified backup and
retained history keep the 0.7 contracts.

## Qualification and release status

The required benchmark matrix uses 1,000, 10,000 and 100,000 records at 0.1%, 1%,
10%, 50% and 90% predicate selectivity. It includes correlated and independent
conditions, cold and warm paths, raw samples, p50/p95, peak RSS where available,
actual rows examined, index-build work, source SHA, executable hash and full
configuration. Allocations are reported only when measured. RSS includes process
history and is not a per-query allocation count.

Every measured query must equal forced Scan in complete ordered results at its
captured head. Performance targets are evaluated from measurements: 90% should
select Scan, and the selective workload should retain at least 80% of the
published 0.8 speedup. A missed target remains a documented counterexample; the
benchmark input is not changed to conceal it.

Correctness qualification additionally covers generated nested ALL/ANY/NOT,
missing/null values, numeric classes, duplicate posting contributions, range
boundaries, concurrent publication, adaptive restart with a waiting writer,
reopen/checkpoint/compaction, subscriptions and client compatibility.

The earlier 0.8 release completed all 19 acceptance items and is publicly
available. The 0.8.2 candidate requires its own complete checks, measured evidence,
matching clean-source native Linux/macOS archives and extracted-runtime receipts.
A local website preview or a Linux-only package does not establish a downloadable
0.8.2 release. Hosted SaaS is coming soon.

## Recorded qualification

The 60-case matrix at clean source
`dde442fe846891a2bb8f034a09cac467ec1ad88f` passed complete ordered forced-Scan
parity for every cold and warm sample. At 100,000 records, the 1% equality query
measured a 46.21× warm speedup (1.156 ms median versus 53.402 ms Scan), exceeding
the 35.36× retention goal. The 90% equality query initially selected Scan.

The cost model also has measured counterexamples. At 100,000 records, correlated
50% AND chose an intersection and restarted: 71.726 ms median versus 45.458 ms
Scan, or 1.578× slower. A cold 90% equality query spent 814.54 ms building the
disposable index before choosing Scan; total cold Auto was 884.77 ms versus
79.46 ms forced Scan. Cold excludes reopen time and does not control OS caches.
These observations remain in the raw samples and are not modeled numbers.

The complete configuration, p50/p95, process RSS, work counters, source/executable
hashes and raw samples are in the accompanying qualification evidence. The
benchmark implementation is unchanged in subsequent packaging/qualification
updates. EXPLAIN calibration fields describe the hint used for planning;
measurements from that execution may affect only subsequent queries.
