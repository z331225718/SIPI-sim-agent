# Agent-Spice

Agent-Spice 是面向电源完整性与高速互连场景的命令行工具。当前稳定的用户工作流有两类：

- `fit-sparam`：将 Touchstone S 参数拟合为 SPICE 子电路、Cadence RFM 和可核验的 fitted Touchstone。
- `run-hspice`：解析 HSPICE 网表，展开 `.alter`，并生成兼容性报告与后端输入文件。

仓库内还保留了 IdEM、极点、模态和基准探针命令，供算法研究使用；它们不是稳定产品接口，参数与输出契约可能变化，因此不在本 README 中逐项承诺。可用 `python -m agent_spice.cli --help` 查看完整命令索引，以及 `python -m agent_spice.cli <命令> --help` 查看探针命令的即时帮助。

## 安装与验证

建议使用项目的 Python 环境安装依赖，然后运行测试：

```powershell
python -m pytest -q
```

HSPICE 后端需要本地安装求解器时，可执行：

```powershell
git lfs pull
.\tools\install-solvers.ps1
.\tools\doctor-solvers.ps1 -Smoke
```

若脚本安装了本地求解器，重新打开终端，或在当前 PowerShell 中刷新 `PATH`：

```powershell
$env:Path = "$env:USERPROFILE\tools\agent-spice-solvers\bin;$env:Path"
```

## S 参数拟合

### 最短命令

```powershell
python -m agent_spice.cli fit-sparam .\board.s19p --rms-target 0.001
```

输入应为 Touchstone `.sNp` 文件。未指定 `--output` 时，交付物写在输入文件旁。以 `board.s19p` 为例：

| 文件 | 含义 |
| --- | --- |
| `board_fitted.sp` | Native SPICE 子电路。 |
| `board_fitted.s19p` | 与原始频率网格相同的 fitted S 参数，用于外部核验。 |
| `board_fitted.rfm` | Cadence Broadband SPICE RFM 模型。 |
| `board_fitted_rfm_wrapper.sp` | 引用 RFM 的 HSPICE/Sigrity wrapper。 |
| `board_fitted_report.json` | 机器可读的拟合、阶次、误差、被动性和产物路径报告。 |
| `board_fitted_report.html` | 中文质量报告，默认显示最终交付摘要和 RMS 最大的 5 个 S 参数元素；完整内部配置与质量诊断在折叠区，JSON 保留全部配置。 |
| `board.log` | 搜索过程的逐阶次文本日志。 |

搜索阶段不会生成每个阶次的 SPICE、RFM、Touchstone 或 HTML 文件。每次试探仅记录到最终 JSON 的 `order_trials`；默认日志会在每个阶次开始和结束时立即追加并刷新。只有最终选中的阶次才会生成交付物。

### RMS 与阶次

验收 RMS 定义为：

```text
sqrt(mean(abs(S_fit - S_raw) ** 2))
```

该值在全部原始频点和全部 S 参数通道上计算。有效阶次定义为：

```text
实极点数 + 2 * 复极点对数
```

搜索从低阶开始。误差远高于目标时会增大阶次步长；接近目标时缩小步长。`--max-order-step` 限制最大跳步，默认值为 `8`；设为 `2` 可使用较保守的两阶步进。由于矢量拟合误差不严格单调，跳步模式只回填最后一个跨越目标的区间；若必须优先检查每个偶数阶次，使用 `--max-order-step 2`。

### 被动性策略

| `--passivity` 值 | 行为 |
| --- | --- |
| `off` | 只验证 RMS，不做被动性检查。 |
| `check`（默认） | 检查被动性；即使非被动，也会保留拟合产物，并在报告中标记警告。 |
| `enforce` | 仅接受同时满足 RMS 目标和被动性目标的最终模型。若修复被动性后 RMS 超标，则该阶次失败。 |

要求最终模型被动的示例：

```powershell
python -m agent_spice.cli fit-sparam .\board.s19p `
  --rms-target 0.001 `
  --passivity enforce
```

