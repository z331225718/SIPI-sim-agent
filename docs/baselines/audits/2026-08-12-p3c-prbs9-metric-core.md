# Independent Audit: P3C-02c PRBS9 Sampled-Eye and TIE Metric Core

审计对象：`sipi-compare` 的 owner-approved PRBS9 v2 strict-grid
waveform, sampled-eye and crossing-time TIE formula core。该切片不读取
ADS、AMI、DLL 或 oracle，也不形成 candidate、receiver、profile 或 release
acceptance。

| Check | Result | Evidence |
| --- | --- | --- |
| PRBS identity | pass | Fibonacci `x9+x5+1`、seed `0x1a5`、pre-shift output 和 511-bit SHA-256 均由 unit test 绑定 v2 contract |
| fixed grid and NRMSE | pass | only `[32704,49056)` participates; finite/zero norm/overflow remain fail-closed |
| sampled eye | pass | current-UI PRBS partition, `min(high)-max(low)`, phase-16 non-wrapping positive-bin width, no interpolation |
| crossing TIE | pass | matching ideal transition only; directional endpoint ownership, half-open half-UI window, linear interpolation, raw RMS without mean removal |
| structural rejection | pass | zero plateau and missing/multiple crossings are errors, not numerical mismatches |
| historical/source drift | pass | NRMSE-only v1 baseline stays immutable; its verifier reports `historical_source_status=source_drift`; v2 is a separate current record |
| release and AMI gates | pass | all admission booleans remain false; release `compare` stays `specified` with `metric_profile_semantics_not_implemented`; P4B is untouched |

OpenCode 只读审计结论：`0 P1 / 0 P2`。

已执行并通过：

```text
cargo test -p sipi-compare
cargo clippy -p sipi-compare -- -D warnings
python -B tools/verify_p3c_prbs9_waveform_nrmse_core.py
python -B tools/test_verify_p3c_prbs9_waveform_nrmse_core.py
python -B tools/verify_p3c_prbs9_metric_core_v2.py
python -B tools/test_verify_p3c_prbs9_metric_core_v2.py
python -B tools/verify_clean_room_register.py
python -B tools/verify_product_boundary.py
```

仍未完成：profile-specific CLI/artifact transport、external reference binding、candidate comparison、accepted receiver stage 和 statistical-eye contour。
