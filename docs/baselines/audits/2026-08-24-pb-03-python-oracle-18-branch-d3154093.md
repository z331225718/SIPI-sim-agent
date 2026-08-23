# PB-03 18-Branch Python Oracle Audit

The 18-entry inventory is an additive successor of the prior PB-03 branch probe and Python-oracle manifests. It is bound to immutable candidate `884b430bee61d365793a3810beaeb76f58bee25c` / tree `d87b058e754eea1ae5f104df034a81b4b13dcb1d` and pinned upstream `5bf6d7ea0ace261891aaeb611ffc1c267e160afe` / tree `5faef6bdb341d444ad65d82a11c0018b15805e24`.

The two fresh archive-only reports executed a real `PythonSimulationBackend`, independently of Rust. NRZ and PAM4/noise/DFE payloads compared 13 adapter-emitted fields. Duo-binary, Viterbi/ISI, FEC, S2P, and CTLE branches were also invoked; their reports retain concrete candidate/oracle exit and payload evidence, and remain blocked on crossing behavior, telemetry mismatch, the pinned FEC decoder error, or channel/CTLE payload mismatch. No status-only result was promoted. AMI/IBIS/TS4/getwave and exact class-pickle branches remain external or data-contract blockers.

The 18 pure-code branch probes have `portable_branch_probe_missing=[]`; this is deliberately distinct from the nonempty `python_payload_oracle_missing` list. The latter prevents an honest branch probe from being mislabeled global Python parity.

The existing focused verifier returned `valid` and its eight mutation tests passed; the additive 18-branch verifier returned `valid` and its twelve mutation tests passed. Historical v1/v2 manifests were not rewritten.
