# Polybase 0.8.0-preview.1 — Query Planning and Execution

Fresh current-head JSON query pages now use declared secondary indexes when a
necessary equality predicate is eligible. Scan and IndexLookup execute the same
typed predicate against canonical values at one captured logical position.
Historical continuation pages keep the verified 0.7 reconstruction path.

## Supported plans

| Plan | Eligibility | Execution |
| --- | --- | --- |
| Scan | Forced scan, no usable covering definition, or no necessary equality | Bounded ordered merge of canonical shard rows |
| IndexLookup | Scalar `eq` at the root or within nested `all`, on a declared path covering the whole query range | Ordered borrowed posting list, canonical point lookup, full residual predicate evaluation |

An equality under `any` or `not` is not a necessary condition and cannot by
itself select an index. An enclosing `all` can still select a separate equality
outside those subexpressions. Multiple eligible definitions select the smallest
complete posting list by its actual stored cardinality, with index name as a
deterministic tie-break. This is not a cost model. There is no OR union, index
intersection, join, compound index, range lookup, collation or estimated cost.

The definition's key prefix must cover the entire query range. Using an index
for only an overlapping prefix would lose records, so that case scans. All
residual conditions, including the selected equality, are re-evaluated against
canonical data. Results remain byte-key ordered and duplicate-free.

## Numeric and missing-field semantics

Typed JSON equality is unchanged: 1, 1.0 and 1e0 compare equal; large i64/u64
integers are not converted to f64; positive and negative zero compare equal.
String `"1"`, boolean true and numeric 1 are distinct. Null matches only an
explicit null field. A missing field never matches equality, including null.
Malformed JSON does not match. Fractional values retain serde_json's existing
finite IEEE-754 parsing semantics; arbitrary-precision decimal parsing is absent.

The shared derived index now stores a separate normalized typed term alongside
its legacy search term. Its decimal-sign/exponent/digits normalization uses the
same equivalence classes as `JsonPredicate::Eq`. The older `/api/search` and
`/api/index-search` scalar-encoding semantics remain unchanged, including their
distinction between 1 and 1.0. The new planner never incorrectly reuses those
legacy numeric terms for typed equality.

## One consistent snapshot

The executor acquires the existing history read gate before reading definitions
at the captured head. It retains the gate through index build/selection, posting
enumeration, canonical value reads and result capture. The writer installs new
MVCC versions before publication but cannot update postings or advance the head
until it acquires the history write gate. Reads at the captured position ignore
those unpublished versions; reclamation cannot pass the blocked publication.

The cache mutex protects posting traversal. Postings and canonical values thus
belong to the same head even for a cold build or concurrent write. Candidate
rechecking supplies residual filtering; it is not a substitute for this boundary.
Queries can pause writer publication for their bounded duration. No hard latency
bound or background index builder is promised. Cache position mismatch disables
the cache and causes a scan rather than using stale omissions as an authority.

## Bounds and fallback

The existing storage, predicate, query, index-memory, page-row and page-byte
limits remain in force. Defaults still include a 16 MiB logical derived-index
budget, 4,096 rows per page and 2 MiB of logical returned row bytes. Predicate
limits remain 64 nodes, depth eight and 32 KiB encoding. Query encoding, range
and page limits validate before planning on both forced and automatic paths.

IndexLookup borrows an existing ordered posting list. It does not materialize an
unbounded candidate array or charge candidates as if they were returned rows.
Candidate visits and scan rows are bounded by the configured storage key limit.
Scan merges at most 64 shard iterators using borrowed head references. It does
not copy the entire database. Only the first requested matching rows are retained;
remaining rows are examined to produce actual match counts and a continuation.
Returned bytes are charged identically in key order, independent of plan.

Metadata inspection allows at most 64 definitions, 32 KiB per definition, and
the configured transaction read-key/read-byte budgets. Missing, deleted, invalid,
out-of-range, memory-capped or otherwise unusable definitions/postings fall back
to a bounded canonical scan. Failed builds discard partial postings completely.
The shared memory budget includes both typed and legacy terms; a dataset that
now exceeds it scans instead. A cache disabled by budget or unindexable data
stays disabled until reopen, as in the existing search implementation. Force
Scan does not build or consult the cache.

Logical charges are not allocator or RSS guarantees. Temporary parsing retains
the existing value/codec bounds. Broad queries still inspect broad candidate
sets; an index is not a promise that a 90% query will be faster than scanning.

