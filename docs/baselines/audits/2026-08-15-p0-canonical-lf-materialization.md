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

The clean-room register also binds the content bytes of its independent
specifications. Those specifications use the same canonical LF checkout rule;
otherwise a default Windows checkout changes the bound source bytes before
verification.

The independent specification template is separately bound by the register
and is likewise fixed to LF.

The inventory writer also emits LF explicitly. A host-native text write would
otherwise recreate a CRLF digest even when the input worktree was canonical.
