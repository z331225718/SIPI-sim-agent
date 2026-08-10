# P3B RFM Receiver Handoff Replay v1

This oracle-only gate proves that one approved external RFM execution can
provide a bounded voltage waveform and the separately attested reference-bit
sidecar to the product-owned fixed receiver boundary. It does not make the
external RFM, Python, engine, ports, current drive, or receiver configuration
part of the product API.

The observer runs only from a clean, immutable external source checkout and
materializes the pinned RFM Git object into a disposable directory. It invokes
the pinned external engine for a 1024-point, 1 ps, port-1-to-port-2,
current-sign-minus-one request. The observer may use its own existing
current-domain voltage conversion, but it must not import or compare a
retained receiver.

The observer emits only two ephemeral sidecars: exactly 1024 finite little
endian f64 receive-voltage samples and exactly 128 bytes with values zero or
one. Before product consumption, the gate validates their byte counts, hashes,
timebase, units, port/sign declaration, source anchors, and a second fresh
replay with identical waveform and bit hashes. No resampling, windowing, FFT,
padding, trimming, sign or unit conversion, thresholding, or bit inference is
permitted at this handoff.

The product side is an ignored Rust test target, not a CLI, FFI, artifact, or
default route. It decodes the sidecars only after containment and shape checks
and constructs `ReceiverInputV1` and `ReferenceBitsV1`. Receiver execution is
a later, separate charter-equivalence stage, so this handoff does not use a
receiver result to decide success.

A successful report is named
`handoff_accepted_pending_receiver_execution_and_charter_equivalence`.
It establishes only external RFM receive-waveform to product receiver-input
replay. It is not a comparison with a retained receiver, a charter-equivalence
result, general RFM/Link/DFE/CDR/BER parity, or an enabled product route.
