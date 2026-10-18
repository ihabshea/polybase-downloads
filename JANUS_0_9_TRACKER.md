# Polybase 0.9 — Project Janus release gate

5 / 6 release gates complete. Engineering qualification passes; public release and deployment remain pending. Performance targets are reported separately from correctness.

- [x] Historical point and range reads with explicit retention errors.
- [x] Historical JSON and whole-word queries at one consistent commit position.
- [x] Explain estimates, actual work, selected route and fallback reasons.
- [x] Seeded differential and process-fault tests with reproducible failures.
- [x] Crash recovery, checkpoint and compaction preserve documented guarantees.
- [ ] Measured benchmarks, explicit limitations and reproducible artifacts published with final release availability verified.

## Engineering evidence

Clean implementation `6a123302edad0ed49cac541615b9719bb007d188` passes formatting, all-target/all-feature Clippy with warnings denied, 227 workspace tests, 181 default engine tests, Rust 1.89 compatibility and documentation checks. Fifty Node checks and real-server Rust/TypeScript compatibility suites pass. SDK 0.9.0 is a qualified candidate; registry availability remains 0.8.3.

The seeded reference-model gate passes 1,600 operations across seeds 20261018–20261025, 836 historical checks, eleven expired-page-cursor checks and 37 real injected-process crashes. Raw evidence and minimization limits are in [verification evidence](qualification/0.9.0/verification/README.md).

The valid 36-case historical matrix passes complete ordered reference/forced-Scan parity. Ninety-three concurrent historical reads and 24 atomic writer commits preserve results. All provisional warm historical targets pass. Seven of twelve current-head cases miss the 10% p50/p95 regression goal; every counterexample is retained. The largest cold p95 is approximately 1.996 seconds, and cumulative process peak RSS reaches 200,524 KiB. Shared-host conditions and uncontrolled OS caches limit interpretation.

The first matrix is retained as explicitly rejected supporting evidence because its source fingerprint changed; its missing original fingerprints are not invented. The final valid source/executable fingerprints and all raw samples are retained separately in [performance evidence](benchmarks/0.9.0/README.md).

The website has a deterministic, script-free commit-position explorer, explicit expiry and matching explanation. Final browser acceptance after the measured guide, homepage and release-note updates passes 196 responsive checks, 80 accessibility scans and seven behavior scenarios, with no violations, browser errors or external requests. The raw report is `docs/benchmarks/2026-10-18-janus/website-qa.json`; earlier decorative-font follow-up evidence is retained separately.

## Publication requirements

The database package version is `0.9.0`. Earlier 0.8.2 artifacts and receipts cannot qualify the new historical engine. Release preparation requires matching clean-source Apple Silicon macOS and x86-64 Linux archives, checksums, extracted-runtime checks including Janus history and the private-pipe executable, archive safety and documentation acceptance.

The production website guard remains enabled and now also requires the complete valid measured matrix with all target misses published. A local website preview and an unpublished package are review artifacts, not a deployed website or downloadable release. The existing live 0.8.2 release and published SDK 0.8.3 remain available.

Native Mac qualification is pending. Hosted CI previously failed before runner steps because of account billing/spending limits; no hosted pass is claimed. This environment has no Sites deployment capability and no registry publication credentials. Linux candidate qualification and public benchmark/source publication can proceed independently.
