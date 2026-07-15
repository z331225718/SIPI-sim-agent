# Agent-Spice

Agent-Spice 是面向电源完整性与高速互连场景的命令行工具。当前稳定的用户工作流包括：

- `fit-sparam`：将 Touchstone S 参数拟合为 SPICE 子电路、RFM 和可核验的 fitted Touchstone。
- `fit-sparam-cascade`：按 manifest 拟合并 enforce 多个二端口 S 参数，再检查和修复有序级联链的整体被动性。
- `fit-yparam`：在 Y 参数域拟合 Touchstone，并输出 Y-domain SPICE 宏、Z-log 误差报告及可选的精确 Y-to-S RFM 交付物。
- `tune-yparam-tran`：针对明确提供的 HSPICE 签核场景，细调既有 Y-derived S-RFM 的低频残差；不会修改 `fit-sparam` 或将某个 CPM 场景硬编码为默认行为。
- `run-hspice`：解析 HSPICE 网表，展开 `.alter`，并生成兼容性报告与后端输入文件。
- `run-rfm`：不重新拟合、不展开普通 SPICE 状态子电路，直接用 XSPICE N-port device 执行 RFM 瞬态仿真。

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

## RFM 直接瞬态仿真

电路中用 `X` 实例连接 N 个端口和最后一个公共参考端，例如二端口：

```spice
Xchannel in out 0 rfm_direct
```

直接执行项目生成或兼容的 `VERSION 200600` RFM：

```powershell
python -m agent_spice.cli run-rfm .\channel-tran.sp `
  --rfm .\channel.rfm `
  --execute
```

该路径读取现有 pole/residue，生成的 `.sp` 仅含一个 XSPICE wrapper，不是展开后的有理函数宏模型。默认加载随 Agent-Spice 发布、与 Windows ngspice-46 ABI 匹配的 `rfm.cm`；不会修改全局 `spinit`，也不要求 Xyce/XDM。完整接口、产物、步长建议、限制和源码构建方法见 [RFM 直接仿真使用说明](docs/rfm-ngspice-usage.md)。

RFM 的复数行保存的是 `A_c/(s+omega_c)` 中的分母系数 `omega_c`，系统极点是 `p=-omega_c`；第二列不是系统极点虚部的直接副本。当前导出器、importer 和随包 XSPICE device 均按该 HSPICE 约定实现。由修复前版本生成的 RFM 即使能被 HSPICE 读入，也可能产生错误频响，必须从原拟合结果重新生成。

## Y 参数拟合与 Z-log 门禁

`fit-yparam` 以标准 Touchstone `.sNp` 为输入，先换算为 Y 参数再执行共享极点有理拟合。它面向阻抗/PDN 误差：报告同时包含 Y RMS（Siemens）和完整矩阵 `Z-log RMS`，后者定义为 `log10(|Zfit| / |Zref|)` 的 RMS（单位为 decades）。

最短命令：

```powershell
python -m agent_spice.cli fit-yparam .\board.s19p `
  --output .\board.y.sp `
  --derived-s-touchstone .\board.y-derived.s19p
```

默认输出是 Y-domain SPICE、JSON、HTML 和日志；`--derived-s-touchstone` 输出由有理 Y 严格换算得到的采样 S 参数。若需要连续频率 Y 正实性证书及 S-RFM 交付，请附加 `--no-fit-proportional --exact-s-rfm <path>`；该路径无法取得 KYP 证书时会硬失败，不会静默降级。

当前项目级算法门禁固定使用 held-out 全矩阵 `Z-log RMS`，严格要求 `Y-fit < S-fit`。运行：

```powershell
python scripts/benchmark_yparam_corpus.py `
  --output runs-yparam-benchmark/corpus-heldout-order20.json