## API and explain

The existing `/api/query-page` and `/api/explain` endpoints share the same
planner and executor. Both accept:

```json
{"query":{"key_prefix":"646f63732f","predicate":"json","value":"","json":{"op":"eq","path":["status"],"value":"open"}},"cursor":null,"limit":128,"force_scan":false}
```

`force_scan` is optional and defaults to false. Rust exposes
`query_page_with_mode(..., QueryMode::ForceScan)` and the HTTP client
`page_with_scan(..., true)`. TypeScript exposes
`client.page(query, cursor, limit, true)`. Existing calls remain valid.
EXPLAIN executes the query; it does not estimate hypothetical work.

| Field | Measured meaning |
| --- | --- |
| `plan` | `scan`, `index_lookup`, or the unchanged `retained_history_scan` |
| `execution_plan` | Tagged `scan` or `index_lookup` with its index name |
| `index_name` | Chosen declared definition, or null |
| `fallback_reason` | `forced_scan`, `ineligible_predicate`, `missing_index`, `no_matching_index`, `index_range_not_covered`, `unusable_index_definitions`, `index_unusable`, or `historical_cursor`; null for a successful lookup |
| `candidate_count` | Actual ordered posting keys visited in the requested range; zero for Scan |
| `scanned_rows` | Actual live canonical values examined by query execution |
| `planning_rows` | Live definition records examined, including an invalid record that caused fallback |
| `index_build_rows` | Actual live canonical rows visited by this query's cold build; zero when warm |
| `index_build_micros` | Measured cold-build time; zero when no build ran |
| `total_rows_examined` | Execution plus metadata plus cold-build rows, including repeated examinations |
| `matched_rows`, `returned_rows` | Complete match count and actual page length |
| `scanned_records` | Zero for current-head execution; WAL records replayed for historical continuations |
| `elapsed_micros` | Actual execution time after input validation, including planning and any cold build |

Row counters count live values, not internal tree comparisons, tombstone slots,
version-vector steps or allocations. Elapsed time includes that overhead. No
unmeasured optimizer costs are reported. HTTP positions remain decimal strings.

## History, subscriptions and recovery

A continuation cursor always uses the 0.7 base/WAL reconstruction path, even if
its captured position happens to equal the current head. It does not consult
current postings. Snapshot-at, retention expiry, checksums, generation selection,
backup and the WAL/frontier commit/recovery protocol are unchanged. Fresh
current-head queries use canonical recovered memory, like existing current-head
search; they do not replay or audit the on-disk WAL on every request.

Live subscription registration and commit-derived delta projection retain their
existing paths and limits. The planner does not skip subscription commits, change
before/after transitions, split a transaction, or advance a cursor without the
normal checked poll. Resume still reconstructs from canonical retained history.
Postings are disposable memory and rebuild after reopen. There is no persistent
index file, new WAL format, repair fallback, or relaxed corruption handling.

## Qualification and release status

The qualification runner uses 1,000, 10,000 and 100,000 records at approximately
1%, 10% and 90% selectivity. It checks complete ordered indexed/forced-scan parity
for every measured sample, alternating execution order after warmups. It reports
raw samples, median and nearest-rank p95 native-engine latency (excluding HTTP
encoding/network time), actual row/candidate counts,
cold build time, cumulative process peak RSS where available, actual source SHA,
source digest, executable hash and every overridden limit. Allocations are
explicitly unavailable; cumulative RSS is not per-query allocation.

```sh
python3 scripts/run-planning-bench.py target/new-planning-evidence --sizes 1000 10000 100000 --samples 21
```

The largest complete-result benchmarks explicitly use the allowed 256 MiB index
budget, 100,000 returned-row cap and 64 MiB result-byte cap. These are qualification
settings, not changed production defaults. The benchmark retains all measured
results and never fabricates target latencies. Warm shared-host measurements are
not cold-cache, power-loss or production-capacity evidence.

Source-maintainer checks also include formatting, all-target/all-feature Clippy,
full/default workspace tests, generated differential cases, controlled publication
races, injected publication failure/recovery, client/console compatibility, native
package verification, and documentation examples. Public download claims remain
gated on matching clean-source native Linux/macOS packages and extracted-runtime
receipts. A local website preview or Linux package alone is not a downloadable
multi-platform release. Hosted SaaS is coming soon.
