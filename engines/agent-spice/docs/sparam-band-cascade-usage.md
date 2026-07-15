# S 参数分频段与级联拟合使用说明

本文说明两个显式启用的 S-fit 能力：

1. 单个 Touchstone 的优先频段拟合。
2. 多个二端口 Touchstone 的有序级联拟合、逐块被动性 enforcement 和级联后被动性验收。

不传新参数时，原有 `fit-sparam` 的全带目标、输出格式和被动性路径不变。

## 1. 优先频段拟合

### 1.1 命令

```powershell
python -m agent_spice.cli fit-sparam .\channel.s2p `
  --priority-band 0:1e7:0.001 `
  --priority-band 1.2e9:1.5e9:0.002:2 `
  --outside-band-weight 0.1 `
  --passivity enforce
```

`--priority-band` 的格式为 `F_MIN:F_MAX:RMS_TARGET[:WEIGHT]`，频率单位为 Hz，区间包含两个端点。频率范围与正数 `RMS_TARGET` 必须在同一个参数中出现；省略 `WEIGHT` 时段内权重为 `1`。该选项可重复，重叠频段的拟合权重取最大值，但每个频段的 RMS 门限仍分别验收。

原有 `--rms-target` 现在明确表示全频段门限。指定优先频段但省略它时，全频段门限默认为最严格频段目标的 3 倍。上例因此要求 0-10MHz RMS 不超过 `0.001`、1.2-1.5GHz RMS 不超过 `0.002`，同时全频段 RMS 不超过 `0.003`。显式传 `--rms-target 0.0025` 可覆盖这个默认值。

`--outside-band-weight` 必须大于 `0`，默认 `0.1`。它不是删除带外数据：带外样本仍参与拟合和完整频带被动性检查，只是在最小二乘目标中的约束被放松。

### 1.2 权重实际作用的位置

优先频段不是仅改变报告或最后的 PASS/FAIL。权重进入三处：

- 有频点预算时的加权频点抽样，使窄目标频段不会被均匀降采样淹没。
- Vector Fitting 的极点迁移方程，优先把公共极点放到目标频段需要的位置。
- 固定极点后的每个 S 参数残差最小二乘。

默认没有 `--priority-band` 时，不构造权重矩阵，保持原有数值路径。

### 1.3 RMS 与验收语义

指定优先频段后：

- 每个频段的 `RMS_TARGET` 单独参与阶数搜索和 PASS/FAIL。
- `--rms-target` 是全频段门限；未指定时自动取最严格频段目标的 3 倍。
- 只有每个指定频段和全频段同时达标，当前阶次才满足 RMS 验收。
- `target_mean_rms_error` 保留为优先频段并集 RMS 诊断值，不再单独决定 PASS/FAIL。
- `comparison_mean_rms_error` 始终是所有原始频点、所有 S 元素的全带 RMS。
- `outside_band_mean_rms_error` 是所有优先频段以外的 RMS。
- `weighted_mean_rms_error` 使用拟合权重计算。
- `frequency_band_metrics` 逐段记录频率范围、目标、权重、频点数、实测 RMS 和 `target_met`。

因此，目标频段达标但全带 RMS 超标，或全带达标但任一目标频段超标，都会继续搜索更高阶次并最终在未找到双门限解时返回 `FAIL`。被动性没有随带外误差一起放松；`--passivity enforce` 仍对完整模型和渐近常数矩阵生效。

## 2. 有序二端口级联

### 2.1 Manifest

级联关系使用版本化 JSON。路径相对 manifest 所在目录解析：

```json
{
  "version": 1,
  "blocks": [
    {
      "name": "die",
      "touchstone": "models/die.s2p",
      "rms_target": 0.0008,
      "max_order": 60
    },
    {
      "name": "package",
      "touchstone": "models/package.s2p"
    },
    {
      "name": "board",
      "touchstone": "models/board.s2p"
    }
  ],
  "cascade": ["die", "package", "board"]
}
```

`blocks` 中每个名称必须唯一，文件必须是 `.s2p`。`cascade` 是从输入端到输出端的连接顺序，必须恰好包含每个 block 一次。block 可覆盖全局 `rms_target` 和 `max_order`。

当前不接受一般多端口连接图、端口映射或同一 block 重复实例。它们需要明确的连接矩阵和端口参考方向，不能安全地套用二端口级联运算。

### 2.2 命令

```powershell
python -m agent_spice.cli fit-sparam-cascade .\cascade.json `
  --output-root .\cascade-fit `
  --rms-target 0.001 `
  --max-order 80 `
  --passivity-epsilon 1e-6 `
  --cascade-passivity-epsilon 1e-8 `
  --cascade-samples 2001
```