```

默认语料覆盖 S19、S30 及 HSPICE 签核使用的 2-port 规约；任一输入持平、落后或 Z 转换失败时命令返回非零。完整的产物、KYP、TRAN 细调参数及门禁说明见 [Y 参数拟合使用说明](docs/yparam-usage.md)。

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

`*_rfm_wrapper.sp` 是供 HSPICE/Sigrity S 元件使用的 wrapper：每个 RFM port 都有一对端子 `nK nK_ref`，因此 N-port 子电路有 `2N` 个外部节点。实例化时必须按端子对连接，例如二端口为 `Xpkg p1 p1_ref p2 p2_ref s_equivalent`；不要把它误接成 `p1 p2 0`。这与 `run-rfm` 的 ngspice XSPICE wrapper（N 个信号节点加一个公共参考）是两条不同的接口。

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

整体很难拟合、但业务对某些频段有更严格要求时，可重复使用 `--priority-band F_MIN:F_MAX:RMS_TARGET[:WEIGHT]`。每个频段必须与自己的 RMS 目标同时出现。是否同时约束全频段，由用户是否显式传入 `--rms-target` 决定。

不传 `--rms-target` 时，只有指定频段的数据参与拟合，指定频段 RMS 和该范围内的被动性决定是否出结果；完整输入频带仅在拟合完成后计算一次，作为非阻塞诊断：

```powershell
python -m agent_spice.cli fit-sparam .\channel.s2p `
  --priority-band 0:1e7:0.001 `
  --priority-band 1.2e9:1.5e9:0.002:2 `
  --outside-band-weight 0.1 `
  --passivity enforce
```

上例中，完整频带 RMS 即使超过任一指定频段目标，也不会阻止输出。报告用 `full_band_rms_blocking: false` 和 `full_band_rms_target: null` 明确标记这种后检查模式，并把最终完整频带计算写入 `full_band_postcheck`。

显式传 `--rms-target 0.0025` 时进入全频段约束模式。程序分别生成原始全频段基线候选和优先频段候选；优先候选必须同时满足全频段及逐频段目标，并且所有指定频段都不劣于基线、至少一段严格改善，才会替换基线，否则回退到基线。`--rms-target` 只表示全频段门限，不替代任何频段自身的 RMS 目标。JSON 会记录 `priority_band_fit_mode`、`candidate_selection`、`full_band_rms_target`、`comparison_mean_rms_error`、`priority_band_targets_hz`、`outside_band_mean_rms_error` 和 `weighted_mean_rms_error`，并在 `frequency_band_metrics` 中记录每段目标、实测 RMS 和是否达标。

### 被动性策略

| `--passivity` 值 | 行为 |
| --- | --- |
| `off` | 只验证 RMS，不做被动性检查。 |
| `check`（默认） | 检查被动性；即使非被动，也会保留拟合产物，并在报告中标记警告。 |
| `enforce` | 仅接受同时满足 RMS 目标和被动性目标的最终模型。若修复被动性后 RMS 超标，则该阶次失败。 |

`enforce` 使用严格边界：验收范围、自适应频点和 `f -> infinity` 的常数矩阵 `D` 都必须满足 `sigma_max < 1`，不是 `1 + epsilon`。无优先频段或显式给出全频段目标时，验收范围是原始完整频带；仅给优先频段时，拟合精度与参考样本只约束指定频段，全频带结果不参与成败。如果有限频带已拟合良好但 `D` 非无源，程序会先严格投影 `D`，再固定已有极点、用共享 SVD 分块求解残数补偿，以保持验收范围内 RMS。大端口补偿后若只剩很小的局部超限，会优先使用 DC 保持微阻尼，而不是直接进入耗时的大规模 QP。

逐阶次日志会明确记录是否检测到非无源 D、补偿基大小和秩、RMS 前后值以及候选接受/拒绝原因。详细算法、跨端口实测和剩余性能工作见 [S 参数渐近无源补偿算法设计](docs/sparam-passivity-asymptotic-compensation-design.md)。

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
| `--log PATH` | `<输入名>.log`，位于 JSON 报告目录 | 写入逐阶次搜索摘要、渐近补偿过程、阶次、RMS、状态和失败原因。 |
| `--rms-target FLOAT` | 无优先频段时必填 | 全频段最终平均 S-RMS 上限。指定优先频段但省略本参数时，全频段只做非阻塞后检查；显式传入时，全频段与逐频段目标必须同时达标。 |
| `--priority-band F_MIN:F_MAX:RMS_TARGET[:WEIGHT]` | 不启用 | 优先拟合的闭区间，单位 Hz；可重复。每段必须携带正数 RMS 目标，默认段内权重为 `1`。 |
| `--outside-band-weight FLOAT` | `0.1` | 加权全频段候选中，优先频段以外的最小二乘权重，必须大于 `0`；需同时指定 `--priority-band` 和 `--rms-target` 才有实际作用。 |
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
| `--passivity-max-iterations N` | auto（通常 `3`；特定大端口快速预设为 `0`） | passivity enforcement 的最大修复轮数；`0` 表示不做修复轮。每轮会重新扫描原始频点，逐批处理窄带违规。 | 原始拟合 RMS 达标、但修复后仍有被动性违例时增加。 |
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
- `comparison_mean_rms_error`：全部原始频点上的全带 `mean_s_rms_v1`；未指定优先频段时也是目标判定值。
- `target_mean_rms_error`：实际用于目标搜索的 RMS；未指定优先频段时等于 `comparison_mean_rms_error`，指定后为优先频段并集 RMS。
- `passivity_max_sigma_after`：最终被动性最大奇异值。
- `constant_matrix_sigma`：RFM 渐近常数矩阵 D 的最大奇异值，严格验收时必须小于 `1`。
- `passivity_enforcement_diagnostics`：D 投影、固定极点补偿、DC 保持微阻尼和最终密集验证的可审计记录。
- `selected_effective_order`：选中的有效阶次。
- `order_trials`：搜索过程中的每个试探阶次及其结果。

失败时不会把最接近的模型当作成功交付：CLI 返回 `FAIL` 和非零退出码；若存在有限 RMS 候选，仍会导出 RMS 最低的诊断输出，并在 JSON/HTML 中标记为“最佳可得输出（未达目标）”。最终 JSON/HTML 会保留搜索记录，方便判断是最大阶次不足、RMS 未达标，还是被动性修复后 RMS 超标。

### 二端口级联拟合

多个二端口按明确顺序连接时，使用 `fit-sparam-cascade`。命令会逐块执行目标阶数搜索和 passivity enforcement，再在共同覆盖频段内统一参考阻抗、级联 fitted S 参数并检查整体最大奇异值；必要时在不突破各块 RMS 门限的前提下选择最小收缩修复。

```powershell
python -m agent_spice.cli fit-sparam-cascade .\cascade.json `
  --output-root .\cascade-fit `
  --rms-target 0.001 `
  --cascade-rms-target 0.002 `
  --max-order 80