### `fit-sparam` 全部公开参数

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `touchstone` | 必填位置参数 | 输入 Touchstone `.sNp` 文件。 |
| `--output PATH` | `<输入名>_fitted.sp` | 最终 SPICE 子电路路径。指定后，未显式覆盖的报告默认写在该目录。 |
| `--report PATH` | 自动生成 | JSON 报告路径。未指定 `--output` 时为 `<输入名>_fitted_report.json`；指定 `--output` 时为输出目录的 `fit_report.json`。 |
| `--html-report PATH` | 自动生成 | 中文 HTML 报告路径；命名规则与 JSON 报告一致。 |
| `--fitted-touchstone PATH` | 自动生成 | fitted `.sNp` 输出路径。默认与 SPICE 输出同名，仅扩展名使用输入 Touchstone 的 `.sNp` 后缀。 |
| `--rfm PATH` | 自动生成 | Cadence RFM 输出路径。默认与 SPICE 输出同名，扩展名为 `.rfm`。 |
| `--rfm-wrapper PATH` | 自动生成 | RFM wrapper 路径，默认 `<rfm 名称>_rfm_wrapper.sp`。 |
| `--report-top-rms N` | `5` | HTML 中绘制 RMS 最大的 S 参数元素数量。`0` 表示不绘制曲线。 |
| `--log PATH` | `<输入名>.log`，位于 JSON 报告目录 | 写入逐阶次搜索摘要，包括阶次、RMS、状态和失败原因。 |
| `--rms-target FLOAT` | 必填 | 最终平均 S-RMS 上限，必须为正数。 |
| `--passivity {off,check,enforce}` | `check` | 被动性处理策略，见上表。 |
| `--max-order N` | `100` | 允许尝试的最大有效公共极点阶次；与端口数量无关。 |
| `--max-order-step N` | `8` | RMS 明显未达标时允许的最大自适应阶次步长；必须为正整数。 |
| `--quality-profile {explore,signoff}` | `explore` | 报告质量门配置。`explore` 用于日常探索；`signoff` 用于更严格的交付检查。 |
| `--fail-on-quality` | 关闭 | 质量报告出现阻断项时，以非零退出码结束。 |
| `--allow-quality-warnings` | 关闭 | 仅与 `--fail-on-quality` 组合使用；允许 `WARN`，但仍拒绝 `FAIL`。 |
| `--subckt-name NAME` | `s_equivalent` | SPICE 子电路名称；RFM wrapper 会使用其安全化后的名称。 |
| `-h`、`--help` | - | 显示命令帮助。 |

所有输出路径必须不同；重复路径会在拟合前报错，避免产物互相覆盖。RFM 路径不能包含单引号，因为 HSPICE/Sigrity wrapper 使用单引号引用该文件。

### 常用示例

指定交付目录并扩大搜索步长：

```powershell
python -m agent_spice.cli fit-sparam .\board.s19p `
  --rms-target 0.001 `
  --passivity enforce `
  --output .\deliverables\board.sp `
  --rfm .\deliverables\cadence\board.rfm `
  --max-order 80 `
  --max-order-step 12 `
  --report-top-rms 8 `
  --log .\deliverables\fit.log
```

用于 CI 或签核：

```powershell
python -m agent_spice.cli fit-sparam .\board.s19p `
  --rms-target 0.001 `
  --passivity enforce `
  --quality-profile signoff `
  --fail-on-quality
```

### 如何验收

优先打开 HTML 报告：其中提供输入、SPICE、fitted Touchstone、RFM 和 wrapper 的本地链接，并展示最差 RMS 曲线。JSON 中建议重点检查：

- `target_met`：是否满足目标。
- `comparison_mean_rms_error`：与 `--rms-target` 使用同一 `mean_s_rms_v1` 公式的目标判定 RMS。
- `passivity_max_sigma_after`：最终被动性最大奇异值。
- `selected_effective_order`：选中的有效阶次。
- `order_trials`：搜索过程中的每个试探阶次及其结果。

失败时不会把最接近的模型当作成功交付。最终 JSON/HTML 会保留搜索记录，方便判断是最大阶次不足、RMS 未达标，还是被动性修复后 RMS 超标。

## HSPICE 网表处理

`run-hspice` 用于网表兼容性分析、`.alter` 展开及后端输入生成。默认只生成文件，不运行求解器：

```powershell
python -m agent_spice.cli run-hspice .\design.sp `
  --backend ngspice `
  --output-root .\runs
```

### `run-hspice` 全部公开参数

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `deck` | 必填位置参数 | 输入 HSPICE 网表。 |
| `--backend {ngspice,xyce,xyce-xdm}` | `ngspice` | 生成目标后端格式。 |
| `--output-root PATH` | `runs` | 输出根目录。 |
| `--execute` | 关闭 | 在生成后调用已配置的后端求解器执行。未指定时只生成工件。 |
| `-h`、`--help` | - | 显示命令帮助。 |

典型输出包括每个 case 的 `case.cir`、兼容性报告，以及 `.alter` 展开后的独立目录。快速核验示例：

```powershell
python -m agent_spice.cli run-hspice tests\fixtures\hspice\alter_pi.sp --output-root runs-smoke
Test-Path runs-smoke\alter_pi\alter_pi__base\case.cir
Test-Path runs-smoke\alter_pi\alter_pi__alter_001_high_decap\case.cir
```

## 完整命令索引与研究命令

顶层 CLI 还包含 `probe-idem-*`、`fit-idem-like`、`fit-modal-z`、`benchmark-sparam`、`preflight-sparam-corpus` 和 `compare-sparam-bands` 等研究、诊断和基准命令。这些命令的参数面较大，且会随算法实验演进；使用前必须以当前版本的帮助为准：

```powershell
python -m agent_spice.cli --help
python -m agent_spice.cli benchmark-sparam --help
```

## 版本与范围

生产 S 参数拟合基线为 `native-idem-fast-v1`。Native 是唯一的生产拟合与 SPICE 导出路径；外部 IdEM 仅用于基准和研究，不是运行时依赖。scikit-rf 用于 Touchstone 读取回退、指标和研究辅助，不是可选择的生产拟合后端。

历史性能对比可参阅 [IdEM 全量基准](docs/sparam-idem-full-benchmark.md) 与 [S19 调优记录](docs/sparam-idem-s19-tuning.md)。
