# Project Janus publication status

The implementation and engineering qualification are complete. The release gate
remains **5/6** until matching native artifacts and actual publication are
verified. The live database remains 0.8.2 and the registry SDKs remain 0.8.3.

## Qualified inputs

- Measured implementation: `6a123302edad0ed49cac541615b9719bb007d188`.
- Frozen package/site source: `4dccc0ff6593f044c6fb9237ca7c7bd891b4ec45`.
- Both use engine tree `768dd1236194e4c6de833f09c1cdb86372fd24cc`.
- Clean public SDK source: `ba784366f9fe2a8a6bb9b233ea8113904c523b1c`.

The [engineering and client evidence](engineering.json) records 227
workspace tests, 181 default-feature engine tests, strict Clippy, formatting,
Rust 1.89 compatibility and documentation checks. Actual published 0.8.3 SDK
archives pass their original integration tests against the new server.

The [seeded and crash evidence](verification/README.md)
passes 1,600 operations, 836 historical checks, eleven expired cursors and all
37 injected process-crash scenarios. The [benchmark evidence](../../benchmarks/0.9.0/README.md)
retains every raw sample and counterexample: all 36 historical cases and warm
historical targets pass, while seven of twelve current-head cases miss the 10%
goal. Cold reconstruction reaches 1.996 seconds. The invalidated first run is
preserved separately and excluded from qualification.

## Native Linux and SDK candidates

The [Linux proof bundle](linux/README.md) includes
repeatable operational recipes. Native host and native Ubuntu 22.04/glibc 2.35
each pass 21 extracted-runtime checks, ten archive-rejection cases, five runnable
documentation cases and seven genuine 0.8.2/0.9 upgrade cases. Staging protection
passes. All five executables require at most GLIBC 2.34.

The local candidate is
`target/evaluation-release-0.9/polybase-0.9.0-x86_64-unknown-linux-gnu.tar.gz`:
3,408,862 bytes, SHA-256
`81b2fefea6e36dfcb726edbad5e4e502018fbd5a67611a23c0bac06f8e0ce83c`.
It is not yet a published downloadable release.

Clean public SDK archives pass client-only/MIT inventories and runtime checks
against that extracted native console, including the new historical methods.
[The package report](client-candidates.json) records
public Cargo provenance, exact archive hashes and commands. No registry
publication was attempted without usable authentication.

## Remaining publication actions

1. Build and qualify the Apple Silicon Mac package from frozen source
   `4dccc0ff6593f044c6fb9237ca7c7bd891b4ec45` with Rust 1.99.0. Run the runtime,
   archive, staging, documentation and upgrade checks. Earlier Mac artifacts do
   not qualify the new historical APIs. Hosted CI currently fails before runner
   steps, so it supplies no native Mac result.
2. Authenticate the registry publisher and publish the independently verified
   public SDK sources/artifacts. Before final publication, reconcile candidate
   installation/status text with the intended release and repeat package
   verification if any archive input changes. Actual checks returned npm `ENEEDAUTH` and
   Cargo `no token found`. Supply credentials through secure environment settings
   or an authenticated maintainer environment; no credential values belong here.
3. From the frozen source, prepare both matching native artifacts with
   `node website/prepare-release.mjs PATH_TO_BOTH_ARTIFACTS`, then run the
   production build/check and publish verified download assets. A real attempt
   using only the qualified Linux candidate correctly rejects the missing Mac
   artifact; [the gate receipt](publication-gate.json)
   records that refusal.
4. Deploy only the qualified static website payload through the existing Sites
   project, `appgprj_6ace7991702881918f3e306d5b5dbdec`, and verify the canonical
   hostname and public asset bytes. This environment has no Sites deployment
   capability. Final local website QA passes 196 responsive checks, 80
   accessibility scans and seven behavior scenarios; local QA is not deployment.

Later proof-only commits preserve the frozen binary and bundled-guide inputs.
The release-input guard remains enabled. Benchmarks use the recorded Rust 1.99.1
measurement executable; native distributions separately pin Rust 1.99.0. Neither
shared-host measurements nor SIGKILL cases establish universal latency or
hardware power-loss guarantees.
