# P3B Receiver Charter Evaluator v1

This is an oracle-only, independent evaluator of the owner-approved fixed
receiver charter. It consumes exactly the external ephemeral f64le waveform
and direct 0/1 reference-bit sidecars already admitted by the RFM handoff
gate. It must not import SIPI Rust code, PyBERT, NumPy, a retained receiver, an
old Rust receiver, RFM data, or an external engine.

The evaluator independently applies all approved semantics: eight fixed phase
candidates, 32 data-aided training symbols, signed class means, a unique one
percent phase margin, five postcursor LMS taps with step 0.25, known-symbol
warm start, frozen decision feedback, zero-decision erasure/error with zero
feedback, and a fixed 96-symbol BER denominator. It produces only an external
temporary result record.

Any future comparison first requires exact input provenance equality. Phase,
lock, decision/erasure sequence, error count, and BER numerator/denominator
compare exactly; center, amplitude, and taps use the approved `1e-9 V + 1e-6
relative` continuous tolerance. A rejection on either side is evidence of a
blocked input under that implementation, not an equivalence pass. This is an
acceptance oracle, never a second product receiver or product route.
