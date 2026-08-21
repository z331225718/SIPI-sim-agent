# P2-06 exact RC measurement implementation

The product now has one bounded text consumer for an exact seven-line deck:
title, `V1 in 0 PULSE(...)`, `R1 in out`, `C1 out 0`, `.tran`, one
`.measure TRAN <name> MAX V(out)`, and `.end`, in that order.

The parser fixes element names and nodes, accepts only finite ASCII SI values,
requires an integral `.tran` stop/step ratio, and enforces caller-owned byte,
line, output-sample, and integration-breakpoint budgets. It rejects `.op`,
`.ac`, extra devices, duplicate commands, measurement windows, and alternate
measurement operations. The parsed request delegates to the existing bounded
one-node RC/PULSE solver. `MAX` is reduced only over the finite samples actually
emitted by that run.

The exact consumer was replayed twice alongside a clean release build of pinned
Agent-Spice `2cc92316`. The oracle ran its original `rc.cir`, while the product
ran the new strict seven-line deck, so this is not a same-input parser compare.
Time and input arrays matched exactly. The maximum absolute error for `V(out)`
and for the product comparator's local `max(oracle V(out))` comparison was
`9.963737488231927e-7 V`, within the fixed `2e-6 + 5e-4 * scale` tolerance.
The report remains external-only and is hash-bound by the current evidence.

Agent-Spice measurement output was not observed, so this does not establish
measurement parity and does not close P2-06. It records a completed bounded
product prerequisite plus a waveform observation only. It does not admit
generalized SPICE, OP/AC, or general measurements. The implementation
and compare records are
`docs/baselines/p2-06-exact-rc-measurement-implementation.v1.yaml` and
`docs/baselines/p2-06-exact-rc-measurement-current-external-compare.v1.yaml`.

Verification:

```text
cargo test -p sipi-tran --lib
cargo clippy -p sipi-tran --lib -- -D warnings
python -B tools/verify_p2_06_exact_rc_measurement_implementation.py
python -B -m unittest tools.test_verify_p2_06_exact_rc_measurement_implementation -v
```
