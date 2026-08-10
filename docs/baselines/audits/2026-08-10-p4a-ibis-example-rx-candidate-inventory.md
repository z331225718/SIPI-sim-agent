# P4A-01a IBIS Example Rx Candidate Inventory Audit

- Candidate commit: `0ba8d17`
- Reviewer: Orca independent read-only reviewer
- Review message: `msg_5505b9d9cf47`
- Conclusion: `0 P1 / 0 P2`

The observer-only inventory freezes the external `example_rx` asset identities
and bounded P4A metadata. The profile remains `candidate`, `oracle_only`, and
not required. Its declared Windows x64 DLL filename does not match the
authorized asset name, so the record remains blocked instead of attempting any
resolution or runtime load.

No product parser, electrical behavior, AMI host, or release capability is
accepted by this audit.
