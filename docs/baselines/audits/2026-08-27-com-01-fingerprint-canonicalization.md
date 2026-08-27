# COM-01 Fingerprint Canonicalization Audit

Date: 2026-08-27
Work item: COM-01 `config validate`
Status: fixed in the working tree; pending a new immutable candidate replay

## Finding

The previous formal COM-01 replay had one `values_equal_fingerprint_drift`
scenario, `xlsx_materialized_json_default`. The materialized parameter and
option maps had identical keys and values, but the digest differed:

| producer | materialized fingerprint |
| --- | --- |
| candidate before this fix | `2d0791ee45451a46093e3318c16d3c3b3797ef3fecb687fa56db84aaa8ef7532` |
| pinned Agent-COM | `d6963c122533d58273e4ebf3224bade1dc38b040f740c1cd92d4c9727e4483dc` |

The first divergence was canonical representation, not materialization:

1. Python workbook integer cells remained JSON integers, while the Rust
   projection had converted them to `2.0`-style JSON floats.
2. Python `capabilities._canonical` maps non-finite values to
   `{"__float__": "inf"}` / `nan` / `-inf`; the public Rust projection uses
   a different `$special_float` envelope.
3. Python compact `json.dumps` uses scientific notation below `1e-4` and at
   or above `1e16`, with a two-digit exponent. `serde_json` uses different
   fixed/scientific thresholds and exponent spelling.

## Port

`config_validate_v1.rs` now carries scalar-origin metadata through schema
calls and direct defaults, and writes the fingerprint with a bounded,
lane-local canonical writer. The writer:

- sorts object keys at every level;
- preserves source integer versus floating scalar spelling;
- normalizes the public special-float envelope to the pinned sentinel;
- matches Python compact JSON escaping, including non-ASCII surrogate pairs;
- matches Python fixed/scientific float thresholds and padded exponents.

The canonical payload has an explicit 16 MiB checked byte cap, including
per-character escaping and UTF-16 surrogate-pair expansion. Materialized
string/numeric storage and cumulative default-map copy inputs are bounded
before cloning. Matrix elements use the same recursive special-float
projection as scalar/vector values, and every derived core scalar updates its
origin marker so an integer source cannot leak through a derived float.

The public materialized JSON remains unchanged. Only the digest boundary uses
the canonical writer; no COM runtime behavior or new public API is introduced.

## Verification

Focused Rust tests cover integer/float distinction, special-float mapping,
float threshold formatting, nested key ordering, control characters, Unicode
escaping, byte-budget rejection, matrix non-finite values, and an XLSX
integer-source-to-derived-float path. The local fixture replay after the fix
produced the pinned fingerprint
`d6963c122533d58273e4ebf3224bade1dc38b040f740c1cd92d4c9727e4483dc`.
That local run used the uncommitted working tree and is not immutable evidence.
The existing formal COM-01 artifacts are intentionally untouched. A new
candidate preparation commit followed by the existing two-stage immutable
replay must establish the replacement evidence.

Commands completed in this working tree:

- `cargo test --manifest-path crates/sipi-agent-com-direct/Cargo.toml --lib`
- `cargo test --manifest-path crates/sipi-agent-com-direct/Cargo.toml --all-targets --offline`
- `cargo check --manifest-path crates/sipi-agent-com-direct/Cargo.toml --lib --offline`
- `cargo clippy --manifest-path crates/sipi-agent-com-direct/Cargo.toml --all-targets --offline -- -D warnings`
- `cargo fmt --manifest-path crates/sipi-agent-com-direct/Cargo.toml -- --check`

No claim is made here for complete COM runtime parity, all override branches,
or acceptance/release status.
