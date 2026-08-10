# P4A Receiver Topology and Acceptance v1

## Receiver Layers

An electrical load is a receive-port termination. A resistor or an explicitly
defined lumped RC topology belongs here and changes the electrical boundary.

An IBIS receiver model is a standard-model branch. It is not automatically a
load or an AMI algorithm.

An AMI receiver algorithm consumes an explicitly defined sampled waveform and
time/clock contract. It is not a port impedance.

An Rx chain is only a future, profile-declared composition container. Every
stage order, handoff, unit, axis, and observable must be explicit.

## Current Rule

All composition is `explicit_profile_only`. There is no default or implicit
IBIS+AMI, RC+AMI, or any other receiver combination. This document implements
no runtime behavior.

## Candidate Boundary

The current example_rx record is a raw AMI ABI candidate only. Its associated
IBIS asset is not composed with it, and its Windows x64 declared DLL filename
does not match the authorized asset identity. It remains external-only and not
required.
