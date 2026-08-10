# P4A IBIS Typed Semantic Envelope Foundation v1

## Scope

`sipi-ibis` may transform a successfully parsed structural document into a
product-owned typed envelope. The envelope recognizes only a lexical document
version, component declarations, model declarations, a `Model_type` section
role, other bracketed section roles, and explicit section-block ownership.
It reads no file, external asset, URL, or profile record.

## Admission Rules

Exactly one document-version section is required. Its payload is one token
formed from two or more dot-separated decimal segments; this is lexical only
and does not select a supported IBIS revision. Component and model declarations
each require one ASCII identifier composed of letters, digits, `.`, `_`, or
`-`; duplicate names within their own declaration class are rejected. Data
records before the first bracketed section are rejected. Each subsequent data
record belongs to the most recent section block in source order.

Unknown bracketed keywords remain `Other` with their original spelling. They
are not rejected or assigned an electrical meaning.

## Profile Boundary

No required-keyword rule is instantiated in v1. The exposed profile-rule status
is explicitly `ProfileRulesUnavailable` until an owner selects an exact
external profile and independently freezes its selector, terminal binding,
PVT, stimulus, observables, tolerances, environment, and allowed oracle scope.

## Deliberate Omissions

This foundation defines no model body interpretation, component/model
relationship, pin/package/clamp/C_comp/PVT/table semantics, units, numeric
conversion, interpolation, Algorithmic Model or AMI behavior, electrical
evaluation, file I/O, CLI route, or external compatibility claim.

## Test Boundary

Tests use only project-authored synthetic structural documents. They do not
read the external pure-IBIS asset, its selector digest, public-standard text,
legacy parser output, or oracle data.
