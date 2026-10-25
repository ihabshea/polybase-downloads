# Availability correction — 25 October 2026

Immutable Atlas source snapshots and evidence may say the current downloadable
database is 0.9.0. That copy came from a stale branch. Polybase **1.0.0 was already
published** at 11:45:19 UTC, with website version 17 deployed at 11:48:09 UTC.
There is no downloadable Atlas 1.5 engine release.

This corrects availability text only. No observed engine version, pinned baseline,
source SHA, executable hash, sample, failed target or raw evidence is rewritten.
The measured baseline remains `54c92946abbaea30bae25e2e8178676e17cbd9e8`. Packaged
source `826f0bc0329e8c2e25333b60a8b9adf6d60c27d9` has identical engine/client/Cerberus
campaign inputs. Reports at `333c2f0` and `b2c865f` remain attributed to those source SHAs.

Publication references:

- [Actual 1.0 release](https://github.com/ihabshea/polybase-downloads/releases/tag/v1.0.0).
- Private publication main: `a6407d670d9f59220b3e2527b35c8870727306ac`.
- Public publication main: `e674c08902f475926395a7967bcf9e023b4a57ba`.
- [1.0 publication records](../1.0.0/publication/).

The later Atlas integration preserves the published 1.0 downloads and records
implementation-input equivalence separately; its whole-tree source hash changes
when presentation and packaging documentation are integrated.
