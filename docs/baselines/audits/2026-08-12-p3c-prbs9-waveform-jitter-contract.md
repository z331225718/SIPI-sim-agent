# P3C-01b PRBS9 Waveform And Jitter Contract

This slice records the owner-confirmed deterministic PRBS9 metric semantics:
Fibonacci `x9+x5+1`, seed `0x1a5`, a verified 511-bit period digest, differential
`-1 V`/`+1 V` rectangular NRZ, 32 GT/s with 32 samples per UI, and a third-period
comparison window after two warmup periods. It defines strict-index waveform
NRMSE, fixed-fold sampled-eye height/width, and raw crossing-time TIE metrics.

No alignment, resampling, gain/DC/polarity transform, de-mean TIE, or CDR is
permitted. The contract remains non-executing: ADS bench/waveform/stage identity
and an accepted receiver are absent, so acceptance, runtime, external-reference,
P4B worker, and release admission remain false. Statistical-eye contour work is
still blocked.

Verification passed:

```text
python -B tools/verify_p3c_prbs9_waveform_jitter_contract.py
python -B tools/test_verify_p3c_prbs9_waveform_jitter_contract.py
python -B tools/verify_p3c_prbs9_waveform_jitter_preflight.py
python -B tools/test_verify_p3c_prbs9_waveform_jitter_preflight.py
python -B tools/verify_clean_room_register.py
python -B tools/test_clean_room_register.py
python -B tools/test_verify_release_capability_publication.py
```

One Orca OpenCode reviewer performed the required read-only audit. Its first
pass found 0 P1/0 P2 and one P3 coverage gap: a broad mock only exercised the
historical preflight branch, not the P4B-drift branch. The fix adds a
path-sensitive P4B-only mock; the second pass found 0 P1/0 P2 and confirmed
the intended branch is directly covered.

The next P3C step requires an immutable external ADS bench and waveform
reference, plus an accepted receiver stage. No AMI asset execution is implied
by this contract.
