# P5-09 COM Behavior-Replica Wording Audit

## Scope

This slice closes only a wording/scope candidate for a selected COM R4.80
behavior profile. No completed behavioral replication is claimed. It does not
close COM acceptance, external comparison, metric tolerances, runtime
integration, or artifact provenance, and it does not establish a product
capability.

The required disclaimer is:

> Wording candidate only; this is not IEEE official certification.

The capability wording also explicitly rejects an IEEE official certification,
standards-compliant result, validated, approved, qualified, equivalent,
matching, or passing result, reference implementation, conformance result, or
completed behavioral replication. Positive wording must not use IEEE-certified,
standards-compliant, validated, approved, qualified, equivalent, match/pass,
parity, conformance, release, or acceptance language. The only positive scope
is a candidate wording contract; it must not claim completed behavioral
replication.

## Bound Evidence

The selected profile remains `com-r480-envelope-v1`. The existing acceptance
record still marks the authoritative reference as missing and product
self-comparison as forbidden. The existing publication row keeps `com.run`
unavailable and blocked on `authoritative_reference_missing`. The P5-08 slices
remain bounded admission/execution/local-metadata work rather than a full COM
runtime or oracle workflow. The R4.80 custody preflight retains the external
oracle, metric/checkpoint/tolerance, and runtime provenance blockers.

The machine verifier checks the exact hashes and required fields in the bound
records. It does not alter any existing COM command, publication, Rust source,
PLAN, ledger, owner request, license map, or historical document.

## Closure

P5-09 can be scoped-closed for this wording contract only. The external oracle,
full metrics and tolerances, full runtime/artifact/provenance, product
capability, product acceptance, and promotion states remain blocked, not
claimed, or false.
