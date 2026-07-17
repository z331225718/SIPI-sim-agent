# Agent-Spice Rust PI/SI engine

This is the new project-owned simulation core. Its deliberately narrow target is
PI/SI rather than full device-level SPICE compatibility.

Current executable slice:

- R, C, L, independent voltage/current sources, and E/F/G/H controlled sources;
- HSPICE-compatible resistor flooring with default `RESMIN=1e-5` and
  `.option RESMIN=...` overrides;
- nested parameterized `.subckt`, `.global`, recursive relative `.include` /
  `.inc`, external `.lib` section selection, numeric and `str('...')` `.param`,
  nested `.if`/`.elseif`/`.else`/`.endif`, and SI numeric suffixes;
- operating point, single-source DC sweep, complex AC sweep, and adaptive Trap
  or variable-step Gear2 transient analysis with backward-Euler restart;
- device-state LTE control for capacitor charge, inductor flux, and RFM dynamic
  output voltage, including rejected-step rollback and source-breakpoint restart;
- direct `VERSION 200600` RFM N-port parsing, S-to-Y OP/DC/AC stamping, and
  sparse Trap/Gear2 state-space TRAN companions;
- native HSPICE `S` elements with per-port positive/negative node pairs and
  `.model <name> S [N=...] RFMFILE='...'` model loading;
- real and complex sparse LU through `faer`, with symbolic reuse, numeric-factor
  caching, compressed stamp replay, and parallel AC frequency blocks;
- `PULSE`, inline `PWL`, and two-column HSPICE `PWL PWLFILE=...` transient
  sources, including `M`, `TD`, and `R` options;
- recursive native compatibility audit with one JSON issue list for directives,
  elements, source functions, and source options;
- native HSPICE `.measure` evaluation for `FIND ... AT`, `FIND ... WHEN`,
  standalone `WHEN`, `TRIG/TARG`, `TRIG AT`, `MIN`, `MAX`, `AVG`, `RMS`,
  `DERIV ... AT/WHEN`, `INTEG`, and ordered `PARAM` expressions; event
  selectors include `TD`, numbered `RISE/FALL/CROSS`, and `LAST`, alongside
  `FROM`/`TO` windows, differential voltage, branch current, and AC
  real/imaginary/magnitude/phase targets;
- JSON output compatible with the existing Python/native result shape, plus
  direct `native_result.json` and waveform CSV output for `run-rfm` and
  `run-hspice`; simulation progress is printed to stderr and waveform CSV rows
  are flushed while the selected analysis is still running.

Build and run on Windows:

```powershell
tools\build-rust-engine.ps1
native\agent-spice-sim\target\release\agent-spice-sim.exe tests\fixtures\hspice\rust_linear_pi.sp
native\agent-spice-sim\target\release\agent-spice-sim.exe `
  native\AgentSpice.Engine\fixtures\rfm_tran.cir `
  --rfm native\AgentSpice.Engine\fixtures\one_port.rfm `
  --output-json native-result.json `
  --waveform-csv waveform.csv

native\agent-spice-sim\target\release\agent-spice-sim.exe legacy.sp `
  --audit-json native_compatibility.json
```

Progress remains visible in the terminal because it uses stderr, while stdout
keeps its machine-readable JSON contract. `waveform.csv` is readable during a
long simulation and retains its flushed rows after `Ctrl+C`; the final JSON is
written only after a successful completion.

Set `AGENT_SPICE_PROFILE=1` to append a TRAN hot-path breakdown for matrix
stamping, sparse solving, candidate-state updates, and LTE evaluation. This is
intended for comparing difficult production decks without a profiler installed
on the target machine.

Netlist parse and parameter errors include the absolute source path, physical line number,
original statement, and the expanded statement when a subcircuit rewrite changed it.

Run the local HSPICE compatibility gate:

```powershell
python scripts\compare_rust_hspice_pi.py `
  --rust-engine native\agent-spice-sim\target\release\agent-spice-sim.exe `
  --output artifacts\rust-hspice-linear-pi

python scripts\compare_rust_hspice_measure_events.py `
  --rust-engine native\agent-spice-sim\target\release\agent-spice-sim.exe `
  --output artifacts\rust-hspice-measure-events

python scripts\compare_rust_hspice_rfm.py `
  --rust-engine native\agent-spice-sim\target\release\agent-spice-sim.exe `
  --output artifacts\rust-hspice-rfm-final
```

Run an ordinary HSPICE-style PI deck through the project-owned engine:

```powershell
python -m agent_spice.cli run-hspice tests\fixtures\hspice\rust_linear_pi.sp `
  --backend native --execute
```

Both `run-hspice` and `run-rfm` now default to the Rust engine. The wheel build
packages `agent-spice-sim` under the host runtime identifier; C# remains a
migration oracle for the frozen device-model work, not the PI/SI runtime core.
The native HSPICE path is dialect-native: it audits and executes the case text
without converting `.inc`, `.probe`, or HSPICE output options to another syntax.
Native measurements are emitted in both `native_result.json` and the Python
`run_summary.json`. `PARAM` expressions may reference earlier measurements,
deck parameters, SI literals, and the native math-function set. `DERIV` uses
local output-grid slopes and `INTEG` uses trapezoidal window integration.
Signal-to-signal event comparisons and optimization qualifiers remain explicitly
unsupported rather than falling back to another simulator.
