# P3C Residual DFT Currentness Reconciliation

The residual-DFT observation was produced from clean archive
`97b0f271abcb7df02a3a9b259c4dafee86f3a783`. Subsequent product changes make
its 30-path source inventory differ from the current candidate. The historical
record remains byte-for-byte preserved, while its original verifier now
returns exactly
`p3c_selected_highloss_residual_dft_current_head_evidence_failed:source_drift`.

This additive record removes the old current-only verifier from the active
open-item gate sweep and replaces it with an exact source-drift gate. It does
not replay external assets, inherit the historical NRMSE/band results as
current, modify a waveform, relax the fixed one-percent limit, or promote a
receiver/profile/release state.
