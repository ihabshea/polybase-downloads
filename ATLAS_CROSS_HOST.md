# Atlas: enrolled cross-host fault execution

`scripts/atlas-cross-host.py` is a controller and SSH stdio agent for three
operator-enrolled independent Linux hosts or isolated VMs. It generates and
records directed TCP fault schedules, launches real `polybase-node` processes,
captures their observations, and runs the independent Atlas checker. Python 3.10+
and OpenSSH are sufficient for the controller. The agent requires Linux `/proc`,
Python 3.10+, and a matching immutable node artifact; it does not require root.

**Actual cross-host qualification has not run in the provided environment.** The
user selected continued local development with this gate open. Read-only
inspection on October 25, 2026 found one container, no `/dev/kvm`, no QEMU or
libvirt, no effective Linux capabilities, no cloud identities or SSH host
enrollment, no VPN, and no enrolled TCP destinations. The managed Docker daemon
is containerized; additional containers would share its kernel and clocks.
Container or local process counts therefore cannot satisfy the three-host gate.
The runner neither discovers credentials nor provisions paid resources.

## Enrollment and trust

Copy the templates in `examples/atlas/` outside the repository and replace every
placeholder using actual deployment evidence. All attestation flags deliberately
default to false. They cannot be inferred from three different hostnames.

For each host, the operator must provide:

- A distinct physical host or isolated VM with its own kernel boot identity,
  independently controllable network, clock and durable storage. Record VM/host
  and volume identifiers in `independence_attestation.evidence`. The controller
  checks unique machine and boot hashes, rejects recognized containers, and
  requires this explicit attestation. Software-visible IDs alone cannot prove
  infrastructure independence or an honest administrator.
- An unprivileged SSH account, a pinned SSH host key, and a separately verified
  SHA256 of the stripped `/etc/machine-id` text. No `StrictHostKeyChecking=no`,
  first-use auto-accept, SSH agent forwarding or interactive login is used.
  Obtain host-key fingerprints through an existing trusted channel; `ssh-keyscan`
  alone is not identity verification. Control traffic uses SSH; peer traffic
  requires an already trusted private network or operator-managed secure tunnel.
- The same immutable `polybase-node`, artifact manifest and this Python agent on
  all three hosts. Pin their actual source SHA, executable SHA256 and agent
  SHA256 in the inventory. The manifest records build command, toolchain and
  target. The read-only handshake recomputes hashes and invokes `--version`;
  these are operator provenance statements, not reproducible-build attestation.
- Existing UID-owned evidence scratch and a **dedicated mounted ext4, XFS or
  Btrfs filesystem of at most 256 MiB** for disposable replica data. A 128 MiB
  disposable block volume or loop-backed ext4 mount is suitable. Provision and
  mount it separately as an administrator; the runner never formats, mounts or
  resizes storage. Scratch must be on another filesystem. No unrelated process
  or data may use the dedicated volume. Filling a shared filesystem is refused.
- Explicit allowed peer IP/port and local proxy-port mappings in the host's
  enrollment file. Permit node-port ingress only from the other enrolled hosts.
  The agent binds its peer proxies to loopback and refuses destinations outside
  the enrollment allowlist. Agent, enrollment, manifests and binaries should be
  immutable to other accounts. Keep the controller inventory and SSH keys out of
  published evidence if they contain private infrastructure identifiers.

Each node listens on its enrolled private IPv4 address. `AtlasNetworkConfig`
uses `genesis: [1,2,3]`, `transport: "trusted_private"`, and per-source `routes`
through that source's local TCP proxies. The controller starts the new opt-in
`--atlas-network --lab-controls` mode and requires a real `hello` response with
`protocol: 2`, `transport: "trusted_private"` and named retry support. Existing
loopback configurations are not silently reinterpreted. The peer protocol is
checksummed, not authenticated; exposing it to untrusted networks is outside
this qualification scope.

