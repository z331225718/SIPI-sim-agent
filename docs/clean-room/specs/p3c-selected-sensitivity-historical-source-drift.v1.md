# P3C Selected Sensitivity Historical Source Drift v1

This reconciliation preserves the selected OOB zero-extension and full bounded
truncation sensitivity observations as historical records only. It binds each
immutable report to its SHA-256 and requires its original verifier to reject
the current product tree with the exact source-drift token.

Neither record is a current observation or a successor selection. The
reconciliation does not replay external custody, choose an OOB or truncation
policy, admit a kernel or candidate waveform, or change NRMSE acceptance,
receiver, passivity, causal-FIR, or release gates.
