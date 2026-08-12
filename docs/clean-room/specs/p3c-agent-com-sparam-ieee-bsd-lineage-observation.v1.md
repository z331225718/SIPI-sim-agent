# P3C Agent-COM / IEEE 802-COM BSD Lineage Observation v1

## Purpose

This is an additive provenance observation for the three Agent-COM
S-parameter candidate paths recorded by the v1 authorization preflight. It
binds a separate, immutable IEEE 802-COM GitLab source commit and the
per-file BSD-3-Clause headers observed there. It does not amend or reinterpret
the v1 historical record.

## Admitted Inputs

Only these two upstream objects are source-input eligible for a later,
separately declared implementation scope:

- `src/interp_Sparam.m`
- `src/s21_to_impulse_DC.m`

Their source identities, full BSD-3-Clause header markers, project root
license, and the Agent-COM markers that name the corresponding R4.80 functions
must all match this record. The implementation scope must preserve the BSD
notice, bind its resulting Rust paths, and choose product semantics separately.

`src/calculate_delay_CausalityEnforcement.m` remains observer/spec/audit-only.
Its named-author chain is not sufficiently established by this record, so it
cannot be placed in an implementer allowlist.

## Exclusions

This observation does not read or run MATLAB, Agent-COM, PyBERT, PyAMI, ADS,
workbooks, fixtures, or oracle outputs. It does not compare algorithms or
outputs, select interpolation/DC/out-of-band/IFFT/delay/causality/passivity
policy, create a Rust implementation, or authorize a product/release input.

## Fail-Closed Rules

The verifier requires the exact Agent-COM and IEEE Git object identities,
source bytes, headers, SPDX spelling, BSD root license, and candidate statuses.
It rejects an MIT-only translation claim, deletion of the named-author blocker,
any global direct-port promotion, extra source input, or any release/P5/product
policy promotion. A changed source is a new observation, not a reason to
rewrite historical evidence.
