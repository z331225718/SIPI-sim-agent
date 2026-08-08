# S 参数 Fit/Export MVP Design

日期：2026-07-02

## 背景

前期 spec 和 IdEM/开源宏建模调研都指向同一个结论：PI 瞬态仿真不能依赖 ngspice 或 Xyce 原生读取 Touchstone 的能力。MVP 应先把 Touchstone S 参数转换为可被 SPICE 后端执行的等效子电路，再进入后续 PDN/CPM 系统 deck。

当前仓库已经有一个很薄的 `fit_touchstone_to_spice()` wrapper，会直接调用 `scikit-rf` 的 `auto_fit()`、`passivity_enforce()` 和 `write_spice_subcircuit_s()`。本设计把它提升为可脚本化、可验证、可报告的 MVP 管线。

## 范围

本阶段交付 `Touchstone -> VectorFitting -> passivity enforcement -> SPICE subckt -> fit report`。

必须支持：

- Python API：`fit_touchstone_to_spice(touchstone_path, output_path, config=...) -> SParamFitResult`。
- CLI：`agent-spice fit-sparam input.s2p --output model.sp --report fit_report.json`。
- 默认使用 `VectorFitting.auto_fit()`，并允许配置为手动 `vector_fit()`。
- 默认执行 `passivity_enforce()`，并记录 enforce 前后的 passive 状态。
- 生成机器可读 JSON 报告，包含输入元数据、拟合配置、RMS error、passivity violation bands、导出文件路径。
- 提供最小 `.s2p` fixture 和 README 验证命令。

本阶段不做：

- SROPEE/MOR 和 32/64/128-port 规模化优化。
- 完整 `sparam.conditioning`，包括端口角色映射、参考阻抗重归一化、DC extrapolation、causality 检查。
- 拟合对比图和网页报告。
- 自动组装 PDN + CPM + S 参数系统 deck。

## API 设计

`SParamFitConfig` 负责表达拟合选择：

- `mode`: `"auto"` 或 `"manual"`。
- `n_poles_real`、`n_poles_cmplx`: 手动拟合参数。
- `model_order_max`、`target_error`: auto-fit 参数。
- `parameter_type`: 默认 `"s"`。
- `enforce_passivity`: 默认 `True`。
- `subckt_name`: 默认 `"s_equivalent"`。
- `create_reference_pins`: 默认 `False`。

`SParamFitResult` 负责返回可序列化结果：

- `touchstone_path`、`spice_path`、`report_path`。
- `ports`、`frequency_points`、`reference_impedance`。
- `config`。
- `rms_error`。
- `passive_before_enforce`、`passive_after_enforce`。
- `passivity_violations_before`、`passivity_violations_after`。

## 数据流

```text
Touchstone file
  -> skrf.Network
  -> Touchstone metadata
  -> VectorFitting(network)
  -> auto_fit() or vector_fit()
  -> is_passive()/passivity_test()
  -> passivity_enforce() when enabled
  -> write_spice_subcircuit_s()
  -> fit_report.json
```

## 错误处理

- 输入 Touchstone 不存在时，由 `skrf.Network` 抛错并透传给 CLI，CLI 返回非零退出码。
- 报告路径未指定时，CLI 默认写到 SPICE 输出同目录的 `fit_report.json`。
- `mode` 不是 `"auto"` 或 `"manual"` 时抛出 `ValueError`。
- passivity 测试方法在某些模型上失败时，记录 `null`，但不阻止 SPICE 导出；后续质量门禁阶段再决定阻断策略。

## 测试策略

- 单元测试使用 fake `Network` 和 fake `VectorFitting`，验证调用顺序、配置传递、report JSON 和返回对象。
- CLI 测试 monkeypatch API，验证参数解析、默认 report 路径和退出码。
- smoke 测试使用最小 `.s2p` fixture，验证真实 `scikit-rf` 能生成 `.subckt` 文件和 JSON 报告。

## 验收命令

```powershell
python -m pytest -v
python -m agent_spice.cli fit-sparam tests/fixtures/sparam/simple_through.s2p --output runs-sparam/simple_through.sp --report runs-sparam/fit_report.json
Test-Path runs-sparam/simple_through.sp
Test-Path runs-sparam/fit_report.json
```
