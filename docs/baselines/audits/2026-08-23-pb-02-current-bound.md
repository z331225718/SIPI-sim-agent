# PB-02 Current Immutable Evidence Audit

Status: **blocked / open**

The candidate is the archive of commit `64b783f66d7e986d0975be5ac3946b453b15c4ed`, tree `0e11721f2bb5b564002820cc7a5aaab45e30ba3b`, archive `c89bc44b36849724b9544eb6222a6431ecd3855ce4c943e6a3845cafe19375b9`. The oracle is PyBERT commit `5bf6d7ea0ace261891aaeb611ffc1c267e160afe`, tree `5faef6bdb341d444ad65d82a11c0018b15805e24`, archive `e6ed484e87712e7120ea4314f21ae74386443ca90c6fe5f0bcfdbf1d99ebeb25`.

Two fresh archive-only `sim-native` replays (`pb-02-current-bound-archive-01` and `pb-02-current-bound-archive-02`) had distinct report digests/nonces and identical toolchain identity. Both candidate and oracle processes exited zero, but the logical NPZ member sets were not equal. This is blocked payload evidence, not promotion. External AMI/IBIS branches remain quarantined.
