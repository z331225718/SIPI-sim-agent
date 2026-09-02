# PB-01/PB-03 archive source corpus

Two independent archive-built replays compared candidate `58f3c99b` against
pinned PyBERT `5bf6d7e`.  Both passed the PB-01 source-loadable class-pickle
contract and PB-03 baseline/analytic-CTLE 150-member artifact contracts; both
also rejected gain `1.1` without publishing `meta.json` or `arrays.npz`.

The reports bind distinct run IDs, nonces and report hashes.  PB-01 compares
the logical class graph and numeric arrays rather than nondeterministic pickle
container bytes.  PB-03 permits only input path, runtime run ID and engine
build provenance normalization.  The aggregate remains deliberately scoped:
no whole-PyBERT, root CLI, license, distribution or release conclusion.
