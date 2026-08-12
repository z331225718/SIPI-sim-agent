# P3C Real-Constrained Fixed-Pole Fit v1

## Purpose

This product-owned core hardens the selected fixed-pole frequency fit into the
canonical real-SISO model required by the P3C execution contract. It accepts
only the existing static, in-memory `Hdiff` transfer and creates neither a
sealed S4P intake nor a time-domain waveform.

## Exact Model

For each allowlisted order 8, 12, or 16, the core constructs only
positive-imaginary poles in ascending frequency. Their negative-imaginary
partners are exact conjugates and are never stored independently. For a
positive member `p` and residue `r`, the response is:

```text
r / (s - p) + conjugate(r) / (s - conjugate(p))
```

The least-squares unknowns are the real and imaginary parts of each canonical
positive-member residue. The implementation stacks real and imaginary response
equations into one real-valued system; it cannot post-fit average, project, or
discard an unconstrained complex residue. Every pole must be strictly in the
left half plane, all model values must be finite, and the first order passing
the existing 0.5% RMS, 3% normalized peak, and 0.5% DC gates is selected.

## Boundary

The implementation retains the fixed 10 MHz-to-40 GHz pole construction,
single-threaded `faer` QR solver, rank gate, rejection behavior, and all
no-relocation/no-repair constraints. It has no caller options, file/artifact
surface, CLI, external S4P, waveform, recurrence, state-space export, or ADS
input. Global rational continuation and source/strobe semantics are contractual
only until the later direct-stepping core implements them.
