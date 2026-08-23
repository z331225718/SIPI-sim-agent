# COM ERL v4 preparation audit

This additive preparation is intentionally not formal evidence. It reuses the
v3 clean-archive support and Windows PE custody helper, and freezes the exact
candidate/upstream archives, 8001-row fixture identity, UTF-8/offline `uv`
command, external caller-supplied cache policy, and release build/runtime
timeouts.

The positive replay is `N=800` with `observation_duration_ui=800`; workbook
`TDR_duration` is recorded only as a raw source field and is never used as the
runtime control. The negative guard is upstream-only `N=1`: the candidate is
not executed, is marked `excluded_from_parity`, and must produce no candidate
metrics or stage payload.

The aggregator requires two ordered, independent positive runs plus the
upstream-only negative guard. A positive stage SHA mismatch is reported as
`numeric_mismatch_open`; it cannot be converted to a matched claim. Raw PTDR
is diagnostic-only because the pinned public upstream diagnostic does not
expose it. S-parameter fitting remains forbidden; channel input is raw S11
FD-to-TD impulse.

The preflight gate freezes positive ptdr_gated/gated count 2310 with upstream
SHA a3e274d035c5cdf11af5e43852341a92a315bb8e9c7552b25b74764721f1879a and
candidate SHA 6b4ca9b5ad5909791917e2eb8bd4079aaaf591b61f8c02af081a9e4f46ed2143.
The N=1 upstream-only guard freezes count 15 and SHA
9bb66210cade8684e08cfdb260a23763c35dc157dd68a8d6e0edda32716e1463.

Stage names use the upstream diagnostic contract exactly: tdr_time_s,
tdr_impedance_ohm, and ptdr_gated. The N=1 guard does not build or run the
candidate; candidate build/timeout fields are null rather than fabricated.

The upstream lock binding is the raw Git-object bytes from pinned commit
5272ffe74702cd585054d975559b06f8afae7b6e: blob b0d367...,
79106 bytes, SHA
5495d481034518d4424a55a27aa2319c90d2045bc280705748d66f44e159a00f.
The previously recorded 7711... value was a non-canonical working-tree/
newline digest and is not admitted.
