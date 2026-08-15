# P7 IBIS Inspect Publication Binding

The `ibis.inspect` row now binds the existing structural-only capability audit,
not the unrelated external static-DC acceptance report. The live descriptor
remains a caller-supplied UTF-8 structural inspection surface with electrical
behavior and external-profile acceptance not evaluated.

The publication verifier fixes the route, schemas, non-oracle state, blocker,
non-claim, capability-contract index, and immutable audit digest. This does
not add file access, electrical evaluation, external asset custody, AMI, or
release acceptance.

## OMP Audit

The existing OMP reviewer performed a read-only audit of the staged route
binding. It reported zero High and zero Critical findings after the full
publication suite passed 26 of 26 tests, including the real CLI manifest
integration check. The metadata verifiers also passed without edits.
