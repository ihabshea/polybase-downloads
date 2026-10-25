# Project Cerberus — acceptance tracker

**6 / 6 engineering acceptance checks complete.** The full campaign passed on clean source `54c92946abbaea30bae25e2e8178676e17cbd9e8`, with identical before/after source fingerprints. Publication remains a separate candidate gate; no downloadable 1.0 release is claimed.

- [x] Named failpoints reach WAL, synchronization, publication, checkpoint, snapshot-installation and compaction boundaries: all 33 required points, 1,056 primary cases and 1,116 actual SIGKILL deaths pass. Acknowledged commit losses and partial batches are zero; 180 publication kills had maintenance pending.
- [x] All 10,000 generated concurrent histories have valid real-time-compatible reference witnesses across 220,000 operations, with zero mismatches, inconclusive checks or invalid traces. Deterministic stored-trace replay passes.
- [x] Every retained position in the recorded workloads passes point, byte-range, typed JSON and whole-word reference checks across maintenance and reopen: 242,364 cumulative position audits, 5,816,736 quiescent queries and 160,000 concurrent historical observations.
- [x] All 1,000 independent byte/structural corruption cases reject or recover a verified valid boundary: 875 strict rejections, 100 preserved boundaries and 25 complete unacknowledged commits, with zero silent corruption in scope.
- [x] Failure artifacts retain seed, minimal permitted operation history, failure point, version and deterministic trace/engine replay commands. Reducer self-tests pass; context-preserving 1-minimality and budget limits are explicit, without a globally shortest claim.
- [x] Formatting, strict Clippy, full workspace tests, compatibility checks, raw campaign evidence and publication prerequisites are recorded. Post-campaign website evidence is recorded separately from engine qualification.

Extra credit passes: 64 identical generated Rust/Node histories using candidate SDK 0.9.0 sources have equivalent observable results, with 70,016 SDK calls and 5,376 historical-position checks. A public independent Python validator additionally checks all 10,000 supplied witnesses and stored head/events; it does not search or re-evaluate historical predicates.

The accepted valid-CRC forgery control demonstrates the non-authentication limit and is excluded from the passing damage count. Successful quiescent historical responses were checked live but are not all archived; offline replay covers stored payloads only. The [contract](CERBERUS_1_0.md) states those limits and the exact report hash.

The current download remains database 0.9.0 with published client SDKs 0.8.3. The engine/CLI 1.0.0 source is a candidate. Native release availability, registry publication and website deployment must be verified before claiming a published 1.0 build.
