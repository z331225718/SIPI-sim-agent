# Current Owner-Input Reconciliation v2

This additive record reconciles the five owner-decision rows that were still
listed by the historical owner-input request. The historical
`owner-input-request.v1.yaml` and `owner-decision-checklist.v1.md` remain
byte-for-byte unchanged.

The accepted recommendations are deliberately narrow:

- `P3B-02`: RX CTLE followed by RX FFE, each explicitly selectable or bypassed;
  no automatic tuning or silent default, and no widening of the v1
  bypass-only contract.
- `P3B-04`: the current public profile has `cdr=none`; lock/reset/cancel are
  not applicable. AMI-internal CDR belongs only to a future authenticated
  route, and the existing 04b core is not a clock source.
- `P3B-05`: PRBS9 with seed `0x001`, caller-supplied TX sample-unit time warp,
  `p=n+shift[n]` linear interpolation, no RNG or amplitude noise, and no
  external tolerance claim.
- `P3C-01`: the exact selected-highloss profile is receiver-free and
  waveform-only. Eye, TIE, and bathtub observables are excluded; Q/0.1 dB is
  generic or future receiver capability only, not a closed-eye fallback.
- `P4A-01`: freeze only the exact IBIS 5.0 file and the observed structural
  inventory. Inventory exhaustiveness remains implementation work;
  model/corner behavior and parser behavior are not guessed, and behavior
  selection moves to P4A-02/P4A-03.

These decisions remove `owner_decision` from the current blocker class. The
P3B-02 equalizer implementation and P4A-01 exhaustive structural inventory
remain `semantics_not_implemented`; the other three narrow owner-decision
rows are scoped-closed, with downstream behavior or acceptance still tracked
by P3B-03, P3C-02/03, and P4A-02/03.
The current owner request contains exactly the five external asset/oracle rows
`P1-04B`, `P4B-08`, `P4B-09`, `P5-02`, and `P5-06`.

The verifier rejects decision tampering, resolved rows reappearing in the
current request, structural IBIS inventory being used as behavior selection,
waveform-only policy being generalized to arbitrary closed eyes, and any
contradiction between public `cdr=none` and the historical 04b CDR-lock core.
It also binds the five external rows to their exact gate lists, rejects a
synchronized request/ledger gate substitution, checks the ledger open count,
and fixes the PLAN checkbox states for the two remaining semantic items and
the three scoped-closed items.

Verification entry point: `tools/verify_owner_decision_reconciliation_v2.py`.
