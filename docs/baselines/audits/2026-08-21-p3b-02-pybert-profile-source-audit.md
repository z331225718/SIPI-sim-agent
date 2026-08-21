# P3B-02 pinned PyBERT profile source audit

The pinned PyBERT tree was inspected through Git objects only. The repository
license is BSD-3-Clause, but source permission is not profile authority.

The source does not define one mechanically selectable fixed receiver profile.
The legacy desktop defaults use a 12 GHz bandwidth, 5 GHz peak and 1.7 dB CTLE,
while the Web request model and adapter use 4.0 dB. The legacy receiver declares
15 FFE taps but materializes 20 tuners with a cursor at index 5; the Web adapter
also materializes a delayed 20-weight unity FFE, while the native Rust default
has an enabled CTLE with no configuration (and therefore fails) plus a disabled,
empty FFE.

The CTLE construction boundary is also not interchangeable: the legacy path
uses `make_ctle`, IRFFT, interpolation, sum normalization and trimming on its
frequency grid. A numeric parameter tuple alone does not freeze that time-domain
state, delay, length, or normalization contract.

Therefore P3B-02 remains open. No profile was chosen by comparison closeness, no
product code or wire schema was changed, and the existing named causal-FIR chain
remains only a bounded prerequisite.
