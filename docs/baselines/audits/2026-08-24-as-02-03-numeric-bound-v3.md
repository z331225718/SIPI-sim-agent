# AS-02/03 Numeric Bound v3 Audit

This additive bound observation is content-bound to candidate commit `aeb09982f360e73159d1335c6e0dd77d1176e65a`, tree `4d0411d9439bed2ff5410b56f799ac47583bf43a`, and archive SHA256 `272beba9cff45b449cf84c19dfcd026f5d42a3d470cdd18bf38a731b3780f4e0`. The runner content is byte-identical to the candidate commit blob (SHA256 `1acc6d619b37f0ea1139ce4a21117024b723a5bf934b42b927fa6af3670e9c61`), and the aggregator content is byte-identical to its candidate commit blob (SHA256 `d951474d93d2c0cb110ab15ad2a961905d4c067db5b9cff6ddf91b3f96fbbae4`); no execution filesystem path is asserted. Upstream remains pinned to commit `2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5`, tree `b6bde97128030d6cea0d68b2f0a35d807be8c402`, archive SHA256 `a5014b006e703b2224382d5c7622f1a14eab82acd9ca2151df8245ab51945144`.

AS-02 run report SHA256: `d06606d889f4e46693b02348e01a75e9b4265de73e7133218d1bbd6eeb96d3d0`, `fbbb57cf1d5965286304d73c85e671243e48867ff6b834e471f26c0c3c5c24a1`; aggregate SHA256: `f4c63318e35db023db9deb8a762427650accda55f47db9737d7761ce9d9cc37e`.

Aggregate path: `docs/baselines/as-02-numeric-bound-v3-aggregate.json`; SHA256: `f4c63318e35db023db9deb8a762427650accda55f47db9737d7761ce9d9cc37e`.

AS-03 run report SHA256: `0238a66dd3688e20dd0703267d19c3d88a30a4be14420edb7eefb2a5980b7bf8`, `361e61a54fd878eb0da870739932716c2e2ad3113c6b91b66f19574dbee484d3`; aggregate SHA256: `9b2486ad15c52d00a01ebe99bc055284a78be6381d4a86ac52383e0feee88f14`.

Aggregate path: `docs/baselines/as-03-numeric-bound-v3-aggregate.json`; SHA256: `9b2486ad15c52d00a01ebe99bc055284a78be6381d4a86ac52383e0feee88f14`.

AS-02 remains numeric mismatch open: upstream cascade mean RMS `0.08305707108701127`, candidate `0.08227413117673504`; each upstream block RMS `0.06916905397206313`, candidate `0.06748965962552016`. No acceptance tolerance or parity claim is made. AS-03 is numerically equal within the fixed fixture scope: upstream Y RMS `0.02585784479592245`, candidate `0.025857844795922492`; upstream mean RMS `0.012928922397961225`, candidate `0.012928922397961246`. Its `1e-12` comparison is scoped only to this fixture and does not close or promote the global row.

Reports use path-redacted tool identities and clear inherited `RUSTC_WRAPPER` and `RUSTC_WORKSPACE_WRAPPER`. Both workflows have two fresh runs with distinct run IDs, nonces, report hashes, and bound candidate/upstream/toolchain/fixture identities. The evidence is a numeric observation only; AS-02 parity remains open and AS-03 remains scoped parity, with no product capability promotion.
