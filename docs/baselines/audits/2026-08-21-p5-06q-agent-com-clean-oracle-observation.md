# P5-06q Agent-COM clean observation

This record is an additive observation of a pinned, clean Agent-COM checkout.
It does not promote an oracle result to product acceptance and does not close
the P5-06 required COM/ERL/TD-ILN comparison contract.

## Identity and license

- Repository: `https://github.com/z331225718/agent-com.git`
- Commit: `5272ffe74702cd585054d975559b06f8afae7b6e`
- Tree: `7094ab6e84989b218730c52432c70da10261f8ea`
- License: root `LICENSE` is MIT, blob `55aac2e4f8c36a978d315efb02815972579b8293`, content SHA-256 `d0807e4df734f0fadc658f4ea3be7bfe4b81c3e85a2b053b069a23189c6034c2`.
- The selected files are pinned by Git blob OID, byte length, and content SHA-256 in the companion YAML. No generated checkout file is used as authority.

## Exact entry point and input

The clean observation used `load_config(config_path, overrides={'COMPUTE_TDILN': 1})`, then `run_com(config=loaded, channels=ChannelSet(thru), options=RunOptions(loaded.profile, diagnostics=False))`. The profile was `r480`; diagnostics were disabled for the scalar run.

The workbook is the relative Agent-COM input `matlab_src/config_sheets_100G/config_com_ieee8023_93a=3ck_SA_120F_C2C_08_17_2022.xlsx`, 67087 bytes, SHA-256 `e676b3fb3cb3048f80c98deaa8faca1d03c13daa216c6259de26885e715ca925`. The single channel is the relative fixture `fixtures/synthetic/thru_10db_at_26p56ghz.s4p`, 6425196 bytes, SHA-256 `b14a92e7f844608aaee5b4cbd3dfda08d7af48bfedb4526043a0733b8823e584`. Case order and checkpoint identity are not aligned to any product output here.

## Observed output

Two fresh runs were performed outside the product repository. The two external JSON payloads are byte-identical: 51793 bytes and SHA-256 `2aa43d7487d7481a9d4463d7e69e7a397cc5bf30efcfad6cb0239d43f7dfae54` for each run. The first two cases reported `COM_dB` values 6.680468404393122 and 6.8626430506219 dB. `ERL`, `ERL11`, and `ERL22` were `Infinity` in both cases. No scalar `TD_ILN_dB` or `TD_ILN` value was emitted.

The payload exposed `FOM_TDILN=22.36644896404741` and a diagnostics `TdIlnResult` vector, but neither is accepted as the required scalar `TD_ILN_dB`. `ICN_mV`, `FOM_TDILN`, an ILN vector, or any other field is not substituted for `TD_ILN_dB`.

## Boundary

The owner comparison policy is absolute 0.1 dB for `COM_dB`, `ERL_dB`, and `TD_ILN_dB`. This observation does not establish that policy as Agent-COM authority. A valid future comparison must bind the same normalized input, case, stage checkpoint, field identity, and units on both sides, with no alignment or interpolation. Since the scalar TD-ILN value and a complete checkpoint contract are missing, status remains blocked and no acceptance or release claim is made.
