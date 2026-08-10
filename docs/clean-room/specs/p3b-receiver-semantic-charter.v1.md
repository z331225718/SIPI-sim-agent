# P3B Receiver Semantic Charter Preflight v1

## Purpose

This is the approval boundary between a generic caller-supplied receiver
preparation and the profile-specific DFE/CDR/BER behavior required by the RFM
profile. It intentionally records no algorithm or numerical default.

## Required Owner Decisions

An approved successor must specify the product stimulus and causal Link input,
DFE model/adaptation/tap order/cursor/units/sign, CDR detector/state/update/
lock/reset/cancel behavior, and BER reference/polarity/alignment/threshold/tie/
window/metric. It must also bind the external oracle stage scope and comparison
tolerances.

## Binding

The approval must bind the exact `sipi.receiver-semantics.v1` schema hash. It
must use an independent product specification for implementation and keep RFM,
PyBERT, and external-engine material in the observer/comparator boundary.

## Non-Claims

The pending charter is not an algorithm selection, receiver implementation,
RFM comparison, Link route, or capability promotion.
