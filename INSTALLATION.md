# Use the Polybase evaluation download

Project Janus adds read-only historical point, range, JSON and whole-word queries
at one exact retained commit. See [historical execution](JANUS_0_9.md) for the
verified horizon, bounded reconstruction, explain output and limitations.

The 0.8.2 optimizer compares bounded scan and indexed execution, combines eligible
AND/OR predicates, and can restart a query under its original captured head. See
[adaptive query execution](PREVIEW_0_8_2.md). The earlier
[0.8 planning reference](PREVIEW_0_8.md) records the original planner contract.

The 0.7 API additions are documented in [the feature reference](PREVIEW_0_7.md):
typed live JSON queries, stable pagination, revisions, online backup and verification,
query metrics, Rust/TypeScript clients, retained historical reads, compaction advice,
named equality indexes, demand-driven streams and the expanded replication lab.

Polybase 0.9.0 is a free database evaluation preview. The package runs
locally without Rust, Cargo, Node, Docker or a cloud account. Its source is private.
The hosted SaaS is coming soon and is not available in this download.

## Requirements and installation

Choose the archive matching your machine:

- `aarch64-apple-darwin`: Apple Silicon Mac, macOS 15 or later. Executables are
  ad-hoc signed; there is no Developer ID signature or notarization.
- `x86_64-unknown-linux-gnu`: x86-64 Linux, glibc 2.35 or later (Ubuntu 22.04+).

Windows, Intel Mac and ARM Linux builds are not included in this release. Use a
local filesystem that supports advisory locks, atomic rename and file/directory
synchronization. Network filesystems and live external file modification are
unsupported. Keep synthetic or disposable data in this evaluation preview.

Download the archive and its `.sha256` file from the same versioned release. On
macOS run `shasum -a 256 -c ARCHIVE.tar.gz.sha256`; on Linux run
`sha256sum -c ARCHIVE.tar.gz.sha256`. The checksum verifies agreement with the
downloaded checksum file; it is not a publisher signature. Extract with
`tar -xzf ARCHIVE.tar.gz`, then change into the resulting `polybase-...` directory.
Do not run installation commands with sudo.

On macOS, if Gatekeeper blocks an executable, review the download and use Apple's
System Settings > Privacy & Security > Open Anyway procedure if you choose to
allow it. The preview does not require disabling Gatekeeper globally. See
https://support.apple.com/guide/mac-help/open-a-mac-app-from-an-unknown-developer-mh40616/mac.

## Start with a local database

From the extracted directory, run:

```sh
./bin/polybase --version
./bin/polybase init ./my-db
./bin/polybase batch ./my-db put projects/one active put projects/two planned
./bin/polybase get ./my-db projects/one
./bin/polybase events ./my-db 0 10
./bin/polybase snapshot ./my-db
./bin/polybase-console ./my-db
```

Open http://127.0.0.1:7340. Choose another port with
`./bin/polybase-console ./my-db 7341`. The console shows live local byte-key data.
Stage changes and explicitly commit a batch; closing a dialog is not a commit.
Expected values reject stale edits. Only one owner may open a directory, so stop
the console before using the CLI on that same database. Use Ctrl-C in its terminal
to stop it; reopen the same directory to recover committed records.

The CLI uses UTF-8 arguments. The console also supports hex bytes. Keys such as
`projects/one` are ordinary byte keys. The local Search panel filters JSON
scalar fields or whole words at one committed position; it does not create a
live cursor, SQL query or schema. Raw CLI writes have no named request identity.
A failed response can leave a write outcome uncertain; inspect recovered
state/events before retrying.

## Your records, your collections

Choose any collection name and record ID. Collections are key-prefix conventions:
`tasks/1` and `notes/1` are different records in the same database. There is no
collection to register first, and no required business fields or document schema.

```sh
./bin/polybase batch ./my-db \
  put tasks/1 '{"title":"Write a note","done":false}' \
  put notes/1 'A first note' \
  put sensors/room-a '{"temperature":21.5,"unit":"C"}'
./bin/polybase get ./my-db tasks/1
./bin/polybase get ./my-db notes/1
./bin/polybase snapshot ./my-db
./bin/polybase-console ./my-db
```

