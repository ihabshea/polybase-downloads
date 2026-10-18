# Polybase 0.9.0 distribution qualification

Both published targets use clean private source `4dccc0ff6593f044c6fb9237ca7c7bd891b4ec45` and Rust 1.99.0.

| Target | Archive bytes | SHA-256 |
| --- | ---: | --- |
| mac | 2,890,967 | `f8f984f51e918833873b8782ea839dccabcfd21f9f44bc8da3bdd887e1ebd353` |
| linux | 3,409,169 | `39b1970d6d2fc51839f125380d67d5b9ab70436c2bb55add9525b7a05b87e416` |

Each target passes 21 extracted-runtime checks, ten rejected unsafe or altered
archives, five runnable documentation cases, staging checksum-symlink protection
and seven bidirectional upgrade checks against the anonymously downloaded 0.8.2
release. Those checks include Janus history, private-pipe embedding, corruption
refusal, retained positions, stable cursors, named retries and complete commits.

Mac execution is native on Apple Silicon macOS 15.1. The published Linux package
is built and tested under Docker amd64 emulation on Apple Silicon, with Ubuntu
22.04/glibc 2.35 and network egress disabled. Its resolved build image is
`sha256:540da88889420c7848f86bc3b9bd973d9bd33e066981f6717e8774f699779462`.
The earlier native Linux candidate had a different archive hash and remains
separate historical evidence. The source engine tree is identical to the
recorded native benchmark implementation; emulated acceptance is not a new
native performance measurement.

The Mac upgrade fixture preserves every assertion from `tools/upgrade-check.py`
and binds its OLD_SHA to the independently verified published Mac archive hash
`688d0d9296a052c1fd6862547a11fde233220b4274bec3c59f30daeb5ecc0d9c`.
The original Linux baseline hash remains
`dbec2441bde1cb880c931459ff8b23c14aa68accb5fcb154d587ede00a88eb10`.

Two initial Linux staging checks timed out during a release rebuild under
emulation. The failure logs are retained in `linux/staging-timeout`. A verbose
build completed the missing executable, then the original unchanged test passed
within its original 120-second deadline. Source, assertions and staged archive
bytes were preserved throughout; `linux/rebuild-diagnostic.log` records the build.

The standalone black-box verifier and runnable examples are in `tools/`. Run
`python3 tools/scripts/verify-release.py ARCHIVE --runtime --report replay.json`,
`python3 tools/scripts/test-release-package.py ARCHIVE` and
`python3 tools/website/verify-examples.py ARCHIVE --report documentation.json`.
Runtime checks execute the verified local executables using disposable data.

The website passes 196 responsive checks, 80 accessibility scans and seven
behavior checks. Its production HTML, styles, scripts and images match the
browser-qualified bytes exactly; only the separately guarded release metadata
and checksum files change from the local preview.

All 227 workspace tests, formatting, strict Clippy, 181 default-feature engine
tests, Rust 1.89 compatibility, strict rustdoc and real-server TypeScript tests
pass locally. Hosted CI did not start because of account billing/spending limits.
These checks do not establish power-loss guarantees or universal performance.
