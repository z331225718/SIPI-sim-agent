# COM Workbook ACCM Replay V6

Two independently materialized clean candidate archives at `b1cc5884` were
compared with a clean Agent-COM `5272ffe` archive through its public runtime.
The selected two-vector, two-package-case matrix matched every common public
scalar within `1e-9`; the largest observed FOM delta was `7.460698725481052e-14`.

Current candidate DFE publication is present on both sides. Agent-COM applies
the workbook Port Order internally, but its public `RunResult` does not expose
that value; V6 records it as not comparable rather than fabricating a mismatch.
This is a scoped observation, not a full result-graph parity, generic COM,
standards, acceptance, or release claim.