In the console, set **Collection / key prefix** to `tasks/`, `notes/`,
`sensors/` or a prefix you choose, and keep **Any value** selected to see all
records in that collection. Clear the prefix to see all collections together.
Include the trailing slash: `tasks/` excludes a separate prefix such as
`tasks-archive/`. The prefix remains a byte comparison, not a schema or hierarchy.

Stage keys from several collections to update them in one atomic transaction.
Records support insert, replacement and deletion, live query changes and recovery
after reopening. Values are bytes: JSON is stored as you supply it, without field
validation. Use the separate Search panel to match a nested field or whole words
within one collection prefix; run it again for subsequent commits. See the
[local search contract](SEARCH.md) for exact matching and limits. Use
**Hexadecimal** in the console for binary keys or values. These conventions also work in the optional three-node lab
within its single partition and documented bounds.

## Uncertain console writes and retention

The console saves the submitted token and exact intent in this tab's session
storage before sending it. After a timeout, inspect the durable request outcome.
If you explicitly retry, reuse that token and intent. An absent lookup does not
cancel another submission. Expired or mismatched tokens require reconciliation;
never replace an uncertain request with a fresh ID automatically.

Query snapshots and later deltas share an ordered local history. Save the applied
result together with its cursor; resuming may repeat delivery. Checkpoint keeps
retained history. Compaction can expire older cursors and named requests. The
default protection refuses to pass a live subscriber; forced expiry is explicit.
Storage caps reject writes rather than silently evicting history.

## Optional private-pipe embedding

The fifth executable, `polybase-stdio`, is an optional private parent/child pipe
for embedding current state. It accepts newline-delimited JSON `info`, `scan`,
`commit`, `compact` and `close` requests on standard input and emits one reply per
line. It opens no network listener and never retries a write automatically.
It does not expose the Janus historical or subscription API; it may compact
retained WAL before writes once that WAL exceeds 64 MiB. Use the local console
and documented historical HTTP or Rust API when you need retained time travel.

## Optional three-node research lab

The package also contains `polybase-node`, `polybase-cluster-console` and the lab
launcher. Python 3.10 or later is needed only for the launcher:

```sh
python3 scripts/start-local-cluster.py ./my-lab --bin-dir ./bin
```

Open http://127.0.0.1:7342. This lab uses separate data from `my-db` and three
loopback ports (7351–7353). Select the observed leader for writes and
quorum-confirmed reads. Local reads can be stale and name their applied position.
Majority acknowledgment does not imply every follower has applied the write.
The supplied processes are detached: closing the cluster console leaves nodes
running. Logs and observed PIDs are in `my-lab`. Stop only the processes you
started, checking each PID's command before signaling it; never kill a process
solely because its number appears in an old PID file. Rerunning the launcher
preserves existing configuration and voting history. It refuses missing bound
directories or occupied console ports. Do not delete `LOCK` files or reset a
voter to make it start. See REPLICATION.md for manual startup and protocol limits.

This is one fixed partition with three voters on one host. It provides no
authenticated public networking, TLS, membership changes, sharding or
cross-partition transactions. Keep it on loopback. It is a research lab, not a
hosted service or a production cluster deployment.

## Back up and investigate failures

Stop every owner, then back up the entire closed database directory together,
including identity/manifest files and selected generations. A replica's outer
binding and entire inner store are one unit. There is no online backup or repair
command. Do not restore an old voter into a running partition or run writable
copies of the same identity. Corrupt selected files fail closed; keep them intact
for investigation. Never delete checksummed metadata or an acknowledged WAL
prefix to bypass an error.

Success follows WAL and frontier synchronization, atomic rename, directory
synchronization and publication. These are implemented process/recovery
boundaries, assuming the filesystem and hardware honor synchronization. Process
crash tests do not establish sudden power-loss tolerance or production fitness.
Read GUARANTEES.md for exact API contracts and bounds, LICENSE for permitted
evaluation use, and THIRD_PARTY_NOTICES.txt for dependency licenses.
