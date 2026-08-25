# Upstream integration ledger v9 audit

Schema: `sipi.upstream-integration-ledger.v9`; this is the v8 immutable predecessor
successor. AS-04, PB-01, and COM remain governed by their existing blockers,
PB-01/PB-02/PB-03 remain scoped observations without branch/global parity or release;
PB-02 is a fixed-fixture payload observation and PB-03 is fixed-subset payload parity.
COM retains `no_public_accm_e2e`. No promotion is made.

This additive successor binds current clean candidate `a8a97139686088b3340e5a8ff4dc47af0829b5ec`, tree `be7b2b25c8cbd705b3c0eb4778b5097762653296`, and the exact
`git -c core.autocrlf=true archive --format=tar` archive SHA256 `95b7374b1c45538f8b0836c6ec4a576d330d9e43dcd1188e53c963d799df098d` (51722240 bytes). The v8 predecessor remains immutable and is bound by physical SHA256 `ce292d1eea19d38628b3e63360d9e269d080ab8533a63b9a46a092f9f8eed69d`.

AS-03 current observation is the two-fresh formal gate from commit `5a6608e0`; the residual approximately 1e-17 numeric mismatch remains open. PB-03 is the two-fresh scoped formal observation from `c93746e9`; its claim is limited to fixed-subset payload parity, with no whole-payload parity or independent-implementation claim, and does not close the row. COM workbook-to-ACCM formal evidence is from `a8a97139`, manifest `docs/baselines/com-workbook-accm-replay-v4.manifest.yaml` SHA `68e4fdc5c9d644d146b541eadd1753b5ff2a886576024a2f9f5f522e6aa95467`. Its status is numeric_observation with matched=false and acceptance=false; both reports and the aggregate are bound in the ledger. The COM formal gate passed its strict verifier and fixed-cargo aggregate verifier; it is not an upstream parity or release claim.

All 15 rows remain open and release-ready=0. Existing v8 blockers and conservative non-claims are inherited: no SI S-parameter fit, channel impulse-only, no global/product parity, no release/promotion, and COM PDB is local/nonpublish. No partial slice closes a row. No promotion is made.

Gate results are mechanically bound as follows: AS-03 current verifier and its mutation suite pass; PB-03 current verifier and its aggregate/mutation gate pass; COM workbook/ACCM strict verifier and fixed-cargo aggregate verifier pass, with 60 preparation tests passing. These are evidence-gate results only, not parity acceptance. The COM reports remain numeric_observation with matched=false and acceptance=false.
