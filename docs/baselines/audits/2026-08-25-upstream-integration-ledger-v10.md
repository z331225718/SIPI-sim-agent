# Upstream integration ledger v10 audit

Schema: `sipi.upstream-integration-ledger.v10`; additive successor to the
immutable v9 ledger. Candidate `f628d7f0660667fe6a79b7a39ea5a3e3b4500a4e`,
tree `5d3cd3e04cb495fab85b247130b8f0b236b6e6a9`, and the exact
`git -c core.autocrlf=true archive --format=tar` SHA256
`754d7c38a136d82fa52c822b3b0090d505ffc97a23259256265bf338101126a8`
(`51988480` bytes) are bound. The v9 predecessor SHA256 is
`de63edd031cf7850817d33085afa8b5729f65f1e9f65a5ce9545a8c0f7b2da35`.

This is governance closeout, not a feature or release promotion. All 15 rows
remain open or scoped, with `release-ready=0` and no global parity claim.
AS-01 and AS-02 are owner-excluded under the no-S-parameter-fit policy, not
completed Rust implementations. AS-03 is retained as an external Y-domain
reference-only workflow; its fixed observation does not promote a product
capability. SI S-parameter fitting remains excluded and the channel policy
remains impulse-only.

AS-05 has a direct Rust portable staging branch, but the external solver is
retained. Its staging contract is limited to trusted, non-concurrent source
and output roots; the attested ngspice observation is not solver correctness,
numeric parity, or row closure. AS-06 now records the attested external
ngspice RFM execution boundary from the v2 source map and NOTICE; the
external solver remains a retained boundary and no numeric parity is claimed.

PB-02's native three-scenario diagnostic (NRZ bypass, PAM4 bypass, and
DuoBinary explicit DFE) matched complete arrays and metrics exactly, but the
pinned upstream CLI still emits a flat envelope without nested `output`.
The diagnostic report was in Temp and is deliberately not formal evidence;
this ledger therefore makes no global parity or release claim. PB-04 and
PB-05 remain retained external-asset branches.

COM-02 binds the current COM source map/NOTICE and records the f628 manual/local
two-case observation. Both workbook port-order and opaque-winner fields are
`unbound_manual_two_case_observation`; this is not formal evidence and is not supported by v4.
The v4 evidence remains historical scoped evidence only and does not bind the
winner. S-parameter fitting is forbidden, the channel is impulse-only, and
global parity, full entrypoint parity, and release remain open.

The source maps, notices, change commits `01323d9c`, `d55cce1b`, `6f52e53f`,
`85955389`, `f50dc6b0`, and `f628d7f0`, predecessor, candidate archive, PLAN,
audit, verifier, and mutation suite are all physically hash-bound by the v10
verifier. No v9 file is rewritten and no Temp report is admitted as formal
ledger evidence.
