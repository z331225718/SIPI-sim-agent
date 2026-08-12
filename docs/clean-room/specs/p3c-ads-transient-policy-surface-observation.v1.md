# P3C ADS Transient Policy Surface Observation v1

## Purpose

This observer records only the declared transient-convolution surface used by the
external P3C ADS oracle.  Its purpose is to make the missing product time-domain
policy explicit before any candidate waveform executor is proposed.

## Inputs and custody

- The observer reads the selected external `channel_gen5_highloss.s4p` by exact
  logical identity, length, and SHA-256.
- The observer reads a small fixed allowlist of locally installed ADS HTML help
  files and reports their logical names, lengths, and SHA-256 values only.
- It builds the already-authorized P3C netlist in memory with 100 as source
  edges.  It does not start ADS, load an AMI/DLL/IBIS asset, copy an external
  asset, create a waveform, or retain external bytes or paths.

## Required observations

- The generated `Tran` declaration uses `ImpLFEOn=yes`, `ImpApprox=no`,
  `ImpMode=1`, `ImpEnforcePassivity=yes`, `UseInitCond=no`, fixed strobe step,
  and `OutputAllPoints=yes`.
- The generated SnP declaration has no component-level passivity override.
- The installed help surface describes adaptive transient low-frequency sampling,
  adaptive impulse construction, and discrete-convolution periodic extension.
- The report records that the bench does not explicitly freeze convolution
  frequency grid, maximum frequency, impulse truncation/length, interpolation,
  or a product causalization/passivity algorithm.

## Boundary

The result is an external ADS policy-surface observation, not an ADS-parity
algorithm.  It cannot generate a product waveform or satisfy candidate/reference,
receiver, AMI, release, or statistical-eye acceptance.  A future product executor
needs a separately owner-approved deterministic policy for every unresolved item.