The agent's protocol-1 `handshake` reads the enrollment and artifact, returns
version/hash, machine/boot hashes, kernel/architecture, monotonic clock resolution,
UTC sample, virtualization, mount and independence evidence. It creates no run
directories or database processes. Later requests use a connection-local random
ownership token and UID-checked run marker. The only executable launched by the
agent is its explicitly enrolled binary; there is no arbitrary shell command API.

## Commands

Build the node and independent checker from the same reviewed source:

```sh
cargo build --release --locked -p polybase-cli --bin polybase-node
cargo build --release --locked -p polybase-engine --example atlas_verify
python3 scripts/atlas-cross-host.py self-test
```

CI can require the checker codec test with
`self-test --checker-binary target/debug/examples/atlas_verify` after building
that example. An explicitly supplied missing binary fails. Without this option,
the test uses an existing release/debug binary or reports the checker codec test
as skipped; it never builds an engine automatically or counts tool tests as
cluster schedules.

Deploy the built node, script and filled enrollment/manifest files with your
existing administrator workflow. No deployment command is run automatically.
The inventory's `known_hosts` path belongs to the controller; remote paths belong
to the enrolled host. Use actual SHA256 digests, not the template values.

Perform read-only host inspection first:

```sh
python3 scripts/atlas-cross-host.py inspect \
  --inventory /absolute/path/atlas-inventory.json \
  --output target/atlas-host-inspection
```

Then execute three measured smoke schedules, one per profile:

```sh
python3 scripts/atlas-cross-host.py run \
  --inventory /absolute/path/atlas-inventory.json \
  --checker target/release/examples/atlas_verify \
  --seed 20261025 --schedules 3 \
  --output target/atlas-cross-host-smoke
```

A full cross-host campaign additionally requires clean, unchanged local source
matching the enrolled artifact source, at least 10,000 actual schedules, all three
profiles, all supported observations checked, and measured evidence for every
declared network fault type:

```sh
python3 scripts/atlas-cross-host.py run \
  --inventory /absolute/path/atlas-inventory.json \
  --checker target/release/examples/atlas_verify \
  --seed 20261025 --schedules 10000 --profiles lan wan asymmetric --qualify \
  --output target/atlas-cross-host-qualification
```

Output directories must be empty. A failed handshake, missing independent host,
missing actual fault evidence, checker violation, checker resource exhaustion,
unsupported observation, changed executable/source, missing log or incomplete
export fails qualification. The script never changes `release_qualified` to true:
membership, historical queries, upgrade, performance and the larger concurrent
history campaign remain separate Atlas release gates.

## Schedules and observed faults

LAN uses 2 ms base directed-link delay, WAN 40 ms, and asymmetric uses 12 ms in
one direction and 36 ms in the reverse. These are injection settings, **not
measured network latencies**. A seed selects distinct receive ordinals for loss,
extra delay, duplication and reordering on every directed link. The full chosen
rules and every actual receive, forward, error and timing observation are saved.
Changing process scheduling can change which consensus message occupies an
ordinal; repeatability means the same workload and rules, with the new execution
trace measured again. It does not promise identical OS scheduling or elections.

Each schedule includes ordinary atomic two-key writes, directed impairment,
bidirectional minority-leader isolation, an all-voter partition, the stale
leader's return, and SIGKILL while a real asynchronous client request is
outstanding. The agent verifies that the owned child's listener inode belongs to
the child, checks the handshake's exact partition/node/genesis, and requires the
actual SIGKILL timestamp to fall inside the agent's client-operation interval.
A timeout is retained as unknown until a terminal named receipt resolves it.
An absent lookup does not resolve uncertainty: the same token and exact intent
are retried within a bounded budget until Applied/Conflict is captured, or the
schedule fails. An applied named retry must preserve position, term and outcome.
Local reads are checked as stale committed-prefix reads; they are never promoted
to quorum reads by labelling them differently.

