# P3B Receiver Semantics Preparation v1

## Purpose

This contract preparation makes receiver dependencies explicit without selecting
a DFE, CDR, decision, or BER implementation. It is not an acceptance semantic
charter for the required external RFM profile.

## Required Caller-Supplied Inputs

`sipi.receiver-semantics.v1` requires all of the following:

- known binary reference bits and an explicit voltage-to-bit polarity;
- a finite fixed DFE coefficient vector and cursor index;
- explicit, strictly increasing sample indices as a clock observation plan;
- a bounded BER observation window, finite decision threshold, and explicit
  tie rejection.

The contract has no defaults. It validates presence, bounds, finite values, and
ordering only. It neither evaluates the coefficient vector nor recovers clocks,
makes decisions, or counts errors.

## Deferred Charter

The required RFM profile remains blocked until an owner approves a separate
semantic charter defining the DFE model/tap order/adaptation, CDR detector and
state/lock rules, BER reference/alignment/polarity/window/metric, exact oracle
scope, and comparison tolerances. This preparation must not be treated as that
charter or as RFM receiver parity.
