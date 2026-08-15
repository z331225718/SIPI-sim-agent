# P7 Compiled License-Metadata Normalization v1

This external-only transform consumes only the hash-bound P7-07c actual-build
closure report. It preserves package identity, source kind, literal Cargo
metadata strings, and bounded license-material identities without parsing or
normalizing license expressions.

Its records are classified solely as `declared_string_unparsed`,
`license_file_declared`, `workspace_inherited_declared_unresolved`,
`metadata_absent`, or `conflicting_or_unbound`. A declared `license-file`
without an exact bounded-material path is an `observer_material_coverage_gap`.
The 07c report did not record a license-inheritance source marker, so a null
workspace license value is not inferred to be inherited; it remains
`conflicting_or_unbound`.

The transform must not fetch data, inspect source/cache paths, rewrite SPDX-like
text, infer NOTICE obligations, produce an SBOM, update the license manifest,
or approve any dependency, first-party path, or release gate.
