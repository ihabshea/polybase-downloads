# Polybase 0.7.0-preview.1

This preview adds the following local APIs. It remains an experimental,
single-host database with bounded state and history. No production fitness,
authentication, SQL, automatic retention, or exactly-once transport is claimed.
All features use existing WAL/frontier durability and fail-closed recovery.

| Feature | Interface | Explicit limitation |
| --- | --- | --- |
| Live JSON queries | `ValuePredicate::Json`, `Database::subscribe` / `resume`; `POST /api/query` | Local database only; complete transaction deltas; finite lease, result and history bounds |
| Typed JSON predicates | `JsonPredicate`: eq/ne/lt/le/gt/ge/exists/type/prefix/all/any/not | Object paths only, 1–8 keys; 64 nodes, depth 8, 32 KiB predicate; scalar comparisons; no array traversal |
| Stable pagination | `Database::query_page`; `POST /api/query-page` | Byte-key order at one retained position; scan/replay per page; no pin, so compaction can expire the cursor |
| Revision-aware writes | `read_revision`, `write_revision`; corresponding HTTP routes | One key per write; detects ABA within retained history; uncertain writes require inspection, not automatic retry |
| Online backup and verification | `Database::backup`, `Engine::verify_backup`; HTTP backup/verify-backup | Pauses sequencer while checkpointing/copying; local filesystem; existing destination refuses; closed-copy verification may perform normal recovery |
| Query explain and metrics | `PaginatedQuery::explain`; `POST /api/explain` | Actual historical records/rows scanned, matches, page rows and elapsed microseconds; no cost-based optimizer |
| Rust and TypeScript clients | `clients/rust`, `clients/typescript` | Loopback HTTP only; synchronous Rust, fetch-based TypeScript; no automatic write retry; TypeScript rejects unsafe integer input |
| Historical snapshots | `Database::snapshot_at`; `POST /api/snapshot-at` | Only retained positions; reconstruction scans base plus WAL; bounded by storage policy; no permanent time travel |
| Adaptive compaction advisor | `Database::compaction_advice`; HTTP compaction-advice | Uses WAL pressure and live subscriber positions; advisory only; external cursors, revisions and request horizons need caller policy |
| Secondary index definitions | create/list/drop/search-index | 64 named single-field scalar equality definitions; canonical reserved metadata keys; derived RAM postings, bounded scan fallback; no unique, compound or ordered indexes |
| Streaming subscriptions | `Subscription::into_stream`, TypeScript `Client.stream` | Demand-driven polling, one complete page at a time; no SSE/WebSocket, background push queue or durable consumer acknowledgment |
| Replication fault lab 2.0 | `scripts/fault-lab-v2.py --seed N` | Real process isolation/heal/SIGKILL/restart/snapshot catch-up; fixed three voters on one host; seed selects schedule, OS scheduling is nondeterministic |

## JSON matching

`JsonPredicate` has a tagged JSON representation, for example:

```json
{"op":"all","predicates":[{"op":"eq","path":["status"],"value":"open"},{"op":"ge","path":["priority"],"value":2}]}
```

Comparisons never coerce strings, booleans or null to numbers. Missing paths fail
all scalar comparisons, including `ne`; incompatible scalar types also fail
all comparison operators. `exists` distinguishes missing from null.
`not` negates the whole inner predicate on a valid JSON document. Invalid JSON
never matches, including `not`. Equality compares numbers mathematically after
serde_json normalization, so 1 and 1.0 compare equal. Integers in the supported
i64/u64 range retain exact ordering and equality without f64 conversion.
Fractional/exponent JSON inputs use serde_json's finite IEEE-754 parsing; arbitrary
precision decimal semantics are not provided. Arrays/objects can be type-tested,
but are not scalar-comparison operands. Strings use case-sensitive Unicode scalar
lexicographic order and prefix matching; no locale collation.

```sh
curl -sS http://127.0.0.1:7340/api/query \
  -H 'Origin: http://127.0.0.1:7340' -H 'Content-Type: application/json' \
  --data '{"key_prefix":"7461736b732f","predicate":"json","value":"","json":{"op":"eq","path":["status"],"value":"open"}}'
```

