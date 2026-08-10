# P4A Input/TYP Static Comparator V1

## Roles

The compare gate has three isolated roles. An oracle-only Python orchestrator
retrieves the pinned external asset into two fresh temporary roots. Its raw
observer parses only the selected Input/TYP clamp rows and evaluates the six
charter probes. A test-only Rust runner reads one temporary request and calls
the product structural parser, selected decoder, and DC evaluator. The product
library remains in-memory and has no URL, file, asset, or oracle dependency.

## Binding

Each root must verify the canonical HTTPS `ibis.org` URL, exact byte length and
SHA-256, selector UTF-8 SHA-256, charter SHA-256, exactly six finite f64le
probes, and contained temporary paths. The raw selector spelling and every
external table remain temporary. The runner rejects missing, duplicate, extra,
escaping, malformed, or pre-existing output paths.

## Table Identity

Both roles compute `sipi.ibis.dc-clamp-table.v1` as SHA-256 over the domain
tag, each ordered label (`gnd`, then `power`), row count, and big-endian IEEE
754 bit patterns for every voltage/current pair. The report retains only this
fingerprint, never a row or selector spelling.

## Comparison

The raw observer and product table fingerprints must match exactly. Each of
the six probes must be in-domain with an exact voltage alignment and zero DC
capacitive current. Ground, power, and total current pass only when
`abs(a-b) <= 1e-12 A + 1e-9 * max(abs(a), abs(b))`. Two fresh roots must also
match asset identity, selector digest, table fingerprint, raw observation hash,
and product result hash. Any download, parser, provenance, runner, partial
output, or numeric mismatch rejects the gate.

## Custody And Non-Claims

The machine-readable report is written only to an operator-selected external
path and contains hashes, tool identities, statuses, and aggregate errors. It
does not contain asset text, selector spelling, table rows, probe arrays, or
absolute paths. This gate covers only the selected Input/TYP static clamp
profile; it does not claim general IBIS parsing, package, PVT, V-T, ramp, AMI,
terminal-network, or release behavior.
