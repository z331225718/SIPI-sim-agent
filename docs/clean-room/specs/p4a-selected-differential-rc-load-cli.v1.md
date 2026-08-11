# P4A Selected Differential R-C Load CLI v1

`sipi rx-load differential-rc-evaluate --stdin` evaluates exactly one
product-owned continuous constitutive relation. It accepts one strict JSON
document with schema `sipi.rx-load.selected-differential-rc-evaluate.request.v1`:

```json
{"schema":"sipi.rx-load.selected-differential-rc-evaluate.request.v1","probe":{"p_to_ref_volts":0.5,"n_to_ref_volts":-0.5,"p_to_ref_slope_volts_per_second":1000000000.0,"n_to_ref_slope_volts_per_second":-1000000000.0}}
```

The topology is fixed: a 100 ohm resistor from P to N and one 1 pF capacitor
from each of P and N to the explicit REF terminal. REF is a terminal role, not
an implicit global ground or node zero. The request must provide finite P/REF
and N/REF voltages and their continuous slopes. It cannot override the
topology, values, sign convention, or reference terminal.

All reported terminal currents are positive when flowing into the load
terminal. The report also includes the P-to-N resistor and the two capacitor
branch currents. It follows the existing continuous relation without inferring
slopes or selecting a numerical integration rule.

The command has no file, URL, asset, IBIS, AMI, channel, waveform, timestep,
history, state, artifact, or default routing surface. It does not solve a
channel termination, compose with an IBIS model, support a single-ended load or
a P-to-N capacitor, or claim external-profile acceptance.
