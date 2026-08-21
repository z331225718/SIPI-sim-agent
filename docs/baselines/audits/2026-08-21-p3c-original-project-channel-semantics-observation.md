# P3C 原项目 channel semantics 取证审计

日期：2026-08-21
范围：只读核验原 ADS 工作区、retained ADS custody 与 PyBERT exact revision；不改变 P3C 求解器或验收政策。

## 结论

本轮证据支持的结论只有两点：

1. PRBS9 seed、phase ownership 和 `finite_edge_right_continuous_v2` source-only 观察中，第三周期 interior 15,841 点的 NRMSE bits 为 `0000000000000000`；完整 channel replay 仍为 `0.02911956313297956`。这两个事实不识别、也不排除任何 root cause。
2. 原 ADS/PyBERT 的 interpolation、causality、delay、impulse trimming 和 output-strobe 语义与当前 SIPI policy 不同，但这些差异没有获得迁移授权。没有宣布 waveform root cause，没有接受 waveform、causal FIR、receiver 或 release。

没有执行 alignment、delay sweep、gain/DC/polarity fit、resampling、rational fit、parameter scan 或 tolerance relaxation；same-index compare 与固定 1% limit 保持不变。

## 证据绑定

规范记录为 `docs/baselines/p3c-original-project-channel-semantics-observation.v1.yaml`，verifier 为 `tools/verify_p3c_original_project_channel_semantics_observation.py`。所有外部对象以逻辑路径、byte length 和 SHA-256 绑定，未把 ADS payload、dataset、绝对路径或 waveform array 放进仓库。

### ADS retained custody

- 原工作区逻辑路径：`ADS/MyWorkspace_wrk/data/channel_gen5_highloss.s4p`，1,834,156 bytes，SHA-256 `25c39335ec4294b5110d7eb79ba669fa1d4941e909e41bf972c6666f8f67ea47`。
- retained custody 逻辑根：`sipi-p3c-oob-ref-recovery-43ed3bad301e4be0b70ba6433750024f/ads-runs/ref01`（同一 retained run 的 `ref02` 亦已核验）。`manifest.json` 为 2,479 bytes，SHA-256 `37930afa7f151cd6ca317f17ebb544dfb9c5a56a4a4c455b35f0114dc4fb94f9`，schema 为 `sipi.p3c-external-ads-prbs9-reference-run.v1`，ADS runtime 为 true，product runtime 与 P4B AMI runtime 均为 false。
- `p3c_prbs9.ds` 为 7,107,072 bytes，SHA-256 `1375d8beec33b2688cf4ab305a6a472b9ae0260960b2128e199b760979d12310`。
- `p3c_prbs9_ideal_load.ckt` retained bytes/hash 为 5,254 / `c6d3df30e2f23dd9181426b2d834bab4cb5990d19a1e48a2b968eb9e79369765`；manifest declared LF bytes/hash 为 5,246 / `2784e9e8d42c7ecdc3459b79a5f9cd79cc86131f839c86b1658e8d40b1d9aaf9`，差异仅 line ending。关键 netlist facts：`Mode=2`、register length 9、seed `0x1a5`、32 Gb/s、edge floor `1e-16 s`、max time step `9.765625e-13 s`、`ImpLFEOn=yes`、`ImpMode=1`、`ImpEnforcePassivity=yes`、output all points。
- canonical payload `canonical_waveform_le_f64.bin` 为 1,177,344 bytes，SHA-256 `5ec5211a273d313655f0b8ced35d58ea89d0bba113f5edc3fd9712218f46e726`；格式是 little-endian f64 `(time, tx differential, rx differential)`，49,056 个半开区间样本，观测列为 `rx_differential`，ADS inclusive endpoint 不纳入 canonical payload。

### dsdump 与 controller log

