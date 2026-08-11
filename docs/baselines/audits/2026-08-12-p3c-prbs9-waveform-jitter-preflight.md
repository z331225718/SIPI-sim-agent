# P3C-01a PRBS9 Waveform And Jitter Preflight

This slice turns the user's supplied policy constraints into a fail-closed
preflight only. It fixes PRBS9 polynomial `x9+x5+1`, symbols `-1` and `+1`,
32 samples per UI, the requirement for a shared seed, strict-index waveform
comparison, no alignment, and a 1 percent relative RMS limit. NRZ jitter is
limited to a crossing-time TIE RMS observable. SNR is excluded and statistical
eye contour comparison remains blocked.

The preflight intentionally has no generator implementation, chosen seed,
sequence hash, UI duration, window, reference waveform, ADS bench identity,
stage, RMS normalization formula, crossing rule, interpolation, TIE tolerance,
or accepted receiver. It is not acceptance-ready and cannot invoke ADS, AMI,
DLL, PyBERT, channel, receiver, or CDR runtime. It also asserts that P4B stays
external-only and that the release publication compare row retains
`metric_profile_semantics_not_implemented`.

Verification passed:

```text
python -B tools/verify_p3c_prbs9_waveform_jitter_preflight.py
python -B tools/test_verify_p3c_prbs9_waveform_jitter_preflight.py
python -B tools/verify_clean_room_register.py
python -B tools/test_clean_room_register.py
python -B tools/test_verify_release_capability_publication.py
```

One Orca OpenCode reviewer performed the required read-only audit. Its first
pass reported 0 P1/0 P2 and identified one P3 test gap: release-publication
drift had no direct negative test. The second pass confirmed that the added
tests reject both a compare acceptance-state promotion and removal of the
metric blocker, with 0 P1/0 P2.

This policy does not relax the remaining P3C-01 blocker. The next execution
step requires owner-supplied, immutable definitions for the generator, seed,
reference/stage/timebase/window, RMS formula, and TIE acceptance semantics.
