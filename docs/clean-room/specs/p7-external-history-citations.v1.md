# P7 External History Citations v1

P7 release-publication documents may cite historical evidence only with the
versioned `history-ref:<alias>@<full-immutable-hash>` marker. Canonical origins
remain in the non-rendered registry; rendered documents expose only alias and
full object hash.

The verifier scopes this rule only to the registry's declared P7 publication
documents. It does not claim to cleanse older repository documentation. Every
entry is `hash_reference_only` and `product_material_status: prohibited`; it
cannot mirror, migrate, redistribute, or promote external source material.

The registry accepts only an exact HTTPS GitHub repository origin spelling and
the declared documents use lexical `docs/baselines/...` paths. File URIs,
Windows or Unix absolute paths, traversal, backslashes, mutable references,
and source paths are rejected.
