# Independent Audit: P3C-01c external ADS PRBS9 reference attempt

审计对象：P3C-01c 未提交的 external ADS ideal-load reference attempt。审计只确认观察、custody 与 fail-closed gate；不将 ADS 运行误报为 P3C acceptance、P4B AMI admission 或 release promotion。

| Check | Result | Evidence |
| --- | --- | --- |
| 外部 ADS 运行可重复 | pass | 两次 fresh external custody 的 canonical payload 与第三周期 hash 相同；本轮 runner 边界修复后第三次实跑仍得到 `5ec5211a...e726` 与 `402596d9...d31c` |
| 外部波形未进入仓库 | pass | verifier 将 source、observation report、canonical payload 与 third-period payload 的 hash 同 tracked-file hash 集合交叉比对 |
| PRBS9 / S4P / ideal-load topology 受限 | pass | runner 固定 511-bit explicit `PRBSsrc` sequence、四端口 Touchstone 与两路 50-ohm load，并静态拒绝 AMI、IBIS、DLL、GetWave 与 CTSPCIE token |
| rectangular-NRZ contract | rejected as required | ADS `PRBSsrc` 将请求的 zero rise/fall clamp 为 `100 as`；baseline 状态固定为 `external_ads_runtime_observed_reference_contract_rejected` |
| P4B / release gate | pass | P4B 仍为 worker-blocked；P3C contract 的 external observation/runtime 仍 false；release compare 仍为 `specified` 且保留 `metric_profile_semantics_not_implemented` |

OpenCode 只读审计初次结论为 `0 P1 / 0 P2`，并提出两项 P3：runner path 注入面，以及 P4B/release cross-file negative branch 未直接测试。修复后复核为 `0 P1 / 0 P2`：所有 ADS 路径均通过 `SIPI_*` 环境变量传入固定 Python code string，`run-id` 限制为 `[A-Za-z0-9_-]+`；新增 P4B/release drift 与 runner boundary tests。

已执行并通过：

```text
python -B tools/test_run_p3c_external_ads_prbs9_reference.py
python -B tools/test_verify_p3c_external_ads_prbs9_reference_attempt.py
python -B tools/verify_p3c_external_ads_prbs9_reference_attempt.py
python -B tools/verify_p3c_prbs9_waveform_jitter_contract.py
python -B tools/test_verify_p3c_prbs9_waveform_jitter_contract.py
python -B tools/verify_clean_room_register.py
python -B tools/test_clean_room_register.py
python -B tools/test_verify_release_capability_publication.py
```

本审计的结论是 observation 与拒绝门一致，不改变当前 blockers：source-edge floor owner disposition、accepted receiver stage 与 statistical-eye contour semantics。
