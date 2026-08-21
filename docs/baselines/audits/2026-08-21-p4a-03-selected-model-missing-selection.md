# P4A-03 Selected Model Missing-Selection Audit

Owner decision D4=A authorizes only grammar needed by an explicitly selected
IBIS model. It does not itself select a signal role, model selector branch,
model, corner/PVT, or table family.

The exact complete external object is not mechanically unique. Its 200 pins
reference four selectors (`CA_PIN`, `CLK_PIN`, `CS_PIN`, and `DQ_PIN`) plus the
direct `CKE_PIN` model. The selector branch cardinalities are 9, 9, 9, and 67.
Together with `CKE_PIN`, those references cover all 95 declared models: 37
Input and 58 I/O models. The Input and I/O declarations expose different
keyword/table families, and no pinned owner record selects a corner/PVT.

Choosing `CKE_PIN`, the first branch, a typical column, or a clamp/waveform
family would therefore be a policy guess, not a mechanical consequence of the
asset or owner record. No selected-model grammar or electrical consumer is
added in this stage. The existing complete-document declaration/linkage
consumer remains valid, while selected-model implementation stays blocked on
explicit signal/model/branch/corner/PVT/table-family selection.