The response has `id`, `instance`, `token`, `position` and hex `rows`. Use the
existing `/api/poll`, `/api/resume` and `/api/unsubscribe` routes. Token encoding
adds predicate tag 3 to the existing local query format; older byte tags keep
their original encoding. An older executable cannot decode a JSON cursor.
Snapshot registration, before/after projection, shared-work caching and resume
all evaluate the same predicate. No index is needed for correctness.

## Pagination, history and explain

`POST /api/query-page` or `/api/explain` accepts
`{"query":QUERY,"cursor":null,"limit":128}`. Reuse the exact query and returned
`next` string for the next page; stop at null. The cursor binds database identity,
query, captured position and exclusive last key with a CRC integrity check.
CRC is not authentication. Page size is 1 through the configured search row cap
(4096 by default), and page bytes are capped (2 MiB by default). A page never
silently truncates on a byte limit; it errors instead. Inserts, updates and deletes
after the captured position cannot move or duplicate rows. Cursors survive reopen
and checkpoints while their position is retained. They do not pin retention.

Explain reports `retained_history_scan`, `scanned_records`, `scanned_rows`,
`matched_rows`, `returned_rows`, `elapsed_micros`, and the captured `position`.
It executes the query; it is not a hypothetical estimate. It currently replays
the complete retained prefix through the requested position and filters all rows.
Named equality indexes accelerate `/api/index-search`, not historical pagination
or initial JSON subscription registration. Live projection checks changed keys.

`POST /api/snapshot-at` takes `{"position":"12"}` and returns hex `rows` and the
requested position. Both history APIs reject future or expired positions and
verify the selected baseline and traversed WAL. Corruption fences the live
database instead of silently substituting another snapshot. Raw historical rows
include index-definition metadata described below.

## Revisions and uncertain outcomes

`POST /api/read-revision` takes `{"key":"7461736b732f31"}`. It returns hex-or-null
`value`, a key/database-bound `revision`, and string `position`. Submit
`{"revision":"...","value":"..."}` to `/api/write-revision`, with null to
delete. The sequencer checks every retained mutation after observation. Even
an equal-byte write or put/delete cycle invalidates the revision. Unrelated key
writes do not invalidate it. A compacted observation returns `history_expired`;
a changed key returns `conflict`. Neither case writes anything.

Revision writes do not have named request deduplication. After a transport error
their outcome may be uncertain. Re-read and reconcile; do not assume failure or
blindly retry with a new revision. For durable original-request lookup/replay use
the existing named conditional-request API and its separate byte expectations.

## Backup and retention

`POST /api/backup` takes `{"directory":"/absolute/new-backup"}`. The parent must
exist, the destination must not exist, and it must be outside the live database.
The sequencer completes a full checkpoint without advancing the retained floor,
then copies identity, CURRENT, and the selected generation into a fresh sibling
staging directory. It synchronizes files/directories, opens and fully verifies
the copy, checks identity/head, reserves the final name, renames, and synchronizes
the parent before returning. Acknowledged named requests and retained query
history are included. Writes queued behind copying wait or encounter normal
backpressure. This is an online operation with a write pause, not a nonblocking
incremental backup. It requires enough free disk; no disk reservation is promised.

On failure, leave any `.polybase-backup-*` staging directories intact for
inspection. Before final selection they are not published backups. A crash
between final-name reservation and rename can leave an empty destination;
verification rejects it. After rename but before parent synchronization the
outcome is uncertain. Never overwrite or merge backups to recover from an error.

`POST /api/verify-backup` uses the same directory shape and opens a closed existing
copy with strict normal recovery. It rejects missing metadata/checksum damage.
It can synchronize a complete unacknowledged tail or remove an allowed incomplete
unprotected tail according to the normal engine recovery policy. Verification is
not a forensic read-only scanner. It does not initialize a missing directory.
Never run a writable backup identity alongside its original as an application
fork; stop the original before restoring the entire directory.

