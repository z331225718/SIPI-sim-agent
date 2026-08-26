# AS-03 fit-yparam numeric checkpoint audit

## Scope

This is an integrity-only checkpoint for the already implemented AS-03
`fit-yparam` path. It does not add an algorithm, public API, tolerance, S-parameter
fit, AS-05 Xyce/XDM work, or a release claim.

## Physical execution

Two fresh runs materialize the candidate and pinned Agent-Spice sources with
`git archive`. The candidate probe is appended only inside the temporary archive
as a private Rust unit test and calls the existing `convert_s_to_y` function. The
upstream probe imports the archived Agent-Spice source plus the bound scikit-rf
and NumPy runtime and reads `skrf.Network.y[0]`. Neither side is represented by a
reimplemented comparison formula.

The candidate probe no longer contains a literal S matrix. It reads the same
Touchstone file through the existing bounded `read_multiport_touchstone` parser,
then passes parser sample zero and its parsed reference impedance directly to
`convert_s_to_y`. The runner independently parses the fixed fixture's header and
first row and requires the runner, Rust parser, and scikit-rf parser receipts to
match exactly, including IEEE-754 S-matrix and impedance bits.

The report binds commit, tree, archive digest, source blobs obtained with
`git rev-parse COMMIT:path` plus `git cat-file blob`, tool and module identities,
fixture bytes, stdout/stderr digests, and all four complex matrix cells as exact
IEEE-754 bit patterns. The reciprocal anchor covers both physical byte digests,
both normalized logical digests, both source identities, the fixture, and the
comparison.

The verifier independently rebuilds both physical and normalized hashes from the
matrix bit strings, derives every residual and its location, and rebuilds the
reciprocal execution anchor. It also invokes the aggregate builder on the two
reports and requires the stored aggregate to be bit-exact JSON-equivalent. Thus
a coordinated edit to a report, aggregate, and manifest must still satisfy the
physical residual and stable-field gates rather than merely updating hashes.
The verifier additionally carries independent fixed candidate and upstream
physical/normalized SHA-256 anchors and the complete expected matrix graph. This
closes two residual coordination cases: changing a component that was equal on
both sides, and changing only a decimal rendering while retaining its IEEE bits.

The physical checkpoint corrects an imprecise earlier narrative. In row-major
order the first differing component is `[0,0].re`, with residual
`4.163336342344337e-17`. The maximum observed residual is
`5.551115123125783e-17` at `[1,1].re`; the earlier weak diagnosis had described
that value as `[0,0]`. This audit preserves the measured matrix rather than
editing the result to match the narrative.

## Trust boundary

There is no independent external trust root. The two executions, normalized
hashes, and reciprocal anchor provide the strongest locally available
tamper-evident integrity gate, not an authenticity or acceptance proof. The
result remains `blocked_numeric_semantics`: the existing Rust path uses manual
Gauss-Jordan S-to-Y arithmetic and faer QR least-squares, while the pinned path
uses scikit-rf/NumPy conversion and `numpy.linalg.lstsq(..., rcond=None)`.

The verifier uses recursive exact-type equality. JSON integer fields cannot be
substituted by floats or booleans, including frequency/sample/port counts,
archive byte counts, and replay count. Paths are repository-relative in the
evidence; runner inputs are parameterized. Resolved repository, report, archive,
and materialized-file custody rejects traversal, symlink/reparse escape, and
multi-link archive files.

Every git, cargo, rustc, Python, NumPy, and scikit-rf identity is sampled before
and after execution and must remain exactly equal. All subprocess pipes are
drained by bounded readers with explicit time and byte limits; overflow or
timeout kills the child and fails the replay without publishing a report.
