# P3C Selected High-Loss Residual Diagnostic v2 Observation

This external-only observation replays the exact selected S4P custody chain
with the owner-confirmed finite-edge PRBS9 source projection v2. It consumes
the immutable ADS canonical RX waveform as the reference and evaluates the
already implemented strict-index time-domain residual diagnostic.

Each of two fresh runs must independently seal and admit the S4P, generate a
v2 candidate, reread the ADS reference before and after extraction, and use
the same three fixed 16,352-sample partitions. The third period diagnostic
NRMSE must be bit-identical to the v3 waveform-only NRMSE for the same pair.

The observation retains only scalar bit patterns, hashes, fixed offsets, and
manifest identities. It retains no source path, waveform, residual vector,
or ADS payload. It has no CLI, transform, alignment, repair, changed source
policy, acceptance threshold, receiver claim, or release effect.