For stale-follower recovery, the controller stops a follower, advances and
compacts the leader, restarts the follower and interrupts an actual `Install`
RPC after sending only part of its frame. The proxy records its frame hash,
full size and actual prefix bytes sent before disconnecting. A later transfer
must recover exact reference state. **This exercises interrupted network
transfer, not termination at a durable snapshot-installation boundary.**

For disk-full recovery, the agent writes only its owned filler on the dedicated
volume, within the 256 MiB bound, until it receives actual errno 28 (`ENOSPC`).
It then requires an actual follower persistence error in peer replies or node
logs while a replicated write runs. Merely filling the volume does not count as
an engine I/O fault. It records the response, terminates or observes the fenced
follower's exit, removes only its filler, restarts and checks reference parity.
`RLIMIT_FSIZE`, a modeled error, or `EFBIG` cannot substitute for this evidence.

The proxies use actual TCP connections and complete protocol-2 Atlas peer RPC
frames. Loss drops a whole frame; duplicate sends it twice; delay records actual
elapsed wait; reorder holds one bounded frame and forwards a subsequent frame
before releasing it. Expiry without a second frame is logged separately and
does not count as observed reordering. Each proxy has at most four workers,
one held frame, a 2 MiB frame limit, a bounded listener backlog and finite socket
deadlines. The proxy never fabricates a client write acknowledgment. These are
application-message network impairments, not a claim about arbitrary IP-fragment
corruption, NIC queues or host-global `tc` shaping.

## Checker and evidence

Every supported write, snapshot and named-outcome observation is converted to
the public `atlas_support::checker::History` schema. Controller monotonic times
provide common invocation/response intervals across nodes. Independent host
monotonic clocks stay in raw logs and are never compared as a shared clock.
Raw replies remain present alongside the conversion. The converter checks
durability, mutation and consistency-mode flags, preserves canonical token
identity and uncertainty, and refuses unsupported value filters or receipts.

Histories are segmented at verified reference boundaries to respect the
checker's 64-operation bound. A boundary requires resolved ambiguous outcomes,
exact all-node reference convergence and a successful matching quorum snapshot.
The next segment carries that exact position, reference rows and all retained
named receipts, including conflicts. All supported observations are retained in one of the segments; the
reference state is linked to previously checked operations rather than invented
from an unchecked engine result. Each segment runs the actual standalone
`atlas_verify --replay-history` checker. Violation, inconclusive and invalid all
fail the schedule. This segmented workload is distinct from the separate
50,000-history concurrent cluster campaign; it does not add to that count.

The output preserves inventory, read-only handshakes, source/checker/executable
hashes, every seed/rule, exact runtime configs, client invocation/response
transcripts, process PIDs/signals, proxy event logs, node output, independent
checker inputs/results/witnesses, reference rows, unknown outcomes and remote
data-file hashes. Successful runs export evidence before deleting **only their
owned replica-data subdirectory** so 10,000 schedules can reuse the bounded fault
volume. Remote scratch evidence remains. Failure data remains on the host; an
SSH disconnect triggers bounded child/proxy cleanup and retains owned state.
The runner does not delete an existing replica or retry into its directory.

To repeat one preserved schedule with new measurements:

```sh
python3 scripts/atlas-cross-host.py run \
  --inventory /absolute/path/atlas-inventory.json \
  --replay-schedule target/atlas-cross-host-smoke/schedule-00000/schedule.json \
  --output target/atlas-schedule-replay
```

To replay only its independent checker evidence:

```sh
target/release/examples/atlas_verify --replay-history \
  target/atlas-cross-host-smoke/schedule-00000/checker-history-00.json
```

Controller self-tests use explicitly synthetic enrollments and loopback codec
peers. They verify corruption/length handling, identity/artifact/disk refusal,
actual proxy loss/delay/duplication/reordering/partial transfer, conversion of
unknown outcomes, rejection of misleading flags, and a wrong-value negative
control through the real independent checker when built. They produce no
cross-host result receipts. `plan` similarly emits `unexecuted_schedule_plan`
with `qualifying_results: false`; it cannot satisfy a measured schedule count.
