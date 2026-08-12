# Independent Audit: P3C-04h Sealed Selected-S4P Static Admission

审计对象：P3C-04h 的 sealed selected-S4P static-admission composition、对应
baseline/verifier 与 clean-room scope。Orca OpenCode 只读审计结论为 `0 P1 / 0 P2`。

| Check | Result |
| --- | --- |
| fixed input surface | pass: caller 仅可给 opaque artifact id 与小写 manifest SHA-256；文件名、S4P hash/length、port map、parser limit 均为产品固定常量，且没有 metadata sidecar |
| same-read verification | pass: `consume_exact_verified_v1` 在同次消费中校验 exact manifest/files/payload，再重读 manifest；adapter 对已验证内存 bytes 继续作精确长度与 SHA-256 检查后才解析 |
| filesystem boundary | pass: 拒绝 extra file、symlink/reparse 与 manifest/source drift；明确仅适用于 no-hostile-concurrent-writer root 假设，不夸大为 hostile-filesystem containment |
| static scope | pass: 仅完成 `channel.s4p -> strict parser -> fixed Hdiff reduction`；没有 metadata/拓扑 override、CLI、wire schema、fit、stepping、waveform 或 artifact publication |
| evidence preservation | pass: 合成测试不能构成生产 selected asset 成功；external custody 与 selected external S4P admission 仍为 false，且保留两次 fresh external custody observation blocker |
| gate preservation | pass: real fit invocation、candidate waveform/reference/metric/receiver、P4B/AMI/IBIS/DLL 与 release 均保持 false/blocked |
| custody | pass: `uv.lock` 未触碰 |

已执行并通过：

```text
python -B tools/test_verify_p3c_sealed_selected_s4p_static_admission.py
python -B tools/verify_p3c_sealed_selected_s4p_static_admission.py
python -B tools/verify_clean_room_register.py
python -B tools/test_clean_room_register.py
python -B tools/test_verify_release_capability_publication.py
cargo test -p sipi-p3c --locked
```

后续只有在两个 fresh private artifact roots 对同一 external source 均形成严格
sealed admission 的 hash-only observation 后，才可建立外部 static custody；该证据也
不会自行授权 real fit、analytic stepping 或 candidate waveform。
