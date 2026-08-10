# P4A Selected Differential R-C Load V1

## Scope

This product-owned relation evaluates one selected three-terminal electrical
load at a continuous instant. It has terminals `P`, `N`, and `REF`. `REF` is
an explicit terminal and never an implicit global ground.

The fixed elements are a 100 ohm resistor from `P` to `N`, a 1 pF capacitor
from `P` to `REF`, and a separate 1 pF capacitor from `N` to `REF`.

## Inputs And Outputs

The caller supplies finite `V(P)-V(REF)`, `V(N)-V(REF)`, and their explicit
continuous derivatives in volts per second. The evaluator never derives a
derivative from sampled data.

All terminal currents are positive into the load terminal. With
`i_r=(V(P)-V(N))/100`, `i_cp=1pF*dV(P)/dt`, and
`i_cn=1pF*dV(N)/dt`, the outputs are:

```text
i_P   = i_r + i_cp
i_N   = -i_r + i_cn
i_REF = -(i_cp + i_cn)
```

All inputs and derived currents must be finite. Any derived overflow rejects
the operation without a partial result.

## Deliberate Limits

This is a continuous constitutive relation only. It does not choose an
integration method, retain capacitor state, bind `REF` to a channel return,
solve a channel or network, infer a derivative, accept a generic R/C value,
or expose a CLI route. It does not implement a P-to-N capacitor, a
single-ended load, IBIS, AMI, package, PVT, V-T, or ramp behavior.
