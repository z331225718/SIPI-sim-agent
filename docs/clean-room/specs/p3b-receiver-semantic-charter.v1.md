# P3B Receiver Semantic Charter Preflight v1

## Purpose

This is the approval boundary between a generic caller-supplied receiver
preparation and the profile-specific DFE/CDR/BER behavior required by the RFM
profile. Its pending record includes a proposed model, but it selects no
implemented behavior until the owner explicitly approves that proposal.

## Required Owner Decisions

The proposed v1 model is data-aided fixed-phase NRZ acquisition over 8 phases,
with 32 training UI and 96 measurement UI. It requires a caller-supplied 128
bit reference vector, uses a five-tap postcursor decision-feedback filter with
a 0.25 training step, then freezes coefficients for measurement. It makes zero
decisions erasures/errors and requires exact comparison for discrete lock,
decision, error-count, and BER outputs. This proposal is deliberately not an
interpretation of external configuration fields.

Owner approval must specifically confirm the external comparator can supply
the same reference-bit vector and receive waveform, and that it accepts this
data-aided fixed-phase / fixed-training receiver model and its stated stage
scope and tolerances. Otherwise the profile remains blocked.

## Binding

The approval must bind the exact `sipi.receiver-semantics.v1` schema hash. It
must use an independent product specification for implementation and keep RFM,
PyBERT, and external-engine material in the observer/comparator boundary.

## Non-Claims

The pending charter is not an algorithm selection, receiver implementation,
RFM comparison, Link route, or capability promotion.
