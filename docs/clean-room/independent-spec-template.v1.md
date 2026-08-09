# Independent Behavior Specification Template v1

This template is a project-authored formatting aid. It contains no legacy
source, oracle fixture, vendor model, or numerical golden data.

An observation/specification author records only the public behavior needed by
an implementation: versioned input and output contracts, units, state
transitions, negative cases, approved comparison tolerance, provenance, and
non-claims. It must not include copied source text, translated control flow,
or recognizable implementation detail from prohibited material.

Each completed specification must name its clean-room scope, list its material
ancestors, and be sealed before an implementer consumes it. The Rust
implementation is independently designed from the registry allowlist.
