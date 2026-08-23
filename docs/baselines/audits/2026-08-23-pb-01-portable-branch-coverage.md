# PB-01 portable branch coverage audit

The active PB-01 preparation slice now covers the pure-data legacy path in
`crates/sipi-pybert-direct/src/legacy_runtime.rs`. YAML `PyBertCfg` mappings and
bounded `.pybert_cfg` state mappings are projected into the same typed request
used by the PB-02 native core. The decoder uses `serde-pickle` only as a
data parser: it requires the PyBertCfg marker, bounds input to 1 MiB and 64
levels/100,000 values, rejects byte-string mappings and non-string keys, and
never restores Python globals or starts a Python runtime.

The branch matrix covers NRZ, PAM-4, Duo-binary, the supported PRBS order set,
analytic RLGC, Touchstone S1P/S2P/S4P channel and CTLE responses, TX/RX FFE,
DFE/CDR, periodic noise, NumPy PCG64 double-ziggurat random noise with an
effective non-zero seed, Viterbi ISI/FEC, jitter, eye, bathtub, BER, bounded
pickle root identity, and the full Rust result-adapter payload. PB-04 preserves the
pinned `sim-auto` selection payload (`requested: auto`, `selected: python`,
blocked parity gate) while admitted portable input executes an independent Rust
reference graph and records the actual `selected: rust_portable_reference`.
PB-05 uses that independent graph for no-reference comparisons and compares
arrays, metrics, metadata, diagnostics, and candidate-failure reference
retention rather than status alone.

The matrix leaves external AMI/IBIS/TS4/GetWave models, exact Python
`PyBertData` class restoration, and independent Python parity open. No row is
promoted and no license decision is made by this artifact.
