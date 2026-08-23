# Agent-COM Upstream Runtime Oracle v2

- Scope is upstream-only observation for COM-02 and COM-04.
- Source is Agent-COM commit `5272ffe74702cd585054d975559b06f8afae7b6e`, tree `7094ab6e84989b218730c52432c70da10261f8ea`, materialized from the pinned Git archive.
- The portable Python leaves `constrained_mmse`, `force_rx_ffe`, and `calibrate_receiver_noise` executed twice per row with identical numeric payloads.
- The full `agent_com.api.run_com` entrypoint was attempted twice per row under the fixed 15 second gate with the archived workbook and synthetic THRU S4P fixture. It blocked in the r4.80 non-MMSE search/evaluation budget; this is not full-run numeric parity.
- Reports bind path-free Python/uv/toolchain/runtime/package identities, relative fixture hashes, runner/aggregate/verifier/mutation/audit hashes, archive containment, 64-hex nonces, and cross-run report/aggregate hashes.
- No candidate Rust binary, candidate parity, release, or promotion claim is made.
