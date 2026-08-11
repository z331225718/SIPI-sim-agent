# P3B Receiver Diagnostic CLI Slice

`sipi link receiver run --stdin` is a product-owned diagnostic route for the
already specified fixed receiver semantics. It accepts exactly 1024 finite
single-ended voltage samples at 1 ps and 128 explicit caller-supplied reference
bits for the sole `channel-rfm-block-2-current-drive-v1` profile selector.
CTLE and FFE remain explicit bypass only.

The route calls only the clean-room delegated-ambiguity receiver implementation.
It publishes a sealed summary artifact with hashes, phase selection, calibration,
tap, and BER summaries. It deliberately does not retain or return the waveform,
reference bits, or raw decisions. Every result states
`product_owned_diagnostic`, `policy_selected_not_locked`, `external_rfm=false`,
and `acceptance=false`.

Invalid shape, timebase, reference bits, profile, receiver failure, cancellation,
resource failure, or publication failure produces no success artifact. There is
no RFM/PyBERT input, path, URL, external process, automatic alignment, implicit
bit generation, clock-lock claim, or fallback phase.

This is not external RFM receiver parity, a physical clock-recovery result, a
required-profile acceptance, a causal-FIR Link stage, eye/jitter/BER accuracy,
or release readiness.
