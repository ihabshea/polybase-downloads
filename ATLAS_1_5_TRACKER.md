# Project Atlas — release readiness

**0 / 10 full release gates qualified.** The implemented candidate has local
evidence; it is not a qualified distributed release. The user chose local
continuation with the three-host gate open.

The immutable first run at `333c2f0ecf25c5987087f7cecc0bcd9fe269af73` passed
50,000 tmpfs-backed, same-process Replica histories and a separate 1,000
overlay-backed histories. The public standalone reference verifier independently
rechecked the stored observations. Those reopenings are not process deaths or
cross-host faults. A separate rolling run recorded eight actual SIGKILL restarts
and verified the supported fixed-mode version pair.

The first unchanged paired benchmark passed all 36 cold-history p95 targets and
missed seven of twelve current-head p50/p95 targets. Its raw samples and source
remain a counterexample during focused follow-up optimization. The baseline and
workload have not changed. New measurements are required before assigning the
follow-up source any performance claim.

- [ ] No acknowledged quorum commit loss.
- [ ] No partially visible transactions.
- [ ] No split-brain committed histories.
- [ ] No incorrect retained-position query results.
- [ ] Interrupted elections and snapshot transfers pass.
- [ ] Voter replacement survives faults.
- [ ] Supported rolling upgrade paths pass.
- [ ] Independent checker passes 50,000 generated cluster histories with no inconclusive pass.
- [ ] Full immutable campaign and provenance published, including 10,000 real cross-host schedules across three profiles.
- [ ] Every declared fixed-baseline performance gate passes repeated paired runs.

Local model, durable single-host scheduler, TCP process and actual cross-host
results must have distinct counters. The [release contract](ATLAS_1_5.md) defines
the required evidence and limits. The existing Cerberus local campaign is retained
unchanged and is not counted toward these distributed targets.
