# PB-03 Legacy Branch Coverage Audit

This additive successor is bound to candidate commit `d3154093fd58aeaa596444825dc17be6cb7e35c0` and tree `2d51e84554558bb4947c0152259af9bf7f927efe`. The pinned upstream is commit `5bf6d7ea0ace261891aaeb611ffc1c267e160afe`, tree `5faef6bdb341d444ad65d82a11c0018b15805e24`.

The source inventory is content-addressed to the immutable candidate commit. Focused Rust tests exercised the portable legacy projection branches for bounded configuration state, NRZ/PAM4/Duo modulation, supported PRBS fields, analytic RLGC, S2P/S1P/S4P parsing, differential renumbering, reference `R`, two-column step/impulse responses, CTLE input, TX/RX FFE/DFE/CDR, deterministic/random noise, Viterbi ISI/FEC, jitter/eye/BER, and relative threshold projection. The AMI/IBIS/ts4/getwave boundary is explicitly fail-closed.

The matrix records `portable_missing: []` for this tested pure-data branch probe. It does not claim a Python payload oracle: `oracle: not_run`, `oracle_payload_parity: false`, and `global_row_closed: false`. Independent Python result parity, exact class pickle restoration, and host-owned model execution remain open. No promotion is authorized.

Verification command: `cargo test --manifest-path crates/sipi-pybert-direct/Cargo.toml --locked`.
