# P3C Selected High-Loss Waveform-Only Historical Source Drift v1

This reconciliation preserves the 04ag external waveform-only observation as
historical evidence when its verifier rejects the current product archive with
the exact `waveform_only_product_source_drift` token. It does not rewrite the
historical observation, reinterpret its result, or provide a current external
reference binding.

The reconciliation is fail-closed: no current waveform NRMSE evaluation,
profile acceptance, receiver, release, or promotion gate may be set true. A
fresh, separately custody-bound observation is required before any current
external claim may be restored. It records neither payloads, waveforms,
external paths, nor reports.
