# Polybase 1.0.0 native publication

The measured Cerberus campaign at `54c92946abbaea30bae25e2e8178676e17cbd9e8`
is preserved unchanged in the parent directory. This directory records native
distribution qualification separately. The production website compares package
implementation inputs with the measured source before publication.

Package source: `826f0bc0329e8c2e25333b60a8b9adf6d60c27d9`.
PR 20 merged at `ec58a594d757672de64bd4964db373e8352423f6`; its later website
and README changes leave packaged engine, client, build and bundled-guide inputs
unchanged. Both packages use pinned Rust 1.99.0 and default features.

The Mac archive runs natively on Apple Silicon. Linux build/runtime checks use
x86-64 Ubuntu 22.04 with glibc 2.35 under Docker emulation on Apple Silicon.
These final Linux runtime results are separate from the campaign's recorded
native Linux host. No successful hosted CI execution is claimed.

The public release retains the free binary evaluation terms, private engine
source, bounded local guarantees and separately versioned MIT SDKs (0.8.3).
SIGKILL does not establish hardware power-loss behavior; CRCs do not authenticate
files. Prior-version performance reports retain their original source identities.
