# Agent-Spice

Agent-Spice is an early PI simulation middleware prototype focused on HSPICE legacy deck compatibility and future S-parameter/CPM workflows.

Current checkpoint:

- HSPICE project manifest parsing.
- HSPICE deck audit for directives, includes, libraries, and unsupported commands.
- `.alter` expansion into independent cases.
- `.measure/.probe/.print` normalization.
- Compatibility report and basic HSPICE-to-backend conversion.
- Backend command adapters for ngspice, Xyce, and XDM-assisted Xyce translation.
- Target-driven Touchstone fitting with truthful passivity checking and enforcement.

Install and verify local solver tools:

```powershell
git lfs pull
.\tools\install-solvers.ps1
.\tools\doctor-solvers.ps1 -Smoke
```

Open a new terminal after installation, or refresh the current shell:

```powershell
$env:Path = "$env:USERPROFILE\tools\agent-spice-solvers\bin;$env:Path"
```

## Verify The MVP

Run the unit and smoke suite:

```powershell
python -m pytest -v
```

Generate HSPICE case artifacts without running a simulator:

```powershell
python -m agent_spice.cli run-hspice tests/fixtures/hspice/simple_pi.sp --backend ngspice --output-root runs-smoke
Test-Path runs-smoke/simple_pi/simple_pi__base/case.cir
Test-Path runs-smoke/simple_pi/simple_pi__base/compat_report.json
```

Verify `.alter` case expansion:

```powershell
python -m agent_spice.cli run-hspice tests/fixtures/hspice/alter_pi.sp --backend ngspice --output-root runs-smoke-alter
Test-Path runs-smoke-alter/alter_pi/alter_pi__base/case.cir
Test-Path runs-smoke-alter/alter_pi/alter_pi__alter_001_high_decap/case.cir
Test-Path runs-smoke-alter/alter_pi/alter_pi__alter_002_low_decap/case.cir
```

Verify the synthetic-real HSPICE corpus golden reports:

```powershell
python -m pytest tests/test_hspice_corpus_golden.py -v
```

## S-Parameter Fitting

### 快速开始

`fit-sparam` 面向常规 S 参数建模：给定 Touchstone 和目标 RMS，工具会搜索满足目标的最小有效阶次，并默认交付可仿真的 SPICE、Cadence RFM 与可独立核验的拟合 Touchstone。最短命令如下：

```powershell
python -m agent_spice.cli fit-sparam .\board.s19p --rms-target 0.001
```

不指定 `--output` 时，产物写在输入文件旁。对 `board.s19p`，成功后会得到：

| 文件 | 用途 |
| --- | --- |
| `board_fitted.sp` | Native SPICE 子电路。 |
| `board_fitted.s19p` | 在原始频率网格上重采样的 fitted S 参数，用于与输入直接比对。 |
| `board_fitted.rfm` | Cadence Broadband SPICE RFM 模型。 |
| `board_fitted_rfm_wrapper.sp` | 引用 RFM 的 HSPICE/Sigrity wrapper。 |
| `board_fitted_report.json` | 面向自动化的完整拟合、阶次、RMS、被动性和产物路径记录。 |
| `board_fitted_report.html` | 中文质量报告，默认绘制 RMS 最大的 5 个 S 参数元素。 |

搜索过程不会为每个候选阶次写出 SPICE、Touchstone、RFM 或 HTML 文件。每次试探的阶次、RMS、被动性和拒绝原因只记录在最终 JSON 的 `order_trials`；传入 `--log fit.log` 时，也会写入一份简洁的逐阶次文本日志。只有选中的最终阶次才生成上表交付物。

默认被动性策略是 `check`：模型会被检查，但即使发现非被动也会保留产物并在报告中标注。需要最终模型严格被动时，将策略改为 `enforce`：

```powershell
python -m agent_spice.cli fit-sparam .\board.s19p `
  --rms-target 0.001 `
  --passivity enforce
```

当需要控制输出目录或文件名时，只覆盖需要改动的路径；其余工件仍会自动生成：

```powershell
python -m agent_spice.cli fit-sparam .\board.s19p `
  --rms-target 0.001 `
  --output .\deliverables\board.sp `
  --rfm .\deliverables\cadence\board.rfm `
  --max-order-step 12 `
  --report-top-rms 8
