# Independent Audit: P3C-04c ADS Explicit-Convolution Sweep Observation

审计对象：P3C external ADS explicit-convolution grid sweep 的 hash-only
observation、其 evidence verifier 与 clean-room gate。Orca OpenCode 只读审计
结论为 `0 P1 / 0 P2`。

| Check | Result |
| --- | --- |
| policy honesty | pass: `N=2048` 只记录为能复现 external adaptive oracle 的 ADS controller candidate；未将 ADS proprietary convolution 宣称为产品算法或 executor |
| external custody | pass: 报告只保留 logical identity、长度与 hash；report、S4P 与十二个 canonical/third-period waveform payload hash 都进入 tracked-file leak guard |
| source drift | pass: S4P、reference runner 与 sweep observer 均由 exact SHA-256 绑定；任何 drift 都 fail closed |
| runtime isolation | pass: observer 只运行授权的 external ADS ideal-load bench；不运行 product code，不加载 AMI/IBIS/DLL |
| gate preservation | pass: product policy/executor、candidate waveform、external reference binding、receiver、P4B 与 release 都保持 false/blocked |
| selection integrity | pass: allowlisted six-grid sweep 使用 strict-index third-period NRMSE、禁止 alignment；只有 `N=2048` 的 NRMSE 为零，其余均超过 1% screening gate |

已执行并通过：

```text
python -B tools/test_observe_p3c_ads_explicit_convolution_sweep.py
python -B tools/verify_p3c_ads_explicit_convolution_sweep_observation.py
python -B tools/test_verify_p3c_ads_explicit_convolution_sweep_observation.py
python -B tools/verify_clean_room_register.py
python -B tools/test_clean_room_register.py
python -B tools/verify_product_boundary.py
python -B tools/test_verify_release_capability_publication.py
cargo test --workspace --locked
```

该观察不能替代产品侧 S4P-to-waveform policy。input-to-impulse-grid、output-strobe、
interpolation/extrapolation 与 causality/passivity 的确定性产品语义仍须独立冻结。
