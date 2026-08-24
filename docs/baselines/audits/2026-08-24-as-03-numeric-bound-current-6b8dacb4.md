# AS-03 governing-corpus current replay audit

This successor is bound to candidate commit `6b8dacb434c1b95571b45e0f07a15fe2e997b012`, tree `5cf877e3da35f387f0a720a081c87214a2d6ca2b`, clean candidate archive SHA256 `59becc6fbfede8dce7019ec1e57c7b8fb98c4682eb85894176050740e6df6cc4`, and the pinned Agent-Spice upstream commit `2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5`, tree `b6bde97128030d6cea0d68b2f0a35d807be8c402`, archive SHA256 `a5014b006e703b2224382d5c7622f1a14eab82acd9ca2151df8245ab51945144`, MIT.

The two reports were made from two explicit, external, create-new fresh roots with offline cargo and pre/post-identical cargo/rustc/python identities. They use the exact governing fixture SHA256 `4da06c257a0f0108e4391d65f894b6bb0d62a24a8f00f82f0f0734e061f5de70` and exact AS-03 args/profile. Run 01 is `as03-6b8dacb4-fresh-01`, nonce `d2701aec1dea54237ac26687a4923f43903c6cd57711651a2de9ba08fb9d483f`, report path `docs/baselines/as-03-numeric-bound-current-6b8dacb4-run-01.json`, SHA256 `bca4296f296fe89740f2e526f1a301f688a55699af0a1f889e781e1ce3ae9df3`. Run 02 is `as03-6b8dacb4-fresh-02`, nonce `ca89b480432044e0813fb9450cf887e9e983bb263ff04f626314ce25fc5797f0`, report path `docs/baselines/as-03-numeric-bound-current-6b8dacb4-run-02.json`, SHA256 `f598d5f9ed284f0e8eac79b39eb7d71c7d61e44462e6087b5560d06bfc895b80`.

Both candidate RMS values are `0.025857844795922492`; upstream is `0.025857844795922482`. Both candidate mean RMS values are `0.012928922397961246`; upstream is `0.012928922397961241`. The historical v2 large candidate mismatch (`0.04390770265061283` versus upstream `0.02585784479592245`) is absent on this governing fixture. The residual approximately `1e-17` difference remains numeric mismatch open. global parity remains open; no acceptance tolerance is claimed, and this does not close AS-03.

The source map and NOTICE remain bound to the pinned Y-parameter, rational-LFT, Z-metric, and KYP paths. SI-channel S-parameter fitting is explicitly out of scope. No product or release promotion is made.

Current manifest path: `docs/baselines/as-03-fit-yparam-numeric-bound-current-6b8dacb4.v1.yaml`; core SHA256: `f9a197f80546eae6e9fde7c4f8c1f3906c6d6a3a155616164b1b2cc4c3d96f2f`
Legacy v2 manifest path: `docs/baselines/as-03-fit-yparam-numeric-bound-v2.yaml`; SHA256: `0ce8d64e0fa3dd8ec31a9073b0127782826106c641261984afc5932b50f669aa`
Legacy v2 aggregate path: `docs/baselines/as-03-numeric-bound-v2-aggregate.json`; SHA256: `730b7a34bef04be54be8fe76138cd3d7c07fae8602ee106daab1d0784f50aeb2`
Legacy v2 runner path: `tools/run_as_02_03_numeric_bound_v2.py`; SHA256: `dc5d52a6ee00c634d1a203dfb6af117cc5b3e25b5c8cdc2133ef383c09aa0bcc`; bytes: `9881`
Legacy v2 uses the same fixture bytes and AS-03 args as the current governing profile; the historical metrics remain separately bound above.
Source map path: `docs/baselines/as-03-fit-yparam-source-map.v1.yaml`; SHA256: `8b8b2a822690dcda4e2d711aaa0425bcb03bbecca697ef0ac712ec444526e815`
NOTICE path: `crates/sipi-agent-spice-direct/NOTICE-AGENT-SPICE-AS-03.md`; SHA256: `0d8cdee1b93f8e8ea51df76653233fea5c8a8e3d5f32b15d276c23c0686b908a`

Aggregate path: `docs/baselines/as-03-numeric-bound-current-6b8dacb4-aggregate.json`; SHA256: `49f78eff9f04bf522fb0b2a32119952e2529a6b4ef0a605e7945b852e03260a8`

Harness: runner `tools/run_as_02_03_numeric_bound_v3.py` SHA256 `11fb2258679fbed702d7e0a12af447710eb4e294a1b5965b37c54f021f46729e`; aggregator `tools/aggregate_as_02_03_numeric_bound_v3.py` SHA256 `36f7e9ba5bd8fbcad6542a4d8f0053a293fe16137058652ef081c1650a2b09ce`; verifier `tools/verify_as_03_numeric_bound_current_6b8dacb4.py` SHA256 `526de14882453e7c0cc78a933e03415ce68a84527bf6c8c47a00255bb9f7fd50`; mutation tests `tools/test_verify_as_03_numeric_bound_current_6b8dacb4.py` SHA256 `8f284eea40ebc208ec4db73beb467fbbc7a8edafae04445bb7784795967359df`.
