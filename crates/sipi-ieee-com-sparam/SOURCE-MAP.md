# Selected IEEE 802-COM Source Map

This crate is a source-specific BSD-3-Clause direct port, not an Agent-COM or
MATLAB import.

- Upstream repository: `https://opensource.ieee.org/802-com/com_code.git`
- Commit: `d4ecd4597a98782887933b5df4c4796da2474195`
- Source: `src/interp_Sparam.m`
- Git blob: `85b52ff25dbb5bb91f032a03d7cdd311e33af432`
- SHA-256: `259762276a3711eb6e9186993ae1cf38b9cb60d4819f263dc7770788a7f90e27`
- License: BSD-3-Clause; full notice: `NOTICE-IEEE-802-COM.md`

`src/interp_sparam_v1.rs` ports only the source function's magnitude setup,
phase unwrap/anti-causal reject, `linear_trend_to_DC_log_trend_to_inf`, and
`trend_and_shift_to_DC` branches. The Rust file fixes those branches as the
P3C policy and rejects every other branch, debug bypass, and undefined source
branch. It does not port `s21_to_impulse_DC.m` or
`calculate_delay_CausalityEnforcement.m`.
