# Independent Audit: P3C Selected-S4P Real-Constrained Fit Harness

审计对象：P3C-04j 的 clean-archive external observation harness。Orca OpenCode
只读审计结论为 `0 P1 / 0 P2`。

| Check | Result |
| --- | --- |
| fresh custody | pass: 每次 run 创建独立 temporary ArtifactRoot，artifact id/manifest 不能复用 |
| source identity | pass: source 在每次 stage 前后和 observer 全程前后均以 fixed length/SHA-256 重验 |
| admission and fit | pass: 仅经 `admit_selected_p3c_sealed_s4p_v2` 获得 fixed transfer，再调用已冻结的 real-constrained fit API |
| model identity | pass: canonical digest 绑定 namespace、order 与所有正虚极点/残数的 f64 bit；metrics digest 覆盖三个 admission metrics |
| fail-closed | pass: runner 与 observer 分别验证 exact report shape、hash、order、cleanup 与双 run 一致性；任何异常拒绝 |
| gate preservation | pass: 无 analytic stepping、waveform、ADS/AMI/P4B 或 release 调用或提升 |
| custody | pass: `uv.lock` 未触碰；source bytes、temporary roots、详细 report 和绝对路径均不进入工作树 |

已执行并通过：

```text
cargo test -p sipi-p3c --locked
cargo test -p sipi-channel --locked
python -m py_compile tools/observe_p3c_sealed_selected_s4p_real_constrained_fit.py
```

下一步只能在 clean archive 上对 exact external source 运行两次 observer；fit 不通过时必须记录
rejected observation，不能放宽 order 或 admission thresholds。
