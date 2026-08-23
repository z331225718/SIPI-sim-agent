# AS-04 tune-yparam-tran immutable v2 audit

Candidate commit 64b783f66d7e986d0975be5ac3946b453b15c4ed tree 0e11721f2bb5b564002820cc7a5aaab45e30ba3b was materialized with git archive into a clean temporary root for each fresh replay. Upstream authority is Agent-Spice commit 2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5, tree b6bde97128030d6cea0d68b2f0a35d807be8c402, MIT.

The two reports are immutable-archive-bound, independently nonce/run-id tagged, report-SHA distinct, and use the same recorded cargo/rustc/python identities. Nelder-Mead control observation; HSPICE execution fail-closed. No numerical parity or acceptance tolerance is claimed.

AS-05 S-elements remain explicitly unsupported where no pinned portable S-domain exporter exists; no Y-fit substitution is allowed. External simulator execution is never fabricated.

The preparation helper was loaded from the candidate archive itself, and its path-free SHA was recorded in both reports and the manifest; the working-tree helper was not executed.

The top-level manifest toolchain is checked against both immutable replay reports and the aggregate; any drift is rejected.
