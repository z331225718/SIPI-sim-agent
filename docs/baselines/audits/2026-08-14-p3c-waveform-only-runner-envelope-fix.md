# P3C-04ae Waveform-Only Runner Envelope Fix Audit

- Reviewer: reused Orca OpenCode reviewer
  `term_095ff00a-2548-477e-8dba-ea6e6f010974`.
- Scope: external v3 runner's CLI success-envelope decoding.
- Result: **0 P1 / 0 P2 findings**.

An external smoke run proved that the runner had parsed the CLI's outer
response envelope as the domain result. The fix first validates the immutable
`sipi.cli.response.v1` envelope (`protocol=1`, `command=compare`, `status=ok`,
and zero diagnostics), then reads its `result` object. All v3 contract,
artifact-binding, third-period, eye/TIE-exclusion, and waveform-limit checks
remain fail-closed. The correction neither changes metric semantics nor
promotes any external or release gate.
