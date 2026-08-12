# Independent Audit: P3C-04b ADS Transient Policy Surface Observation

审计对象：P3C external ADS transient-convolution policy-surface 的 hash-only
观察与 fail-closed evidence gate。Orca OpenCode 只读审计首轮发现一个 P2：
custody-leak guard 未覆盖四份 ADS HTML 的 hash。修复后同一审查员复核，结论为
`0 P1 / 0 P2`。

| Check | Result |
| --- | --- |
| external custody | pass: S4P、两次 hash-only report 与四份 ADS documentation 都不入库；六个 external payload hash 都进入 leak guard |
| runtime isolation | pass: observer 只构造内存 netlist 并读取受限 help allowlist；不启动 ADS，不加载 AMI/IBIS/DLL |
| policy honesty | pass: ADS adaptive behavior 仅为外部 observation；频率 grid、max frequency、impulse truncation、interpolation、causalization/passivity 和 startup/strobe product policy 继续 missing |
| gate preservation | pass: static bench 仍无 time-domain executor；candidate/reference/receiver/P4B/release 都保持 false/blocked |
| fail closed | pass: report/source/runner/document drift、遗漏 unresolved policy 或 admission promotion 均拒绝；custody test 锁定全部 six external hashes |

已执行并通过：

```text
python -B tools/observe_p3c_ads_transient_policy_surface.py ... (two fresh external reports, identical SHA-256)
python -B tools/verify_p3c_ads_transient_policy_surface_observation.py
python -B tools/test_verify_p3c_ads_transient_policy_surface_observation.py
python -B tools/verify_clean_room_register.py
python -B tools/verify_product_boundary.py
python -B tools/test_verify_release_capability_publication.py
cargo test --workspace --locked
```

该观察不是 ADS-parity executor 或 candidate acceptance。下一步仍需要 owner 冻结一个
确定性的产品侧时域 network policy，才可讨论 P3C candidate waveform generation。
