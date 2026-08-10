# P4A IBIS 7.1 Behavior-Scope Preflight v1

## Scope

This observer-only record establishes a narrow bridge between the official
IBIS 7.1 document listing and the already pinned `example_rx` candidate facts.
The public standard is used as an observation basis only; its body, tables, and
algorithms are not copied into this repository or supplied as implementation
material.

The candidate is an Input-model observation with `C_comp`, GND clamp, POWER
clamp, package, temperature, voltage, and Algorithmic Model attachment
presence. Values, curve samples, and evaluation rules are intentionally absent.

## Boundary

Input electrical behavior and AMI algorithmic behavior remain separate future
scopes. An Algorithmic Model attachment does not establish a callable DLL,
AMI runtime, or an implicit IBIS-plus-AMI composition. The declared Windows
x64 DLL identity mismatch continues to prohibit a black-box run.

## Deferred Semantics

Model parsing, interpolation, clamp evaluation, package handling, PVT corner
selection, waveform/timebase contract, and every runtime result remain
undefined until a required asset/profile and an independent product semantic
contract are selected.

## Non-Claims

This preflight does not provide an IBIS parser, electrical model, AMI host,
runtime execution, numerical acceptance, or release capability.
