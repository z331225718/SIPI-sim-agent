# Independent Audit: P3C PRBS9 Contract v2 Source-Edge Amendment

审计对象：用户授权的 ADS `PRBSsrc` 100 as source-edge amendment。v1 contract 和 v1 rejected attempt 均作为历史证据保留，不回写、不改标、不提升其结论。

| Check | Result | Evidence |
| --- | --- | --- |
| v1 historical identity | pass | v2 verifier 绑定 v1 raw content SHA-256 `7c55086a...1751` |
| amendment scope | pass | semantic projection 仅排除 version/authority/supersedes 与 source transition fields；PRBS、window、metric 与 tolerance 必须逐项相同 |
| ADS edge literal | pass | v2 exact freeze 为 `ads_prbssrc`, `EdgeShape=0`, equal rise/fall `1e-16 s`, transition reference `0.0` |
| runtime/release boundaries | pass | v2 admission 仍全部 false；P4B worker gate 与 release compare blocker 仍由 verifier锁定 |

OpenCode 只读审计结论为 `0 P1 / 0 P2`。首轮指出 `unauthorized_semantic_diff` 没有直接测试；已用 mocked digest 绕过全文 digest guard 并直接变异 waveform RMS tolerance，复核确认精确触达 projection guard，仍为 `0 P1 / 0 P2`。

已执行并通过：

```text
python -B tools/verify_p3c_prbs9_waveform_jitter_contract_v2.py
python -B tools/test_verify_p3c_prbs9_waveform_jitter_contract_v2.py
python -B tools/test_run_p3c_external_ads_prbs9_reference.py
python -B tools/verify_p3c_prbs9_waveform_jitter_contract.py
python -B tools/test_verify_p3c_prbs9_waveform_jitter_contract.py
python -B tools/verify_p3c_external_ads_prbs9_reference_attempt.py
python -B tools/test_verify_p3c_external_ads_prbs9_reference_attempt.py
python -B tools/verify_clean_room_register.py
python -B tools/test_clean_room_register.py
```

此 amendment 本身不是 external reference evidence。后续仍必须以 clean archive 中显式 `100 as` 的 runner 执行两次 fresh ADS run，并将其与 v2 contract 绑定。
