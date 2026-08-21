# P3B-02 explicit RX CTLE -> RX FFE semantics and PyBERT observation

## Result

The product-side semantics gap is closed for a caller-supplied, in-memory
profile. `sipi-link` now exposes an explicit RX CTLE -> RX FFE composition in
`crates/sipi-link/src/rx_ctle_ffe_v1.rs`. The API requires the CTLE transfer
representation, uniform grid and origin, normalization reference, and initial
state. The FFE requires tap order, cursor index and output-origin convention,
coefficient units, sign, sample/UI domain, and initial state. Each slot is an
explicit `Bypass` or `Explicit` value; there is no `Default`, auto-tuning, or
silent fallback.

Both enabled stages are materialized as causal FIRs and delegated to the
existing bounded full-linear convolution through
`apply_rx_named_fir_prerequisite_v1`. Output and multiply-accumulate limits are
checked before execution. A cursor-at-origin FFE retains precursor samples on
an explicit negative output axis rather than dropping or silently shifting
them.

The v1 wire contract remains bypass-only. This slice is an additive in-memory
caller/profile surface, not a selected product profile, CLI route, artifact
route, external parity result, or release capability.

## Pinned source observation

`tools/observe_p3b_02_pybert_semantics.py` reads only Git objects from the
external PyBERT repository at commit
`5bf6d7ea0ace261891aaeb611ffc1c267e160afe` and records exact blob identities
plus semantic marker observations. It stores no source bytes. The observation
confirms the legacy CTLE construction sequence (`make_ctle` -> `irfft` ->
interpolation -> sum normalization -> trim), the post-CTLE sample-spaced FFE
convolution, and native typed CTLE/FFE controls. It also confirms conflicting
legacy 1.7 dB versus Web 4.0 dB CTLE defaults and an RX cursor at 5.

Those pinned objects provide source semantics, not a mechanically unique
selected profile. `profile_status.required` therefore remains
`external_asset_oracle`; no profile was chosen by oracle closeness.

## Verification

```text
python -B tools/observe_p3b_02_pybert_semantics.py --pybert-root C:\Users\z3312\code\Py-bert-agent --report docs/baselines/p3b-02-pybert-source-semantic-observation.v1.yaml
python -B tools/verify_p3b_02_pybert_semantics.py --pybert-root C:\Users\z3312\code\Py-bert-agent
python -B -m unittest tools.test_verify_p3b_02_pybert_semantics -v
C:\Users\z3312\.cargo\bin\cargo.exe test -p sipi-link --lib
```

The verifier rejects product API hash drift, missing typed semantic markers,
wire non-bypass variants, external commit/tree/blob drift, source marker drift,
and any selected profile or oracle-closeness claim.