`POST /api/compaction-advice` takes `{"retain_commits":"128"}`. The suggested
floor keeps that many commits, respects the oldest active subscriber and never
regresses the current floor. Recommendation becomes true at 70% WAL-cap pressure
with reclaimable history. The advisor changes nothing and does not estimate
exact reclaimable bytes or guarantee latency. Persisted external cursors and
revisions do not register pins; choose retention policy accordingly. Recheck via
the protected compaction API, which checks pins again at execution time.

## Named indexes

`POST /api/index-create` takes
`{"name":"tasks-status","prefix":[116,97,115,107,115,47],"path":["status"]}`.
Names are 1–64 ASCII letters/digits/underscore/hyphen. Prefixes are byte arrays
of at most 4096 bytes, paths use the JSON bounds above, and at most 64 definitions
may exist. Creation is an ordinary validated durable transaction; duplicate names
conflict. `/api/index-list` takes `{}`, `/api/index-drop` takes `{"name":"..."}`,
and `/api/index-search` takes `{"name":"...","value":"open"}`.

Definitions live under the reserved application convention `\0polybase/index/`.
Do not write that prefix through raw byte APIs. The engine does not add a new
storage namespace or prevent raw users from modifying it; malformed definitions
fail explicitly. Exporters using all-key snapshots must account for these rows.
Definitions recover with the WAL and are included in backups. Actual postings
are the existing bounded derived JSON equality index and rebuild from canonical
state after reopen. Its budget can fall back to a verified full scan, reported by
`indexed:false`. This named search retains the current-head search scalar
encoding semantics: numeric 1 and 1.0 have distinct index terms. Typed live
JSON predicates instead use the mathematical comparisons documented above.
Definitions are resolved in a validated metadata read before
the search captures its own head; concurrent drop does not cancel a started
search. No uniqueness, compound ordering, persistent index file or automatic
historical planner is claimed.

## Clients and streaming

See [client usage](https://base.polymathlabs.xyz/preview-0-7.html#clients-and-streaming). TypeScript requires Node 24+ for direct
`.ts` execution, or compilation with TypeScript. Its strict check is pinned in a
lockfile. The Rust client is a workspace library using standard-library blocking
TCP with serde/serde_json. Both cap requests at 128 KiB and responses at 8 MiB,
use loopback origins and a five-second socket/request timeout, and avoid automatic
write retries. Server operations can outlive timeout/cancellation.

The engine `Stream::next_timeout` polls at 10 ms intervals, bounded to 30 seconds
per call. TypeScript's async generator polls only on consumer demand, yields a
complete page, and advances its in-memory cursor when the consumer asks for the
next page. It waits 25 ms on idle polls. Persist applied rows and cursor together
before requesting another page. On errors, preserve that pair and explicitly
resume; the client never silently resnapshots or substitutes a new write identity.
This is a polling stream with backpressure, not SSE/WebSocket transport. Server
leases can expire while consumers pause; delivery can repeat after recovery.

## Acceptance and reproduction

```sh
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --all-features --locked -- -D warnings
cargo test --workspace --all-features --locked
cargo test -p polybase-engine --locked
node --test scripts/test-console.mjs scripts/test-cluster-console.mjs website/test-release-inputs.mjs
npm --prefix clients/typescript ci --ignore-scripts
npm --prefix clients/typescript run check
npm --prefix clients/typescript test
python3 scripts/run-preview7-bench.py target/preview7-evidence --runs 3 --records 128 --fault-seeds 7 41
```

These Cargo and benchmark commands are source-maintainer workflows, not commands
available from the binary-only evaluation package. The packaged fault lab and
HTTP clients can run independently of the private database source.

Use a new empty benchmark destination. The benchmark records source tree digest,
dirty status, binary hash, toolchain, host, profile, cache policy, input sizes,
raw timings and correctness assertions. Fault lab traces preserve acknowledgments,
partitions, leader changes, kills, restarts and verification outcomes. Seed controls
schedule selection; kernel scheduling and port assignment are not deterministic.
The lab never controls a pre-existing cluster, resets voter state or kills an
unowned process. Existing model/protocol and SIGKILL suites remain required.

Cross-platform release qualification and website publication are separate from
local validation. The production website continues to require clean-source,
matching, runtime-verified Linux and macOS packages. A preview build is not
publishable and must not advertise an unqualified downloadable release.