```

`--rms-target` 是每个 block 的默认 RMS 门限；`--cascade-rms-target` 是最终级联模型的阻塞 RMS 门限。后者按报告中的 `evaluation_scope` 计算，未达标时即使所有 block 和级联被动性都通过，命令仍返回 `FAIL`。

当前稳定关系模型是 manifest 中的有序 2-port 链，不支持多端口任意连接图，也不做带外延拓。完整 manifest、产物、修复算法和失败语义见 [S 参数分频段与级联拟合使用说明](docs/sparam-band-cascade-usage.md)。

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

典型输出包括每个 case 的 `case.source.sp`、`case.cir`、兼容性报告，以及 `.alter` 展开后的独立目录。`case.source.sp` 永远保留用户输入的原始 case；`case.cir` 是 converter 处理后实际交给后端的网表。带相对 `.include` 或 `.lib` 的本地模型文件会按原相对路径暂存到 case 目录，并在目标为 ngspice 时递归转换，因此生成的网表可在该目录直接运行。

### ngspice 前置转换与 SIPI/PI 范围

选择 `--backend ngspice` 时，converter 是仿真前的固定步骤，而不是可选的格式化工具。它会扫描顶层网表和相对 include/lib 依赖，记录转换、阻断项和输出请求到 `compat_report.json`，再执行 `case.cir`。目前面向无源 SIPI/PI：R/L/C/K、传输线、理想 V/I 激励、PWL/PULSE/SIN/EXP、CPM/UPM、VRM/decap 与拟合后的 S 参数宏模型。

已处理的常见差异包括 `.inc -> .include`、`.probe -> .print`、`.alter` case 展开、Cadence/HSPICE 电流 PWL 的 `R=<time>` 重复语义，以及电流源/电容的 `M=<N>` 并联倍数。对于 ngspice 不存在等价物的输入，converter 必须在报告中阻断，不能静默删改。工艺有源模型、专有 `.model` 参数、Verilog-A、加密 PDK 不属于当前自动转换范围。

### 直接 S 参数实例的自动拟合

历史 HSPICE 网表可以使用 S 元件直接挂载 Touchstone，例如：

```spice
S1 pkg_in cpm_top 0 TSTONEFILE='package.s2p' TYPE=S
```

ngspice 不能将多端口 Touchstone 直接用于 `.tran`。在 ngspice 路径中，converter 会识别带 `TSTONEFILE=<*.sNp>` 的 S 元件，并自动执行：

```text
HSPICE S 元件 -> Touchstone 读取 -> auto fit (RMS=0.001, passivity=enforce)
-> 生成 SPICE 子电路 -> 替换为 X 子电路实例 -> ngspice TRAN
```

拟合产物位于每个 case 的 `sparam/` 目录，包括 `.sp`、拟合后的 Touchstone、JSON/HTML 报告和 `*.fit.log`。预处理日志会写入 `preflight.log`，执行时同样会出现在 `stdout.log`。拟合达到目标时会记录 `FIT_PASS`；未达到 `0.001` 但已有最低 RMS 候选时，仍使用该候选继续仿真，并记录 `FIT_FALLBACK_BEST_RMS`、实际 RMS、实例名和输出路径。没有任何可导出候选时才阻断。

当前自动映射要求 S 元件为最常见的公共地参考形式：`N` 个信号节点加末尾 `0` 参考节点。非公共地或端口数不匹配会报告阻断，避免错误连接。

快速核验示例：

```powershell
python -m agent_spice.cli run-hspice tests\fixtures\hspice\alter_pi.sp --output-root runs-smoke
Test-Path runs-smoke\alter_pi\alter_pi__base\case.cir
Test-Path runs-smoke\alter_pi\alter_pi__alter_001_high_decap\case.cir
```

指定 `--execute` 时，默认 `ngspice` 路径会额外生成：

- `stdout.log`、`stderr.log`：后端完整输出与诊断；
- `waveform.csv`：由 `.print` 输出解析出的波形；
- `run_summary.json`：退出码、日志索引、CSV 波形状态，以及已解析的 `.measure` 数值和失败信息。

例如：

```powershell
python -m agent_spice.cli run-hspice tests\fixtures\hspice\simple_pi.sp --output-root runs-pi --execute
Get-Content runs-pi\simple_pi\simple_pi__base\run_summary.json
```

Windows 离线生产默认只需 ngspice：`tools\install-solvers.ps1` 与 `tools\doctor-solvers.ps1 -Smoke` 均不会要求 Xyce 或 XDM。仅在显式选择 `--backend xyce-xdm` 时，才需要通过 `-IncludeXyce` 安装并检查这两个本地可选工具。

## 完整命令索引与研究命令

顶层 CLI 还包含 `probe-idem-*`、`fit-idem-like`、`fit-modal-z`、`benchmark-sparam`、`preflight-sparam-corpus` 和 `compare-sparam-bands` 等研究、诊断和基准命令。这些命令的参数面较大，且会随算法实验演进；使用前必须以当前版本的帮助为准：

```powershell
python -m agent_spice.cli --help
python -m agent_spice.cli benchmark-sparam --help
```

## 版本与范围

生产 S 参数拟合基线为 `native-idem-fast-v1`。Native 是唯一的生产拟合与 SPICE 导出路径；外部 IdEM 仅用于基准和研究，不是运行时依赖。scikit-rf 用于 Touchstone 读取回退、指标和研究辅助，不是可选择的生产拟合后端。

历史性能对比可参阅 [IdEM 全量基准](docs/sparam-idem-full-benchmark.md) 与 [S19 调优记录](docs/sparam-idem-s19-tuning.md)。
