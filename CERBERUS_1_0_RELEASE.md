# Project Cerberus — 1.0.0 release

Cerberus qualifies the local engine under deterministic process termination,
overlapping transactions/maintenance, retained historical reads and independent
byte/structural corruption. Default production formats and existing observer APIs
are unchanged; named crash rendezvous are opt-in test features.

The clean-source run at `54c92946abbaea30bae25e2e8178676e17cbd9e8` passes:

- 10,000 distinct seeded histories with valid real-time-compatible witnesses for
  220,000 recorded operations. No mismatch, invalid trace or inconclusive result.
- 1,056 termination/restart cases and 1,116 actual SIGKILL exits across all 33
  named boundaries. No acknowledged commit loss or partial batch; 180 publication
  kills had maintenance callers pending.
- Every retained position in the recorded workload: 242,364 cumulative position
  audits and 5,816,736 quiescent point/range/typed JSON/text checks, plus 160,000
  concurrent historical queries.
- 1,000 covered damage cases: 875 strict rejections, 100 preserved verified
  boundaries and 25 complete unacknowledged commits recovered. No silent
  corruption within this scope.
- Extra credit: 64 Rust/Node programs, 70,016 actual SDK calls and 5,376
  historical-position checks, with both clients matching an independent model.

A separate standard-library Python validator verifies all 10,000 supplied
successful witnesses and 40,000 stored full-head/event observations. It does not
invoke the engine, search for witnesses, authenticate the recorder or replay
unstored historical-query payloads.

**Checksums are not authentication.** The separately archived negative control
accepts a fully consistent earlier WAL rewrite with recomputed CRCs and returns
a forged older value. This was explicitly excluded from the agreed qualification
scope and is not included among passing corruption cases. SIGKILL qualification
also does not simulate hardware power loss. Passing bounded generated histories
is evidence for those observations, not a formal proof of every schedule.

[Full report, raw compressed traces, receipts and independent verifier](qualification/1.0.0/README.md)
· [Contract](CERBERUS_1_0.md) · [Engineering tracker](CERBERUS_1_0_TRACKER.md)

The database source remains private. Matching 1.0.0 Mac and Linux evaluation
archives, checksum sidecars and extracted-runtime receipts are distributed in
[the versioned release](https://github.com/ihabshea/polybase-downloads/releases/tag/v1.0.0).
Published client SDKs remain independently versioned at 0.8.3. The original
campaign evidence is preserved unchanged; native-package publication records
are retained separately under `qualification/1.0.0/publication/`.
