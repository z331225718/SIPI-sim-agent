# P4A IBIS Structural Parser Foundation v1

## Scope

`sipi-ibis` accepts bounded ASCII bytes and creates a structural document of
physical lines, comment-stripped records, bracketed keyword spelling, and
whitespace-delimited payload tokens. The parser retains record order and
source byte/line/column spans. It does not read files or run a CLI command.

## Admission Rules

The caller supplies nonzero limits for input bytes, physical-line bytes,
physical-line count, and record count. The parser rejects a limit breach, NUL,
non-ASCII byte, bare carriage return, malformed/empty/unclosed bracketed
keyword, or an opaque data record with unbalanced brackets. Balanced brackets
inside an opaque data token are retained without assigning semantic meaning.
Any rejection returns only a
stable diagnostic and no partial document.

Both LF and CRLF are accepted and retained as source spelling. A vertical-bar
comment begins at the first bar in a physical line. Empty and comment-only
lines retain physical-line provenance but create no record.

## Deliberate Semantic Boundary

Every bracketed keyword, including an unknown keyword, is structural only.
This foundation defines no required headers, IBIS-version allowlist, duplicate
rule, model/component relationship, unit conversion, numeric parsing, table
interpolation, clamp/package/PVT behavior, Algorithmic Model semantics, or
AMI composition. Those rules require later independent semantic contracts.

## Test Boundary

Tests use only project-authored synthetic ASCII snippets. No public-standard
body, external IBIS file, candidate asset, or legacy parser output is used as
an implementation fixture or expected result.

## Non-Claims

This is not a complete IBIS parser and does not establish electrical behavior,
standard conformance, external asset compatibility, AMI support, or a public
runtime capability.
