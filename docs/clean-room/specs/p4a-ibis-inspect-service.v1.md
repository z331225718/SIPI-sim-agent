# P4A IBIS Inspect Service v1

## Scope

This specification defines a product-owned, in-memory inspection service for
one JSON-provided UTF-8 text value. The current structural parser accepts only
its bounded ASCII structural subset; non-ASCII text is rejected by that parser.

The service runs exactly the bounded structural parser followed by the typed
semantic envelope. It returns the input UTF-8 byte length and SHA-256 identity,
the declared lexical version token, and component, model, and block counts.

## Response Boundary

Every successful response states that electrical behavior and external-profile
acceptance are `not_evaluated`. It also identifies the P4A IBIS conformance
matrix by its stable ID. It does not return text, token spelling, declaration
names, table values, model selectors, file paths, URLs, external asset identity,
or any electrical calculation.

## Process Contract

The CLI accepts only `sipi ibis inspect --stdin` with one
`sipi.ibis.inspect.request.v1` JSON document. The source is an object containing
`encoding: "utf-8"` and `text`. It has no binary, base64, file, URL, profile, or
evaluation field. Unknown fields and malformed, empty, or structurally rejected
input fail closed. The existing CLI response, diagnostic, and exit-code contract
remains the sole process authority.

## Non-Goals

This service does not select or decode an IBIS profile, evaluate clamps or
capacitance, solve an endpoint network, access an external asset, invoke an
oracle, support AMI, or change the default simulation route.