优先频段也可应用于每个 block：

```powershell
python -m agent_spice.cli fit-sparam-cascade .\cascade.json `
  --priority-band 1e8:2e9:0.001 `
  --outside-band-weight 0.1
```

级联命令沿用相同双门限语义：每个 block 的全带门限默认是最严格频段目标的 3 倍；显式 `--rms-target` 或 manifest 中 block 的 `rms_target` 可覆盖全带门限。级联被动性收缩候选也必须保持每个 block 的全带与逐频段 RMS 同时达标。

### 2.3 执行流程

1. 验证 manifest、二端口数量和级联顺序。
2. 对每个 block 独立运行目标阶数搜索，策略固定为 `passivity=enforce`。
3. 每个 block 生成 SPICE、fitted Touchstone、RFM、RFM wrapper、JSON、HTML 和日志。
4. 取所有输入频率范围的交集；交集为空时失败，不做带外延拓。
5. 在 `--reference-impedance` 指定的共同参考阻抗下重归一化，默认 `50 ohm`。
6. 按 manifest 顺序级联原始样本和 fitted 模型，报告级联 RMS 与最大奇异值。
7. 若级联最大奇异值超过 `1 + --cascade-passivity-epsilon`，进入受约束修复。

每个 block 已通过连续频率 Hamiltonian 被动性检查。级联检查使用共同频段内的密集采样，主要用于发现参考阻抗、数值容差和组合后的局部越界；报告中的 `evaluation_scope` 固定标明 `intersection_only_no_extrapolation`。

### 2.4 级联修复算法

修复只缩放有理模型的 S 参数残数、常数项和比例项，极点保持不变：

```text
S_adjusted(s) = alpha * S_fitted(s),  0 < alpha <= 1
```

标量收缩保持因果性和稳定极点，并把 S 矩阵推向严格被动区域。搜索顺序为：

1. 分别尝试只收缩一个 block。
2. 单块无可接受解时，尝试全链相同收缩。
3. 对通过候选做二分细化，寻找最接近 `alpha=1` 的值。
4. 在候选中选择各 block 目标 RMS 增量最小的解。

任何候选只要使某个 block 的目标 RMS 超过其门限，就会被拒绝。`--minimum-scale` 默认 `0.8`，限制最大收缩范围；`--adjustment-iterations` 控制扫描和二分次数。若在 RMS 门限和收缩范围内无解，命令返回 `FAIL`，不会为了被动性静默牺牲拟合精度。

修复后会重新生成被调整 block 的全部模型产物，并在 block JSON 中写入 `cascade_adjustment`。未被调整的 block 不会重写。

## 3. 输出目录

默认输出目录为 `<manifest 名称>_fit`：

```text
cascade-fit/
  cascade_report.json
  cascade_fitted.s2p
  blocks/
    die/
      die.sp
      die_fitted.s2p
      die.rfm
      die_rfm_wrapper.sp
      fit_report.json
      fit_report.html
      fit.log
```

`cascade_report.json` 重点字段：

- `status`：全部 block 达标且级联被动性达标时为 `PASS`。
- `cascade_mean_rms_error`：原始 block 级联与 fitted block 级联的平均 S-RMS。
- `passivity_before_adjustment` / `passivity_after_adjustment`：级联最大奇异值及频率。
- `selected_scales`：每个 block 的最终收缩系数；未调整为 `1.0`。
- `adjustment_trials`：候选 block、系数、级联最大奇异值和各 block RMS。
- `blocks`：每个 block 的目标 RMS、产物路径和最终系数。

`cascade_fitted.s2p` 使用统一参考阻抗和级联评估频率网格，便于外部工具复核。

## 4. 失败条件

以下情况返回非零退出码并在报告中记录原因：

- manifest 版本、名称、路径或顺序无效。
- 输入不是二端口 `.s2p`。
- 任一 block 在最大阶次内未同时满足 RMS 和被动性目标。
- 各 block 没有共同覆盖频段。
- 级联被动性越界，且所有允许的收缩候选都会突破 block RMS 门限。

生产签核仍应结合实际连接方式做 AC/TRAN 验证。级联命令证明的是给定有序二端口关系、共同参考阻抗和共同频段下的模型组合质量，不替代系统网表中的终端、偏置和激励条件。

项目 19-port/30-port 语料上的固定阶次 A/B、具体端口级联例子及已暴露问题，见 [项目语料实验报告](sparam-band-cascade-experiment-report.md)。
