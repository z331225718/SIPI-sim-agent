# P4B AMI Text Structural Foundation v1

## Scope

`sipi-ami-text` accepts one bounded UTF-8 text stream and produces an ordered
structural tree of parenthesized forms, atoms, quoted text, comments, and
source spans. This is a product-owned structural grammar: it recognizes no
AMI keyword, parameter, default, model, unit, or DLL behavior.

## Structural Grammar

Outside quoted text, space, tab, LF, CRLF, and a `|` line comment are
ignorable. A document is zero or more top-level parenthesized forms. A form is
an opening parenthesis, zero or more nested forms, atoms, or quoted tokens, and
a closing parenthesis. Atoms stop at whitespace, parentheses, a quote, or a
comment marker. Quoted tokens retain their original spelling, including quote
and escape characters; this layer does not decode escapes.

The parser accepts valid UTF-8 only. NUL, other control characters, bare CR,
unbalanced parentheses, an unterminated quote, an atom outside a form, and all
configured input/depth/node/token limits are rejected. A rejection returns no
partial document.

## Limits And Diagnostics

The caller supplies nonzero maximum input bytes, nesting depth, node count, and
token bytes. Diagnostics have stable codes and byte/line/column spans. Limits
are checked before allocation or recursion can exceed the supplied bound.

## Semantic Boundary

`semantic_validation_status_v1()` is always `RulesUnavailable`. This foundation
does not select an AMI revision or support any reserved/model-specific
parameter, coercion, default, binding, IBIS relationship, Init/GetWave/Close
lifecycle, DLL, file I/O, CLI route, runtime, or external compatibility claim.

## Test Boundary

Tests use only project-authored synthetic text. They do not read a `.ami`
asset, a vendor DLL, existing candidate code, PyBERT, or any oracle fixture.
