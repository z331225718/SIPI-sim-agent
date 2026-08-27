# COM-01 Direct-Port Source Map

Scope: the pinned Agent-COM config validate request/profile, schema-driven
materialization, package selection, and consumption-status artifact. The COM
runtime itself is not executed here.

| Pinned upstream path | Rust direct-port role | Status |
| --- | --- | --- |
| src/agent_com/cli.py | argument defaults, profile selection, text/JSON transport, error boundary | ported |
| src/agent_com/config/excel.py | XLSX/CSV/MAT loader and case-insensitive lookup | reused through sipi-com after direct pre-allocation preflight |
| src/agent_com/config/schema.py | schema, package split, duplicate warning, package references | ported |
| src/agent_com/config/materialize.py | source-order assignments, defaults, derived values, package case selection | ported for schema-reachable config-validate path; selected-package full oracle fixture open |
| src/agent_com/config/derived.py | DFE/core/package shape derivations | ported in direct module |
| src/agent_com/config/literals.py | MATLAB scalar/vector/matrix literals and default expressions | reused through sipi-com parser plus direct special cases |
| src/agent_com/config/consumption.py | implemented/report-only/unimplemented/obsolete/unverified field registry | derived registry consumed in Rust; full runtime trace sections open |
| schemas/behavior-presets.yaml | preset/fix-id catalog | exact MIT blob quarantined and parsed |
| schemas/r480-config.schema.yaml | complete r4.80 call/default catalog | exact MIT blob quarantined and parsed |
| src/agent_com/capabilities.py | materialized fingerprint boundary | ported: canonical key ordering, Python scalar int/float spelling, special-float tags, compact JSON string escaping, and float exponent formatting |

Exact pinned source Git identities and embedded resource hashes are bound in
docs/baselines/com-01-direct-port-preparation.v1.yaml. Resource custody is
restricted to the quarantine directory and its
NOTICE-AGENT-COM-CONFIG-MIT.md. Workbook and MAT fixture bytes are external
owner inputs and are never copied into this repository.

The direct module does not use a surface-only classifier as its materializer.
It executes the embedded schema calls, scales values, resolves defaults,
applies package and core derivations, and builds the consumption report.
Allocation-driving counts, input/output numeric-element totals, file/cell
sizes, and array dimensions are bounded in the Rust trust boundary. Override
keys are canonicalized to concrete schema calls so a case-insensitive match
cannot be silently ignored. Differential evidence stores only hashes, counts,
error categories, and bounded difference-key summaries; it excludes complete
materialized parameter values.

`config_preflight_v1.rs` is a lane-local admission guard required because the
shared readers allocate after ZIP/XML or MAT decompression. Before invoking
them it bounds XLSX member and aggregate uncompressed sizes, workbook/rels,
sharedStrings and target-sheet XML, explicit and rectangular sheet extents,
and MAT zlib expansion, nesting, element count, dimension count, and every
matrix dimension product. The shared readers remain the sole semantic decoders.

The pinned registry classifies source-exact `Do_White_Noise` as
unimplemented. The trusted workbook materializer retains that option only in
its source consumption/diagnostic record, with scope limited to the
Wiener-Hopf branch; that branch remains fail-closed. It is not projected into
the generic COM DTO or numerical chain, and public JSON cannot inject it.

The materialized fingerprint writer mirrors the pinned `capabilities.py`
boundary rather than delegating to `serde_json`: source integer cells retain
their JSON integer spelling, floating scalars use Python's fixed/scientific
notation thresholds and padded exponents, and the materialized JSON special
float envelope is normalized to the pinned `__float__` sentinel. JSON object
keys are sorted at every level and strings use Python's ASCII-safe
`json.dumps` escaping. The writer is bounded by the same 16 MiB trust budget
as the configuration input, checks every escaped character (including UTF-16
surrogate expansion) with checked byte accounting, and rejects cumulative
materialized/default-copy storage before cloning default maps. Derived core
fields overwrite stale integer-origin markers as floating values, and matrix
JSON projection recursively preserves special-float envelopes. Focused tests
cover these first-divergence and budget cases; broader upstream replay
evidence remains a separate immutable artifact and is not overwritten by this
source change.
