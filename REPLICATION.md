# Polybase packaged three-node research lab

This guide applies to the extracted evaluation archive. No Rust, Cargo or
private source checkout is needed. The local database and replicated partition
have separate directories, identities, positions and contracts.

## Start the supplied executables

From the extracted `polybase-...` directory, with Python 3.10 or later:

```sh
python3 scripts/start-local-cluster.py ./my-lab --bin-dir ./bin
```

The launcher creates a new empty lab with a random partition identity, voters
1–3 on loopback ports 7351–7353 and a cluster console at
http://127.0.0.1:7342. It preserves existing configuration/history and rejects
missing bound directories. Choose another console port with `--console-port`;
`--node-ports` chooses three ports only when creating a new binding.
Do not overwrite an existing cluster configuration or copy live voting data.

The processes are detached. Closing the cluster console closes only that console;
nodes remain running. Logs and observed PIDs are under `my-lab`. Before signaling
a process, verify its current command belongs to this lab. An old PID file alone
is insufficient. Never delete a live ownership lock or stop an unrelated service
to make these ports available.

To restart an already initialized lab manually, first stop its owners and retain
the original `my-lab/cluster.json` and node directories. Run these in separate
terminals, where Ctrl-C stops the process in that terminal:

```sh
./bin/polybase-node ./my-lab/cluster.json 1 ./my-lab/1 --lab-controls
./bin/polybase-node ./my-lab/cluster.json 2 ./my-lab/2 --lab-controls
./bin/polybase-node ./my-lab/cluster.json 3 ./my-lab/3 --lab-controls
./bin/polybase-cluster-console ./my-lab/cluster.json 7342
```

The optional `--lab-controls` exposes explicit isolation/reconnection/election
experiments. It is not public-network administration or authentication.
All four tools support `--help` and `--version` without opening storage.

## Writes, reads and retry horizons

Select the observed leader for writes and quorum-confirmed reads. A successful
write acknowledgment follows durable majority acceptance and durable local
commit/application publication. It does not establish freshness on every
follower. Local reads show only that node's committed/applied prefix; an explicit
index/term minimum can reject with `behind` or expired history.

Conditional byte batches apply all mutations together or choose a durable
no-mutation outcome. Log indexes also include barriers, rejected commands and
duplicate attempts, so application events can have gaps. Identical retained
request tokens and intent return the original outcome across leaders. Different
intent rejects. Keep the original token and exact intent after a lost response,
timeout, leader change or persistence failure. Absence is not cancellation;
expired/mismatched outcomes need reconciliation, never an automatic fresh ID.

Queries combine byte-key ranges and whole-value predicates. A filtered snapshot
at S and complete transaction deltas strictly after S share this partition's
history. Save the applied result with its cursor; delivery can repeat. Old query
cursors can expire after explicit snapshot/compaction. Physical compaction keeps
still-valid request outcomes; their expiry is a separate ordered operation.

## Limits and storage care

Defaults include 512 retained protocol entries / 4 MiB, 128 KiB application
commands, 512 KiB state / 4,096 keys, 256 retained outcomes / 512 KiB canonical
intent, and one 2 MiB snapshot transfer in 64 KiB chunks. Admission and peer queues
are bounded. Explicit maintenance is necessary as caps are approached; a full
uncommitted log can require investigation, never deletion of committed history.
These are logical limits, not hard RSS or latency promises.

The outer `REPLICA` binding and complete inner `store/` are one durable unit. Stop
owners and copy the whole closed directory for backup. Missing bound storage or
checksum corruption fails closed. Do not reset a voter, restore stale voting
history into an active partition or run writable copies of one identity.
There is no online backup, automatic repair or membership replacement.

This is one immutable three-voter partition on one host. It provides no TLS,
authenticated public networking, Byzantine safety, dynamic membership, sharding,
cross-partition transactions, global order or proven host-failure availability.
Process crash tests do not certify sudden hardware power-loss tolerance. See
the included GUARANTEES.md and README.md for the complete evaluation boundary.
