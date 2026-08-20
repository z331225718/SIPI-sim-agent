# PLAN Open-Items Gate Coverage (Complete Inventory)

PLAN.md contains 74 checkbox items, of which 65 are checked and 49 are
open. This audit records the mechanical coverage gate that maps EVERY
open item to a state-keeping verifier (or its dependency class), so an
open item can never silently regress to an unguarded condition while it
waits for its owner decision or external oracle.

## Coverage Correction

Earlier coverage audits were computed from a truncated PLAN read (277 of
655 lines) and covered only 9 open items (P1-04B through P3C-01). The
complete file has 49 open items spanning P3C-02/03, P4A-01..06, P4B-01..09,
P5-02..09, P6-02..10, and P7-01..09. This revision extends the gate to the
full 49-item inventory; all previously delivered per-area gates remain
unchanged and in force.

## Delivered Gate

- `tools/verify_plan_open_items_gate_coverage.py` — verifier for schema
  `sipi.plan-open-items.gate-coverage.v1`. It maps all 49 open items to
  66 gate references and fails closed if any referenced gate file is
  missing from disk. Representative mappings:
  - P3C-02/03, P5-03/06/08/09, P6-02..10, P7-05:
    `verify_release_capability_publication.py` (publication row keeps the
    state honest);
  - P4A-01..06: the four P4A preflight/conformance verifiers;
  - P4B-01..04/07..09: the P4B preflight and PE-declaration verifiers;
  - P5-02/04/05/07: `verify_p5_agent_com_git_object_preflight.py`;
  - P7-01..04: twin-build/composition/archive/install verifiers;
  - P7-06: `verify_p7_evidence_anchor_v2.py`; P7-07: license-material
    observation v2; P7-09: `verify_external_history_citations.py`.
- `tools/test_verify_plan_open_items_gate_coverage.py` — 4 tests updated
  to the 49-item/51-gate inventory.

## Verification

`python -B tools/verify_plan_open_items_gate_coverage.py` returned
`{"gates": 66, "items": 49, "schema": "sipi.plan-open-items.gate-coverage.v1", "valid": true}`.
`python -B -m unittest tools.test_verify_plan_open_items_gate_coverage` passed 4/4.
Spot checks: P4A-02 and P4B-01 verifiers run clean (preflight passed);
P4A-01 and P5 require external roots and fail closed with the missing
argument, which is itself the state-keeping behavior.

## Artifact Hashes (SHA-256)

- verifier: `CBC2E96BF16AF41AB2A2C9C962D1AFC4F44DB0C6950C6F8668D562FBB4BEB818`
- tests: `24EA447DF5E2CF231A563828775DB87B5363742F05878D46EB7C739CE478ADA1`

## Scope and Non-Claims

- This gate records coverage of state-keeping verifiers only; it does not
  complete any open item, accept any profile, or substitute for owner
  decisions or external oracles (IBIS/AMI/DLL assets, MATLAB/ADS oracle,
  fresh-machine/license/NOTICE gates, CDR amendment, metric semantics).
- The gate does not certify TRAN, link, channel, IBIS, AMI, COM, metric,
  or release readiness.