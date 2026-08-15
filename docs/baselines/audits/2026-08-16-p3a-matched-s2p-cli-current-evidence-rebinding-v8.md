# P3A Matched S2P CLI Current Evidence Rebinding V8

Date: 2026-08-16

## Scope

P4A sealed IBIS quasi-static batch support changed the `sipi-cli` and
`sipi-contracts` product inputs. The earlier P3A v7 record is consequently a
historical source-drift record and cannot attest the new executable.

## Observation

The unchanged external-only `channel_16ghz_3db.s2p` Git object was materialized
twice in fresh temporary custody. A clean archive of candidate
`c7aebc79576b074729352a9e8c9af0aee95f0894` was built locked and offline, and
the bounded `sipi channel run` comparison passed both frozen absolute and
relative error gates. The external report remains outside the repository; the
v8 evidence record binds only its SHA-256 and aggregate facts.

## Boundary

This rebind restores only selected matched-S21 periodic-kernel observed
evidence. Ordinary caller input remains unattested. It does not establish
general Touchstone behavior, reflection or termination, Link/eye/BER,
artifacts, external oracle behavior, or release readiness.
