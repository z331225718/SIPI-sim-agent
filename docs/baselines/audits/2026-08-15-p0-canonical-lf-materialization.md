# P0 Canonical LF Materialization

P7 composition preflight exposed an EOL split before candidate execution.
With the host Git default `core.autocrlf=true`, a normal detached worktree
rendered some byte-hashed root governance files as CRLF while
`license-manifest.v1.yaml` remained LF. A canonical `git archive` uses the
Git blob bytes, so no clean checkout representation could satisfy all three
P0 byte-identity verifiers.

This record authorizes no normalization in a verifier. Instead,
`.gitattributes` makes the named governance files LF at checkout. The
follow-up inventory regeneration and manifest rebinding must use those
canonical bytes. The earlier P7 attempts remain historical materialization
observations; this is not a product-source, license, or release promotion.
