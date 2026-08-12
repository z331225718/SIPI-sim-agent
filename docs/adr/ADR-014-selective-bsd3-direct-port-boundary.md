# ADR-014: Selective BSD-3-Clause Direct-Port Boundary

- Status: Accepted
- Date: 2026-08-12
- Decision maker: project owner
- Scope: source provenance, licensing, clean-room material admission, and future
  S-parameter implementation work

## Context

ADR-011 keeps SIPI-sim-agent first-party product code under MIT and excludes
source whose redistribution rights have not been established. That remains the
default. It does not prohibit a compatible, explicitly licensed third-party
source from entering through an auditable per-file route.

The owner authorized a path-by-path audit for the Agent-COM S-parameter helper
ports and, after admission, a mixed-license direct-port mode. The linked
Agent-COM functions declare an R4.80 lineage. A repository-level MIT license
is not enough to relicense a derived upstream implementation, so this decision
uses the official 802-COM source repository and its per-file BSD-3-Clause
headers as the only currently observed upstream license evidence. IEEE standards
and meeting material are not treated as a code license.

## Decision

1. SIPI-sim-agent first-party code continues to be MIT. A third-party direct
   translation retains its upstream license, copyright notice, and required
   attribution. The root MIT license never rewrites that source-specific
   license.
2. `bsd3_source` is an implementation-eligible clean-room material kind only
   when a scope lists its immutable upstream object, content hash, BSD-3-Clause
   evidence, and the exact source paths being translated.
3. The initial 802-COM admission is selective. Only `interp_Sparam.m` and
   `s21_to_impulse_DC.m` at the recorded GitLab commit are eligible source
   inputs. They are not product API, algorithm-policy, release, or parity
   admissions.
4. `calculate_delay_CausalityEnforcement.m` remains blocked for direct port:
   its named-author chain requires an independent confirmation or an equally
   verifiable project record. Its BSD header alone is not promoted here.
5. Before any Rust translation is added, a new implementation scope must bind
   the exact Rust files to the admitted source objects, choose all product
   S-parameter semantics independently, add source-specific SPDX/NOTICE/SBOM
   entries, and pass a release-boundary audit. A resulting file may be
   `BSD-3-Clause`; `BSD-3-Clause AND MIT` is allowed only when its source map
   proves an additional MIT-derived contribution. `MIT` alone is forbidden for
   a direct translation of the admitted BSD source.
6. PyBERT, PyAMI, MATLAB workbooks, oracle outputs, and unadmitted Agent-COM
   paths remain outside this decision and retain their existing boundaries.

## Consequences

- Future direct ports can use a small, reproducible compatibility route without
  claiming that all historical COM code was relicensed.
- The first two 802-COM source objects can inform an implementation only after
  a dedicated scope is created; this ADR intentionally adds no Rust algorithm,
  no S-parameter policy, and no candidate execution.
- NOTICE/SBOM/archive gates stay fail-closed. P5 authoritative-reference,
  source-drift, ADS/AMI, receiver acceptance, and release gates do not move.

## Non-claims

- This is a provenance and project-policy decision, not a legal opinion.
- It does not assert that Agent-COM and 802-COM implementations are
  semantically identical or that IEEE standards license source code.
- It does not authorize a general MATLAB, COM, PyBERT, PyAMI, or Agent-COM
  import, nor does it make a product release mixed-license ready.
