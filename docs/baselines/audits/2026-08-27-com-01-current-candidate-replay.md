# COM-01 Current Candidate Replay Audit

Date: 2026-08-27

This audit records two fresh immutable replays of the current COM-01
config-validate leaf.  The business candidate is commit
bc882d2e5a19c2a844bacc485ede5b874e8f9c37 with tree
d87cfecea77ccd670073a6c069658e6b4e8c3137.  The external oracle is pinned to
Agent-COM commit 5272ffe74702cd585054d975559b06f8afae7b6e with tree
7094ab6e84989b218730c52432c70da10261f8ea.  Both inputs were materialized
from immutable Git archives and the oracle ran with frozen offline uv.
The replay harness is commit e74e10d2933b1ddbc73f7da1a7785ca15ba49e09
with tree 2e49b25641439d29110747edde157eb232d1250c.  Its four COM-01
tool blobs and raw SHA-256 values are bound by the manifest physical map and
the report harness-source receipts.

The 14-scenario matrix produced 6 passed value projections, 7 matching error
codes and categories, and 1 materialized-fingerprint-only drift.  The
fingerprint scenario had an equal bounded value projection and no difference
keys, but its exact serialized fingerprint differed.  This is retained as an
explicit blocker; the report is not a parity, product, migration, or release
gate.

The committed report bindings are:

- run 1: 53415dcbf1d7eb45ca1c62fc8bdccd8ba8c14f014a08eba22a7057f575df00ee
- run 2: 29d947762dc3dc04cea3aac08366f494dfa6faac1d277d2d2f9f8d47befe671d
- aggregate: 07c1f59bb2bfa61c35c0ad1eaadfdd4077048db8d4ee09c9b5db4bb0f2118c78

Cargo's release artifact was admitted as a regular in-target source even
when Cargo represented it as a hardlink.  Each replay copied it with
exclusive creation into a run-local execution directory and bound source and
copy pre/post basename, byte count, SHA-256, and link count.  The two Windows
PE copies had different raw SHA-256 values.  No canonical PE normalization
strategy is claimed, so raw binary reproducibility remains environment-local
and scoped; this does not weaken the stable semantic observations above.

The evidence stores bounded hashes, counts, error categories, warnings and
consumption summaries only.  It stores no raw workbook/configuration values.
S-parameter fitting is outside this row.  Channel simulation remains
impulse-only and is not exercised by this evidence.
