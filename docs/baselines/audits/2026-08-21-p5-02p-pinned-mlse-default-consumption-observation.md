# P5-02p pinned-source MLSE default and consumption observation

Evidence schema: `sipi.p5-02p.pinned-mlse-default-consumption-observation.v1`.

This is a new, source-only observation for the P5-02 parameter gap. It binds
five parameter assignments and their selected downstream consumers to the
Agent-COM Git object `5272ffe74702cd585054d975559b06f8afae7b6e`. The source
file is `matlab_src/com_ieee8023_480.m`, tree
`7094ab6e84989b218730c52432c70da10261f8ea`, Git blob
`2e226d785c1ed2403f6d0a11288bf75939021814`, and normalized SHA-256
`88db14d7d82dab980d223a5be02a28013c11e0d0239e0e97e36c9d36fef55596`.

The matrix is deliberately narrower than a full COM parameter catalog:

| keyword | source fallback/alias | selected consumer |
| --- | --- | --- |
| `DER_CDR` | `1e-2` at line 8915 | `DER_DFE <= param.DER_CDR` at line 2187 |
| `trunc` | `128` at line 8926 | `j == param.trunc` and `j < param.trunc` at lines 2199 and 2204; warning at 2228 |
| `N_tc` | alias to the preceding `param.trunc` at line 8927 | shares the truncation consumers; it is not an independent default |
| `Q_budget_adj` | `0` at line 8930 | zero/nonzero branch at lines 2212/2215 and subtraction at line 2219 |
| `CDR` | `MM` at line 9222 | `switch OP.CDR` at line 3872, with `Mod-MM` and `otherwise % MM` branches |

The nested `xls_parameter` helper at line 10408 records case-insensitive
keyword matching, right-hand-cell consumption, fallback return when a default
is supplied, duplicate-key error behavior, and optional string evaluation.
The pinned Python reader at `src/agent_com/config/excel.py` records the
MATLAB `parameter` cell-array load surface through `scipy.io.loadmat` with
`simplify_cells=False`, followed by a two-dimensional `COM_Settings` cell
surface. These are source observations, not a product authority or an input
provenance statement.

The independent verifier
`tools/verify_p5_02p_pinned_mlse_default_consumption_observation.py` checks the
exact schema, status, source identities, reader/helper contracts, five-entry
order, source snippets, scope, non-claims, and audit binding. Its mutation
tests intentionally reject source, default, consumer, alias, reader, helper,
scope, and audit drift.

The default document-only verifier result explicitly reports
`source_git_object_checked=false`. Supplying an external Agent-COM checkout
with `--source-root` additionally runs `git rev-parse`, `git cat-file`, exact
blob SHA-256 checks, and exact line checks for every assignment, helper line,
input-shape line, and consumer line. The checkout path is deliberately not
recorded in this evidence or audit.

Validation completed with the document-only verifier (valid, five entries,
`source_git_object_checked=false`), the same verifier with the external
checkout (`source_git_object_checked=true`), and `python -B -m unittest
tools.test_verify_p5_02p_pinned_mlse_default_consumption_observation` (eleven
tests passed, including wrong commit/blob/line/reader/source-root mutations).
No Rust or MATLAB execution was needed for this document-only slice.

Open facts remain: workbook/config bytes and their generator invocation are
not bound here; the full parameter catalog, `missingParameter` follow-up, and
dynamic string-evaluation behavior are not closed; and no MATLAB execution,
Rust runtime implementation, checkpoint alignment, metric tolerance,
acceptance, or release decision is claimed.
