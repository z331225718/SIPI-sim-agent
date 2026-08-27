# COM-03 Current Candidate Replay Audit

Date: 2026-08-27

This audit records two fresh immutable replays of the current COM-03 compare
leaf.  The business candidate is commit
bc882d2e5a19c2a844bacc485ede5b874e8f9c37 with tree
d87cfecea77ccd670073a6c069658e6b4e8c3137.  The external oracle is pinned to
Agent-COM commit 5272ffe74702cd585054d975559b06f8afae7b6e with tree
7094ab6e84989b218730c52432c70da10261f8ea.  Both inputs were materialized
from immutable Git archives and the oracle ran with frozen offline uv.
The replay harness is commit e74e10d2933b1ddbc73f7da1a7785ca15ba49e09
with tree 2e49b25641439d29110747edde157eb232d1250c.  Its four COM-03
tool blobs, the shared COM-01 custody helper, and their raw SHA-256 values are
bound by the manifest physical map and report harness-source receipts.

The 23-scenario matrix covered matched documents, mismatches, malformed JSON,
invalid schema, negative tolerance, and missing files.  All 23 candidate
results matched the oracle exit code and stdout projection: 7 successful
matches and 16 matching error branches.  This is a scoped behavioral
observation only.  It does not promote complete COM parity, a product
capability, a migration row, or release readiness.

The committed report bindings are:

- run 1: b2f42694211b7a6a614023627b54612407171fa6d6fbed058f95ec353b20573f
- run 2: a16438887fb11bedcea9e6cd867b1d95b76a17b072690af1ca217c7e082d2d35
- aggregate: 841647723f0f215f1d08d2e56d3ba1acaf612807c91d339b9516353f22762bf0

Cargo's release artifact was admitted as a regular in-target source even
when Cargo represented it as a hardlink.  Each replay copied it with
exclusive creation into a run-local execution directory and bound source and
copy pre/post basename, byte count, SHA-256, and link count.  The two Windows
PE copies had different raw SHA-256 values.  No canonical PE normalization
strategy is claimed, so raw binary reproducibility remains environment-local
and scoped; the 23 semantic branch observations remain identical.

The evidence keeps independent payload names and bounded payload hashes.  It
does not commit or return the payload documents.  S-parameter fitting is
outside this row.  Channel simulation remains impulse-only and is not
exercised by this evidence.