```

这里会默认同时写出 `deliverables\board.s19p`、`deliverables\cadence\board_rfm_wrapper.sp`、`deliverables\fit_report.json` 与 `deliverables\fit_report.html`。`--fitted-touchstone`、`--rfm-wrapper`、`--report`、`--html-report` 可分别覆盖默认路径。所有请求的输出路径必须不同；重复路径会在拟合开始前直接报错，避免覆盖工件。

### 如何验收结果

优先打开 HTML 报告：它列出输入、SPICE、fitted Touchstone、RFM 与 wrapper 的本地链接，并展示默认 5 条 RMS 最大曲线。用 fitted Touchstone 与原始 Touchstone 做外部工具比较时，必须使用同一频率网格和参考阻抗；JSON 内的 `comparison_rms_error`、`rms_target`、`target_met` 和 `passivity_max_sigma_after` 是自动化验收的权威字段。

成功表示所选最低阶模型满足用户给定的 RMS 目标，并在 `--passivity enforce` 时也满足被动性。若失败，顶层 JSON/HTML 与各阶次 trial 目录仍会保留，便于判断是阶次上限不足、RMS 未达标，还是被动性修复使最终 RMS 超标；不会把最接近的失败模型伪装成成功交付。

`fit-sparam` is a target-driven workflow based on the local Native IdEM-fast vector-fitting implementation. The production fitting baseline is `native-idem-fast-v1`, and Native is the only production fitting backend. The user supplies a final mean S-RMS target and chooses how passivity is handled. The tool searches for the lowest accepted effective common-pole order up to `--max-order`.

The production SPICE output is always emitted by the Native writer; there is no exporter selection. External IdEM integration is limited to benchmark/research tooling and is not a production runtime dependency.

scikit-rf remains a supporting dependency for non-fitting infrastructure such as Touchstone fallback loading, metrics, modal/research workflows, and compatibility investigations. It is not a selectable production fitting backend.

```powershell
python -m agent_spice.cli fit-sparam .\path\to\model.s91p `
  --rms-target 0.001 `
  --passivity check `
  --max-order 24 `
  --output runs-sparam\model.sp
```

The RMS target is:

```text
sqrt(mean(abs(S_fit - S_raw) ** 2))
```

It is evaluated over every original frequency point and every S-parameter channel, so it does not grow with port count.

Effective order is reported as:

```text
real pole count + 2 * complex pole-pair count
```

### Passivity Policies

`--passivity check` is the default.

- `off`: fit and evaluate RMS without passivity work.
- `check`: select order from RMS, run the Hamiltonian/adaptive full-frequency checker, and emit a non-passive model as `PASS_WITH_PASSIVITY_WARNING`.
- `enforce`: run enforcement only for orders whose pre-enforcement RMS can meet the target. An order passes only when the post-enforcement model meets both the RMS target and `max_sigma <= 1 + 1e-6`.

Example requiring a passive final model:

```powershell
python -m agent_spice.cli fit-sparam .\path\to\model.s91p `
  --rms-target 0.001 `
  --passivity enforce `
  --max-order 24 `
  --output runs-sparam\model_passive.sp
```

Enforcement is judged from the final model. A good pre-enforcement RMS does not satisfy the target if passivity repair pushes the final RMS above the requested value.

### Order Search

Vector-fitting error is not strictly monotonic in order, so the production scheduler does not use binary search. It starts at low order and increases the step only while RMS remains far above the requested target; after the first passing probe, it backfills the last skipped interval to choose the best passing order found there. Every requested order is evaluated at most once. `--max-order-step` caps the adaptive jump and defaults to `8`; set it to `2` to retain the former conservative two-order ladder.

Defaults:

- `--max-order 24` for 60 or more ports.
- `--max-order 40` below 60 ports.
- Full original frequency grid for fitting and final evaluation.
- Native vector fitting baseline `native-idem-fast-v1`.
- IdEM-fast topology and pole-relocation profile: models below 30 ports use full streaming relocation; models with 30 or more ports prefer reciprocal relocation and automatically fall back to full streaming when reciprocity is not present.

### Success And Failure

On success, the requested SPICE output, fitted Touchstone, RFM, RFM wrapper, and JSON/HTML reports are written. On failure, trial reports and the top-level audit report remain available, but the requested production model exports are absent. The tool never promotes the closest failed model as a successful result.

The JSON report includes:

- `rms_target`, `passivity_policy`, and `max_order`.
- `selected_effective_order`, `target_met`, and `target_stop_reason`.
- Per-order pre/final RMS and pre/final max sigma.
- Fit, check, enforcement, total time, and peak RSS.
- Requested/effective order and pole topology counts.
- `rms_formula=mean_s_rms_v1` and `order_formula=real_plus_twice_complex_v1`.

Top-level time covers every attempted order in the target search, and top-level peak RSS is the maximum across those trials. Per-order costs remain available in `order_trials`.

For CI or signoff, add the quality gate:

```powershell
python -m agent_spice.cli fit-sparam .\path\to\model.s91p `
  --rms-target 0.001 `
  --passivity enforce `
  --max-order 24 `
  --output runs-sparam\model.sp `
  --quality-profile signoff `
  --fail-on-quality
```

Historical candidate-list and passivity flags remain hidden compatibility aliases. New automation should use only `--rms-target`, `--passivity`, and `--max-order`. Removed backend choices such as vector-fitting backend selection, relocation backend selection, and `skrf` export selection must not be used in production examples.

The canonical Native/IdEM comparison is recorded in `docs/sparam-idem-full-benchmark.md`.
The canonical IdEM S19 tuning report is recorded in `docs/sparam-idem-s19-tuning.md`.
