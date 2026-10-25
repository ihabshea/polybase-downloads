# Independent Atlas recorded-observation QA

These MIT-licensed tools validate **supplied recorded observations**. They contain
no Polybase engine, server, storage, replication implementation or private
application data. The database source and release binaries have separate terms.

A passing result means the supplied observations fit the bounded reference
specification. It does not establish that the recorder executed an engine,
captured every call, used the claimed source revision, survived a hardware fault
or ran on independent hosts. It does not qualify a release by itself.

## Build and test

Rust 1.89 or later and Python 3.10 or later are required. The Rust package pins
`serde` and `serde_json` and includes `Cargo.lock`. It has no engine dependency.

```sh
cargo build --release --locked \
  --manifest-path atlas-history-checker/Cargo.toml \
  --target-dir /tmp/atlas-public-checker
cargo test --locked --manifest-path atlas-history-checker/Cargo.toml \
  --target-dir /tmp/atlas-public-checker
cargo clippy --all-targets --locked \
  --manifest-path atlas-history-checker/Cargo.toml \
  --target-dir /tmp/atlas-public-checker -- -D warnings
python3 -B test-audit-atlas.py \
  --checker /tmp/atlas-public-checker/release/atlas-history-checker -v
```

The unchanged independent reference module is `atlas-history-checker/src/checker.rs`,
SHA-256 `9b9e18dd96d112b531183815260e71434680fcdb74cb28566486a3b8cba31e7e`.
It has 23 synthetic selftests, including separate exhaustive small-state oracles.
Synthetic test counts are never measured engine-history counts. The command-line
and Python negative controls separately reject malformed input, false observations,
invalid ordering, wrong counters, uncertain qualification results and truncated
archives.

## Check the captured local campaign

Run from this directory, supplying the exact source/version/count for the chosen
campaign. Multiple input shards are streamed through **one persistent checker
process**; the tool does not launch one process per history.

```sh
python3 -B audit-atlas-traces.py \
  /path/to/campaign/local-durable-*/histories.jsonl.gz \
  --checker /tmp/atlas-public-checker/release/atlas-history-checker \
  --expected-source 333c2f0ecf25c5987087f7cecc0bcd9fe269af73 \
  --expected-version 1.5.0-preview.1 \
  --expected-count 50000 \
  --report NEW-audit.json \
  --witnesses NEW-witnesses.jsonl.gz
```

Plain JSONL and gzip are detected by magic bytes. Each line is limited to 16 MiB;
at most 100,000 histories are accepted. Duplicate JSON object fields, NaN/infinity,
invalid bytes, duplicate IDs/seeds across shards, mixed provenance, truncated
streams and invalid/inconclusive search results fail closed. Report and witness
destinations must be new files. To pin artifact identity, supply one `--sha256`
option per input in the same order. Without expected file hashes, embedded source
labels remain unauthenticated recorder claims.

The audit independently validates:

- Client invocation/response boundaries, node/client IDs, calls, outcomes and
  monotonic clock order as stored in the schedule.
- Existing message references, unique identities, complete recorded terminal
  actions, duplicate links, cluster binding and snapshot-chunk boundaries.
- Every stored historical point response, concatenated byte-key range result,
  `n == 1.0` typed numeric result and `ATLAS shared` whole-word text result against
  a separate Python byte-map specification anchored by original named receipts.
- Conditional outcomes and ordered atomic mutations in those historical prefixes.
- Stored counters that can be reconstructed from the supplied observations.

The historical numeric oracle covers the generated small exact numeric classes;
it is not a general arbitrary-precision JSON implementation. No unrecorded
historical predicate or query is inferred. Raw historical events aggregate range
rows: individual page boundaries and continuation cursors are absent. Therefore
`historical_pages` is reported as a recorder-only counter. `message_reorders` also
includes decisions on dropped/delayed messages whose offsets were not stored;
only delivered reorder observations can be independently recounted. These two
counters are explicitly listed as unverified, rather than converted to measured
facts. Expiry events verify their stored below-floor relationship, not an
unstored error payload.

The Rust checker independently searches interval-compatible serial histories.
It treats unknown writes as possibly committed after their timeout, coalesces
canonical named request identities, checks exact conditional outcomes and atomic
batches, and returns a witness only after its independent model accepts one.
It does not use consensus-log order as proof of linearizability. Local reads are
checked against a declared committed prefix and may be stale; only observations
explicitly marked quorum receive the real-time linearizability requirement.
Recorded consistency labels and clock boundaries cannot authenticate the original
runtime implementation.

The report includes exact input-file and decompressed-stream SHA-256 hashes,
canonical History hashes, checker response hashes, tool/binary identities,
independently recounted observation totals and explicit false execution/deployment
claims. The gzip witness stream retains each input record hash, canonical history
hash and complete independent checker witness. Failure reports identify partial
streams; a checked prefix is never reported as a successful complete campaign.

## Standalone reference checker

The Rust CLI also accepts plain `History` JSON or `record.history`/`minimized`
envelopes, one object per input line:

```sh
cat supplied-histories.jsonl | \
  /tmp/atlas-public-checker/release/atlas-history-checker > NEW-results.jsonl
```

It emits one bounded JSON result per line and a final summary. Empty input,
violations, invalid input, exhausted search budgets and limit violations exit
nonzero. The default budget is 200,000 explored specification states per history;
`--budget N` permits 1 through 1,000,000. `--minimize-failures` retains every write
and its original context while deleting eligible read/outcome observations; its
reduction is context preserving, not a globally minimal engine/network replay.

The Python wrapper requires complete captured Atlas records. Use the standalone
Rust interface for plain histories with no stored transport/historical payloads;
those absent observations cannot be audited by the wrapper.
