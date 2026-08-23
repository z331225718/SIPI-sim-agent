# PB-01 Current Immutable Evidence Audit

Status: **blocked / open**

This successor evidence is generated only from candidate commit `64b783f66d7e986d0975be5ac3946b453b15c4ed`, tree `0e11721f2bb5b564002820cc7a5aaab45e30ba3b`, archive `c89bc44b36849724b9544eb6222a6431ecd3855ce4c943e6a3845cafe19375b9`. The pinned PyBERT oracle is commit `5bf6d7ea0ace261891aaeb611ffc1c267e160afe`, tree `5faef6bdb341d444ad65d82a11c0018b15805e24`, archive `e6ed484e87712e7120ea4314f21ae74386443ca90c6fe5f0bcfdbf1d99ebeb25`.

Two independent archive-only replays used run IDs `pb-01-current-bound-archive-01` and `pb-01-current-bound-archive-02`, with distinct nonces and report digests. Both processes exited zero, but `tx_out_p` differed from the oracle beyond the fixed tolerance. The row remains blocked; no parity or promotion is claimed. External AMI/IBIS, exact class pickle, and uncovered branches remain open.

The report and aggregate bindings in the successor manifest are content-addressed. Toolchain identity is exact across both runs; execution used only the immutable archive materialization.
