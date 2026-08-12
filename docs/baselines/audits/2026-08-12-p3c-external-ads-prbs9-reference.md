# Independent Audit: P3C-01d External ADS PRBS9 Reference

审计对象：P3C-01d external ADS oracle reference。该 evidence 接纳的仅是 v2 contract 下的 external reference observation；不改写 v1 rejected attempt，也不将 oracle observation 误报为 product acceptance。

| Check | Result | Evidence |
| --- | --- | --- |
| v1 rejected attempt immutable | pass | raw baseline SHA-256 与 rejected status/match/reference flags 均由 verifier 固定 |
| clean archive binding | pass | commit `e167c57...`、tree `d8c8b7...` 与 `git archive` 中 runner bytes hash 逐项绑定 |
| v2 fresh ADS runs | pass | 两次 fresh run manifest、canonical payload 与第三周期 payload identity 一致；显式 rise/fall 均为 `100 as` |
| historical waveform rebind | pass | v2 fresh canonical/third-period hash 与 v1 historical waveform hashes 精确相同，且保留 v1 rejected context |
| custody | pass | external report、manifests、source、payload 和 third-period hash 均不得进入 tracked files |
| non-promotion gates | pass | candidate metric evaluation、receiver, acceptance, P4B AMI, product runtime, release compare 与 release ledger 均仍 fail-closed |

OpenCode 只读审计结论为 `0 P1 / 0 P2`。审计确认 v1 attempt 的 `reference_contract_match: false` 和 clamp mismatch 保持原状；新 v2 reference 的 true flags 仅属于 external ADS oracle lane。`uv.lock` 是用户已有未提交改动，未纳入本切片。

已执行并通过：

```text
python -B tools/verify_p3c_external_ads_prbs9_reference.py
python -B tools/test_verify_p3c_external_ads_prbs9_reference.py
python -B tools/verify_p3c_prbs9_waveform_jitter_contract_v2.py
python -B tools/test_verify_p3c_prbs9_waveform_jitter_contract_v2.py
python -B tools/verify_p3c_external_ads_prbs9_reference_attempt.py
python -B tools/test_verify_p3c_external_ads_prbs9_reference_attempt.py
python -B tools/verify_clean_room_register.py
python -B tools/test_clean_room_register.py
```

剩余 blockers 仅为真实的 product-side work：candidate waveform/eye/jitter comparator、accepted receiver stage 与 statistical-eye contour semantics。
