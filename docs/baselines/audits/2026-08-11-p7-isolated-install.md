# P7-04a Same-Host Isolated Install Admission

P7-04a is deliberately narrower than the PLAN's fresh-machine requirement. It
re-admits a P7-03a archive, streams the accepted product bytes into a new
external prefix, and invokes the prefix-local executable with a minimal loader
environment.

Its output must say `fresh_machine: false`, `fresh_user: not_assessed`, and
`promotion_status: blocked`. A fresh VM or machine remains required to close
P7-04. An external observation will be recorded only against a commit with a
matching P7-01a/P7-02a/P7-03a evidence chain.
