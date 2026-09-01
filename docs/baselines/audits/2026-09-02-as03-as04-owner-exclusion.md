# AS-03/AS-04 owner exclusion audit

## Decision

The owner decision is to skip the legacy Agent-Spice `fit-yparam` and
`tune-yparam-tran` workflows. They are recorded as `excluded_by_owner` and
`historical_quarantine_not_product_reachable`. The decision does not claim
numeric parity, acceptance, product capability, or release readiness.

| row | upstream entrypoint | current disposition | product reachable | parity/release claim |
| --- | --- | --- | --- | --- |
| AS-03 | `fit-yparam` | `excluded_by_owner` | no | none |
| AS-04 | `tune-yparam-tran` | `excluded_by_owner` | no | none |

The excluded routes remain fail-closed. No Rust, CLI, product-boundary,
license, or numerical-policy change is authorized by this record. The existing
S-parameter-fit prohibition and one-final-FD-to-TD-impulse channel policy stay
in force.

## Immutable history

The v14 integration ledger and v1 migration inventory are predecessors, not
files to rewrite. The historical AS-03 power-wave replay and AS-04 direct-port
evidence remain preserved as immutable historical-only evidence. Their previous
numeric observations, custody records, and limitations are not promoted or
deleted by this disposition.

The additive successors are:

- `docs/baselines/upstream-integration-ledger.v15.yaml`
- `docs/baselines/upstream-migration-inventory.v2.yaml`
- `docs/baselines/as03-as04-owner-exclusion.v1.yaml`

The successors change only the current owner disposition of AS-03 and AS-04.
AS-01, AS-02, AS-05, and AS-06 are unchanged. In particular, the existing
AS-05 Xyce/XDM exclusion and AS-06 scoped external observation are not altered.

## Candidate binding

The successor governance documents are bound to the clean CLI-tombstone
candidate `ad797d8c6421c51b9607a2624cf4572c9c8b0b50`, with tree
`d305cbfd27960926c969db9abbaeac81d8b1e988`. Its `git archive --format=tar`
snapshot (with `core.autocrlf=true`) is 62,822,400 bytes and has SHA-256
`149c1162f8ba697a7d9509cb0950afff3fdad8c5977af051c6bd279b29cd1b30`.
This is custody metadata for the owner disposition only; it is not a parity,
product-capability, or release claim, and it does not make either excluded
workflow reachable.

## Verification boundary

The dedicated verifier checks strict YAML shape, duplicate-key and non-finite
value rejection, predecessor byte hashes, exact successor row changes, exact
untouched-row preservation, historical evidence bindings, and the no-parity,
no-acceptance, no-product-capability, and no-release invariants. Its mutation
tests cover owner promotion, reachability reversal, historical evidence drift,
predecessor drift, unrelated-row drift, policy drift, duplicate keys, and
non-finite YAML values.

This is a governance disposition only. It is not a fresh upstream replay, a
Rust implementation, a solver result, or a release approval.
