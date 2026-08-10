# P3B Independent Receiver Charter Evaluator

Commit `9317478` adds an external-only, stdlib-only evaluator for the approved
fixed receiver charter. It reads only temporary canonical waveform and
reference-bit sidecars plus their request manifest; it does not import SIPI,
PyBERT, NumPy, a retained receiver, or an old Rust receiver.

The evaluator independently implements the charter's eight candidate phases,
32-UI data-aided training, signed class normalization, 1 percent phase margin,
five postcursor LMS taps with step `0.25`, 96-UI measurement window, and the
approved erasure rule: count an error, feed back `0.0`, and continue. Its
product-owned tests cover phase selection, ambiguity, LMS, erasure feedback,
and invalid sidecars.

The ignored `receiver_observer_runner` test target now records either the
product receiver's complete temporary result or its explicit rejection. It
remains a test-only target rather than a CLI, FFI, artifact route, or external
engine dependency.

Orca read-only audit `msg_cd04c0bb5309` found `0 P1 / 0 P2`. The audit checked
the evaluator's oracle-only clean-room registration, independent algorithm,
fixed charter constants, rejection behavior, and the absence of a product
route or legacy runtime dependency.

This accepts evaluator readiness only. It does not yet compare the evaluator
and product receiver on the two external RFM replays, establish receiver
equivalence, or certify RFM, Link, DFE, CDR, BER, or a default route.
