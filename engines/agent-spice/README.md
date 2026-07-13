# Agent-Spice

Agent-Spice 是面向电源完整性与高速互连场景的命令行工具。当前稳定的用户工作流有两类：

- `fit-sparam`：将 Touchstone S 参数拟合为 SPICE 子电路、RFM 和可核验的 fitted Touchstone。
- `run-hspice`：解析 HSPICE 网表，展开 `.alter`，并生成兼容性报告与后端输入文件。

仓库内还保留了 IdEM、极点、模态和基准探针命令，供算法研究使用；它们不是稳定产品接口，参数与输出契约可能变化，因此不在本 README 中逐项承诺。可用 `python -m agent_spice.cli --help` 查看完整命令索引，以及 `python -m agent_spice.cli <命令> --help` 查看探针命令的即时帮助。

可公开复核的基准结论见 [S 参数 Benchmark](docs/sparam-benchmark.html)。

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
| `board_fitted.rfm` | RFM 模型。 |
| `board_fitted_rfm_wrapper.sp` | 引用 RFM 的 wrapper 网表。 |
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
| `--rfm PATH` | 自动生成 | RFM 输出路径。默认与 SPICE 输出同名，扩展名为 `.rfm`。 |
| `--rfm-wrapper PATH` | 自动生成 | RFM wrapper 路径，默认 `<rfm 名称>_rfm_wrapper.sp`。 |
| `--report-top-rms N` | `5` | HTML 中绘制 RMS 最大的 S 参数元素数量。`0` 表示不绘制曲线。 |
| `--log PATH` | `<输入名>.log`，位于 JSON 报告目录 | 写入逐阶次搜索摘要，包括阶次、RMS、状态和失败原因。 |
| `--rms-target FLOAT` | 必填 | 最终平均 S-RMS 上限，必须为正数。 |
| `--passivity {off,check,enforce}` | `check` | 被动性处理策略，见上表。 |
| `--max-order N` | `100` | 允许尝试的最大有效公共极点阶次；与端口数量无关。 |
| `--min-order N` | `1` | 已由此前完整报告验证的最低起始阶次；仅用于相同输入的重复拟合以跳过已知失败的低阶 trial。新输入必须保留默认值。 |
| `--max-order-step N` | `8` | RMS 明显未达标时允许的最大自适应阶次步长；必须为正整数。 |
| `--quality-profile {explore,signoff}` | `explore` | 报告质量门配置。`explore` 用于日常探索；`signoff` 用于更严格的交付检查。 |
| `--fail-on-quality` | 关闭 | 质量报告出现阻断项时，以非零退出码结束。 |
| `--allow-quality-warnings` | 关闭 | 仅与 `--fail-on-quality` 组合使用；允许 `WARN`，但仍拒绝 `FAIL`。 |
| `--subckt-name NAME` | `s_equivalent` | SPICE 子电路名称；RFM wrapper 会使用其安全化后的名称。 |
| `-h`、`--help` | - | 显示命令帮助。 |

所有输出路径必须不同；重复路径会在拟合前报错，避免产物互相覆盖。RFM 路径不能包含单引号，因为 HSPICE/Sigrity wrapper 使用单引号引用该文件。

### 专家调参

默认 `auto` 不会因本节接口而改变：**未传任何专家参数或 `--tuning-profile` 时，仍使用当前 Native `idem-fast` 自动策略、全频点 RMS 判定和既有 passivity 契约。** 只有默认参数在合理 `--max-order` 内不能满足目标的特殊输入，才应使用这些覆盖项。

| 参数 | 默认值 | 表示什么 | 何时尝试 |
| --- | --- | --- | --- |
| `--pole-spacing {lin,log,resonance}` | auto（当前为 `lin`） | 初始共享极点的频率布局：`lin` 均匀覆盖、`log` 低频更密、`resonance` 依据响应峰值提出初值。 | 怀疑窄带谐振或特定频段动态被遗漏时，优先尝试 `resonance`。 |
| `--fit-iterations N` | 端口相关 auto 值 | Native VF 的最大 relocation 迭代数。 | 初始模型明显尚未收敛时增加；更大值会增加时间，也可能放大极点漂移。 |
| `--hf-complex-pairs N` | 大端口 `2`，其余依 auto | 预留给高频端的附加复极点对数量。 | 高频 RMS 明显高于低频、且提高总 `--max-order` 仍无效时尝试。 |
| `--hf-pair-damping R` | `0.03` | 高频复极点对的归一化阻尼；较小值对应更尖锐、更高 Q 的候选谐振。 | 高频存在窄峰时可小幅降低；过小会导致条件数和被动性风险上升。 |
| `--hf-pair-start-fraction R` | `0.68` | 高频复极点对允许出现的频段下界，占输入频率跨度的归一化比例。 | 高频问题更靠近末端时提高；问题覆盖较宽的中高频时降低。 |
| `--passivity-max-iterations N` | auto（通常 `1`；大端口 enforce 为 `0`） | passivity enforcement 的最大修复轮数；`0` 表示不做修复轮。 | 原始拟合 RMS 达标、但修复后仍有被动性违例时增加。 |
| `--passivity-samples N` | auto（通常 `8`；大端口 enforce 为 `64`） | 每轮无源修复保留的最严重违规频点上限。 | 违规频段较多或修复遗漏局部尖峰时增加。 |
| `--passivity-active-variables N` | `3072` | 无源修复中允许同时调整的变量预算。 | 大端口模型的 enforcement 受限或修复不足时增加；会提高内存和时间。 |

`R` 必须在 `(0, 1]` 内。建议一次只改变一类参数，并固定 `--rms-target`、`--passivity`、`--max-order` 与输入文件；再比较 JSON 中的 `order_trials`、`comparison_mean_rms_error` 和 `passivity_max_sigma_after`。专家参数不保证通过，CLI 的 `PASS/FAIL` 与退出码仍以相同质量契约为准。

可将一组可复用覆盖写入严格 JSON profile：

```json
{
  "version": 1,
  "overrides": {
    "init_pole_spacing": "resonance",
    "fit_max_iterations": 20,
    "high_frequency_complex_pairs": 4,
    "high_frequency_complex_pair_damping": 0.06,
    "high_frequency_complex_pair_lower_fraction": 0.72,
    "passivity_max_iterations": 2,
    "passivity_samples": 16,
    "passivity_active_variables": 4096
  }
}
```

```powershell
python -m agent_spice.cli fit-sparam .\special.s166p `
  --rms-target 0.001 `
  --passivity enforce `
  --max-order 100 `
  --tuning-profile .\special-tuning.json `
  --fit-iterations 24
```

profile 只能包含上表对应的字段，未知字段会报错；同名 CLI 参数优先于 profile。报告的 `tuning_overrides` 记录请求来源和值，`effective_base_config` 记录最终实际生效的基础配置。

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

失败时不会把最接近的模型当作成功交付：CLI 返回 `FAIL` 和非零退出码；若存在有限 RMS 候选，仍会导出 RMS 最低的诊断输出，并在 JSON/HTML 中标记为“最佳可得输出（未达目标）”。最终 JSON/HTML 会保留搜索记录，方便判断是最大阶次不足、RMS 未达标，还是被动性修复后 RMS 超标。

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
