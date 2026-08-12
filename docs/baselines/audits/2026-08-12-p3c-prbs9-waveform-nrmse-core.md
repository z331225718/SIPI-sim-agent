# Independent Audit: P3C-02b PRBS9 Waveform NRMSE Core

审计对象：`sipi-compare` 的 P3C PRBS9 v2 strict-grid waveform NRMSE core。该切片只实施当前完全确定的 waveform formula，不把未冻结的 sampled-eye 或 TIE 离散边界伪装为实现。

| Check | Result | Evidence |
| --- | --- | --- |
| profile identity and grid | pass | product constants bind v2 contract hash, 49056 total samples and third-period `[32704,49056)` |
| formula and numeric rejection | pass | scaled sum-of-squares; finite input, zero reference norm and subtraction/ratio overflow all fail closed |
| no hidden transform | pass | sample shift, DC offset, gain and polarity change all remain numeric failures |
| boundary and non-claims | pass | no CLI/file/artifact/ADS/AMI access; external binding remains `not_evaluated`; eye/TIE remain `not_implemented` |
| release gates | pass | release compare row remains `specified` with `metric_profile_semantics_not_implemented` |

OpenCode 只读审计结论为 `0 P1 / 0 P2`。首轮 P3 指出 implementation binding branch 没有直接负测；已抽出 `implementation_source` 并用 mock 直接触发 `implementation_binding_drift`，复核仍为 `0 P1 / 0 P2`。

已执行并通过：

```text
python -B tools/verify_p3c_prbs9_waveform_nrmse_core.py
python -B tools/test_verify_p3c_prbs9_waveform_nrmse_core.py
cargo test -p sipi-compare
cargo clippy -p sipi-compare --all-targets -- -D warnings
python -B tools/verify_clean_room_register.py
python -B tools/test_clean_room_register.py
```

仍未完成：profile-specific CLI transport、external reference binding、sampled-eye/TIE discrete semantics、accepted receiver 与 statistical contour。
