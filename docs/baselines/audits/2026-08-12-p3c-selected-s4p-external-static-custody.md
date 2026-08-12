# Independent Audit: P3C Selected-S4P External Static Custody v2

审计对象：P3C-04i v2 external static-custody observation、其 hash-only evidence
和 source-drift verifier。Orca OpenCode 复核结论为 `0 P1 / 0 P2`；首轮发现的
report CRLF/runner stdout-stderr 非确定性已在提交前修正。

| Check | Result |
| --- | --- |
| fresh custody | pass: clean archive 在两个独立 temporary ArtifactRoot 中分别 materialize、seal、admit；manifest identities 不同，record count 均为 2002 |
| source identity | pass: fixed source length/SHA-256 在每次 stage 前后重验；failure、cleanup 失败或 manifest/source drift 均 fail-closed |
| report custody | pass: source bytes、temporary roots、absolute paths 和 detailed report 均留在 worktree 外；仓库仅绑定 1839-byte LF-canonical report digest 与 aggregate facts |
| repeatability | pass: observer 改为 ASCII `write_bytes` 且排除 cargo stdout/stderr 路径噪声；reconstructed report hash 与 evidence 一致 |
| current-source binding | pass: verifier 用当前 Git archive bytes 而非 Windows checkout line endings 重建受测 product inventory，相关 source drift 会拒绝 current evidence |
| gate preservation | pass: 仅提升 selected external static custody/admission；fit、stepping、waveform/reference/receiver、P4B 和 release 仍为 false/blocked |
| custody | pass: `uv.lock` 未触碰；product-boundary 与 license manifest 同步暂存 |

已执行并通过：

```text
python -B tools/observe_p3c_sealed_selected_s4p_custody.py --source <external> --report <external> --cargo <external>
python -B tools/verify_p3c_selected_s4p_external_static_custody_evidence.py
python -B tools/test_verify_p3c_selected_s4p_external_static_custody_evidence.py
python -B tools/test_observe_p3c_sealed_selected_s4p_custody.py
python -B tools/verify_clean_room_register.py
python -B tools/test_verify_release_capability_publication.py
```

下一步是将此 exact admitted static transfer 接入已有 real-constrained fixed-pole
fit，并先单独观察 fit admission；不得在该步直接进入 analytic stepping 或 candidate
waveform。
