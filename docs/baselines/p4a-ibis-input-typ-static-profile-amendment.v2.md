# P4A Input/TYP Static Profile Amendment V2

The v1 selected-model digest identified an Input model without the required
POWER clamp section. That violates the frozen two-branch observable, so the
v1 selection cannot be compared or accepted.

Under the user's standing instruction to decide profile details autonomously,
the required profile is amended to another uniquely digest-selected Input
model in the same pinned external-only asset. The new selector digest is
`0be75aff11736ab3fee529275984551c241433d189ba1a21bad1b0e0e70fd2ff`.
It has exactly one ground and one power clamp section in the observer's
declared structural scope.

All remaining contract fields stay unchanged: the six static voltage probes,
Typical-only current column, signed ground-plus-power shunt current,
zero DC `C_comp`, interpolation, tolerance, external-only custody, and every
non-claim. This amendment does not expose or record the selector spelling,
tables, or any external asset bytes.
