# P3B Delegated Phase Selection v2

This project-owned, profile-scoped amendment applies only to
`channel-rfm-block-2-current-drive-v1`. It is a forward semantic revision; it
does not rewrite the approved fixed receiver v1 or its erasure amendment.

The receiver retains all v1 acquisition inputs and calculations: eight phase
candidates, the first 32 data-aided symbols, score equal to absolute class
separation, and a one-percent relative unique-winner margin. A finite,
positive best score that is uniquely at least one percent above the next score
uses the v1 path unchanged and reports `unique_locked` and `locked`.

When the best score is finite and positive but fails the unique-margin rule,
the receiver forms the contender set whose score is at least
`best_score / 1.01`. It selects the smallest phase index in that set and
reports `delegated_ambiguous_tie_break` plus
`policy_selected_not_locked`. DFE, erasure feedback, and the fixed 96-symbol
BER computation then proceed unchanged. Their output is a
`policy_selected_diagnostic` only.

Zero, non-finite, or otherwise unqualified best scores reject with
`cdr_unqualified`; there is no default phase. This amendment adds no phase
tracking, RFM input, Python dependency, CLI route, Link-stage admission, or
required-profile acceptance claim.
