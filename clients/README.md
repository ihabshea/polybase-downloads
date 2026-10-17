# Standalone Polybase clients

The Rust and TypeScript SDKs are MIT licensed. They connect to a separately
installed Polybase console on IPv4 loopback; the database engine remains private.
SDK version 0.8.3 is qualified against console 0.8.2.

```sh
npm install @polymathbase/polybase-client@0.8.3
cargo add polybase-client@0.8.3
```

Read the [TypeScript](typescript/README.md) and [Rust](rust/README.md) guides.
The local database binaries have their own [evaluation terms](../LICENSE);
the [Rust](rust/LICENSE) and [TypeScript](typescript/LICENSE) source licenses
apply only to these client directories.

The `clients-v0.8.3` tag identifies the registry package source. Cargo's
`.cargo_vcs_info.json` records that public revision; the npm package's repository
directory and pinned TypeScript build can be compared to the same tag.
Only explicitly selected SDK source files are mirrored here;
the engine, server implementation, database directories and user data are absent.

For source checks, use Rust 1.89+, Node 24+ and a downloaded `polybase-console`:

```sh
cargo test --manifest-path clients/Cargo.toml --locked
npm --prefix clients/typescript ci --ignore-scripts
npm --prefix clients/typescript run check
POLYBASE_CONSOLE_BIN=/absolute/path/to/polybase-console npm --prefix clients/typescript test
```

The SDKs do not automatically retry writes. A timed-out write can still commit;
reconcile application state before another write. Persist applied subscription
rows and their token atomically before requesting the next page.
