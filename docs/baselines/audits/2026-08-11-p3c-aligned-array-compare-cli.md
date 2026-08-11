# P3C-03a Aligned Array Compare CLI

`sipi compare run --stdin` exposes only the product-owned,
`sipi.compare.aligned-arrays-request.v1` contract. A request carries two
already aligned finite arrays, their exact shape, canonical unit,
semantic-binding SHA-256, and explicit absolute and relative tolerances.
The route calls the single `sipi-compare` directional
reference-to-candidate comparator.

Shape, unit, binding, non-finite values, invalid tolerances, unknown fields,
and fixed request/element limits are rejected before comparison. A numeric
mismatch is instead a successful bounded response with `passed=false` and
aggregate error metadata. Responses never echo input arrays and the route
does not read files or URLs, create artifacts, call an oracle, align axes,
convert units, or select a profile.

## Review

One Orca OpenCode reviewer audited the staged slice, identified a command-shape
inconsistency for `sipi compare run` without `--stdin`, and verified the
fail-closed fix. The final review reported no P1, P2, or P3 findings. The
unrelated user-owned `uv.lock` change remained outside this slice.

## Non-Claims

This is a caller-supplied aligned-array capability only. It does not define
channel-to-compare binding, eye, jitter, bathtub, BER, external profile
comparison, or an oracle workflow.