Keysight ADS dsdump 对 dataset 的 `TRAN.TRAN` 观察为 inclusive 49,057 点，采样间隔 bits `3d712e0be826d695`（32 samples/UI）。首个 symbol bits 为 `1101`；index 32 是 phase-0 boundary，首个观测到的 phase-1 transition 为 index 65；第三周期起点为 index 32704，phase-1 transition 为 index 32705。即 phase 0 保留 prior symbol，phase 1..31 归属 current symbol。这是 source phase fact，不是 channel solver parity 证明。

原工作区 `netlist.log`：7,858 bytes，SHA-256 `676838f9bff5f92cd0e645da7db20b3adf3399cab015300d1d3b34e8098f3983`。关键 controller 字段为：Touchstone interpolation `linear`、extrapolation `constant`、`ChannelSim Type=Statistical`、`ToleranceMode=1`、`EnforcePassivity=yes`、`MaxImpulseLength=1000`、`NumberTimePtPerUI=32`、`StatusLevel=2`、`AntiAliasingWindow=1`、`ImpLFEOn=yes`、`ImpCache=yes`、TX/RX `UseControllerSampleRate=yes`、RX `wave_capture_delay=1000`、count `2047`、mode `2`。该 log 是 controller observation，不是 P3C acceptance。

### PyBERT exact revision

PyBERT exact commit 为 `5bf6d7ea0ace261891aaeb611ffc1c267e160afe`，tree 为 `5faef6bdb341d444ad65d82a11c0018b15805e24`。绑定的源码 blob SHA-256 为：

- `src/pybert/models/bert.py`: `145cb77bd1c864a41c307e76581beb19c6de7ec1a5764cada9df82882bbf4d10`
- `src/pybert/pybert.py`: `a2fdd33db845db09155e323a26465688d759e77ed2bcc4a23cb7a5298d5457dd`
- `src/pybert/utility/sparam.py`: `a14b65364f124a807c0efd3f0c73d7dc54bb750598edcf26996c588054e3011d`
- `src/pybert/utility/sigproc.py`: `394c8ffebf5ae2c352ab16c0155a1241b84089f6bd8bbb40fc7ce1d73e0758ad`
- `docs/RUST_SIMULATION_ENGINE_MIGRATION.md`: `e7036c0b71b0ea34bbe0bdc6634590f963b7917d9cf7814bcaf0ff195abc3f86`

该 revision 的语义观察为：`calc_chnl_h` 后进行保留 leading zeros 的 causal linear convolution；四端口执行 mixed-mode Sdd21；Touchstone 为 polar interpolation/extrapolation policy；source/load 使用频变 termination 与 voltage normalization；`irfft` 后从 `t_irfft` cubic resample 到 system `t` 并按 dt 缩放；impulse 做 20..100 UI front-porch、kept-energy 0.999 trimming；peak index 仅作 delay diagnostic；native channel stage 没有显式 ADS controller output strobe。以上仅作 forensic reference，未复制 PyBERT 算法。

## 当前产品绑定与验证

SIPI clean archive commit 为 `74ef3870a1738f58fc2694ca989a39dc290b9339`，tree 为 `bd1d8e6948b828509cffac598529615c4f7f9f4c`；观察绑定的 P3C/S-parameter/channel/compare source inventory 均由 verifier 按该 archive 重新 hash。当前 strict replay 绑定第三周期 start `32704`、count `16352`、NRMSE bits `3f9dd184cd51df98`、decimal `0.02911956313297956`，固定 limit `0.01`，`within_limit=false`。source-policy 变更仅为 test-only evidence，未改 product runtime policy。

通过的验证：

```text
python -B tools/verify_p3c_original_project_channel_semantics_observation.py
{'valid': True, 'source_phase_bound': True, 'current_waveform_accepted': False}

python -B -m pytest -q tools/test_verify_p3c_original_project_channel_semantics_observation.py
4 passed
```

mutation tests 覆盖 retained dataset identity、dsdump phase index、controller sample rate、PyBERT source blob/semantic、conclusion migration authorization 和 alignment policy；每项篡改均 fail closed。该切片没有修改 `PLAN.md`、remaining-items ledger、product-boundary/license/source-map，也没有提交 commit。
