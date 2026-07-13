# Agent-Spice：S 参数宏建模与实验性 PI 网表仿真

> 页面定位：项目技术总览。本文可直接导入或粘贴到 Confluence；算法细节以《Native S 参数宏建模算法：架构、继承与创新报告》为准。

## 1. 项目概述

Agent-Spice 面向 SI/PI 工作流中的两类任务：

1. **S 参数宏建模（生产主线）**：将 Touchstone 多端口 S 参数拟合为稳定、可检查被动性、可供 SPICE 瞬态仿真的有理宏模型，并导出 SPICE、RFM、拟合后的 Touchstone 和机器可读质量报告。
2. **PI 网表仿真（实验性功能）**：读取常见 HSPICE 风格 PI 网表，展开 `.alter`，转换为 ngspice 可执行网表，运行 DC/AC/TRAN 并归档波形和日志。该功能当前仅适合受支持的无源 SIPI/PI 子集与回归/验证用途，**不应视为完整 HSPICE 兼容器或大规模生产求解器**。

S 参数拟合生产基线为 `native-idem-fast-v1`。外部 IdEM 仅用于研究基准和对照，不是运行时依赖。

## 2. S 参数宏建模：问题与目标模型

输入是频率采样的 $m$ 端口 S 参数 $S(j\omega_i)$，输出使用共享极点的矩阵有理模型：

$$
\hat S(s)=D+sE+\sum_{k=1}^{K}\frac{R_k}{s-p_k},\qquad \Re(p_k)<0.
$$

其中：

- 所有 $m^2$ 个 S 参数响应共享同一极点集合 $\{p_k\}$；
- 每个极点对应矩阵残差 $R_k$，因而保留端口间耦合；
- $D$ 为常数项，$E$ 为可选比例项；
- 有效阶数为实极点数加两倍复极点对数。

生产验收不是仅看局部曲线，而是在**全部原始频点、全部 S 参数元素**上评价：

$$
\operatorname{RMS}=\sqrt{\frac{1}{Nm^2}\sum_{i=1}^N\|\hat S(j\omega_i)-S(j\omega_i)\|_F^2}.
$$

当要求 `passivity=enforce` 时，还必须满足

$$
\max_{\omega}\sigma_{\max}(\hat S(j\omega))\le 1+\epsilon.
$$

因此，低 RMS 但不被动的模型，或修复被动性后 RMS 超标的模型，均不被视为通过。

## 3. Native Fit 算法架构

```text
Touchstone S(jw)
  -> 输入校验与全频网格冻结
  -> 目标驱动的有效阶数搜索
  -> 每个候选阶数：共享极点多响应 Vector Fitting
       -> 公共极点 relocation
       -> 固定极点全矩阵 residue least squares
       -> 全频 RMS、极点拓扑与稳定性核验
       -> S 参数被动性检查
       -> 可选的受限 residue/constant 修复与全频复核
  -> 选择最低通过阶数
  -> 导出 SPICE / RFM / fitted Touchstone / JSON / HTML / log
```

实现模块边界如下：

| 层 | 主要模块 | 职责 |
| --- | --- | --- |
| 输入和交付 | `fitting.py`、`artifacts.py` | Touchstone、拟合编排、SPICE/RFM/Touchstone 输出、JSON/HTML 报告。 |
| 有理近似核心 | `native_vf.py`、`pole_relocation.py` | 共享极点初始化、SK/VF relocation、稳定性/共轭结构、固定极点 residue LS。 |
| 阶数决策 | `target_fit.py` | 自适应阶数试探、临界区间回填、最低有效阶次选择、FAIL 时 best-effort 选择。 |
| 被动性 | `passivity.py` | 奇异值采样、Hamiltonian 检查、违规模态、受限 residue/constant 扰动、候选筛选和回退。 |
| 质量和性能 | `quality.py`、`performance.py` | signoff/explore 质量诊断、全频评价、资源与 BLAS 线程约束。 |

### 3.1 共享极点多响应 Vector Fitting

核心近似算法是 Vector Fitting（VF）。每轮在当前公共极点下构造 Sanathanan-Koerner 型线性最小二乘问题，求得辅助分母，然后由其零点更新极点。全部矩阵元素共同参与极点 relocation，因此输出是一个公共分母的 MIMO 宏模型，而不是 $m^2$ 个彼此无关的标量拟合。

初始极点支持线性、对数和基于残差共振的布局；默认 auto 保持保守的线性策略。复极点以共轭结构处理，频率归一化用于改善数值尺度。对可利用互易结构的数据，relocation 预压缩冗余响应并保留 multiplicity 权重，以降低大端口计算量而不改变拟合目标。

### 3.2 固定极点 residue LS

极点 relocation 完成后，极点固定，再在全部响应上求解 residue、常数项和可选比例项。非线性的公共分母搜索与线性的分子系数求解因此被分开处理；DC 约束可被纳入此阶段。

### 3.3 目标驱动的阶数搜索

CLI 从低阶开始试探。误差远高于目标时扩大阶数步长；接近目标时缩小步长。发现首个通过阶数后，回填前一个失败阶数与首个通过阶数之间的候选，最终选择**有效阶数最小**的通过模型。

若达到 `max-order` 仍不能满足契约，系统不会静默失败：它会导出 RMS 最优的 best-effort 模型与完整 JSON/HTML/逐阶日志，并返回明确的 `FAIL`。这使用户能区分“最大阶数不足”“RMS 不达标”和“被动性修复后退化”。

### 3.4 被动性检查与受限修复

被动性层由三个环节组成：

1. **违规定位**：流式计算最大奇异值，结合 Hamiltonian/state-space 检查定位违规频带与关键频点。
2. **低扰动候选生成**：主要对 residue 与常数项施加受限扰动；可使用违规奇异模态的灵敏度、QP/NNLS 类最小范数子问题、参考误差正则化等方式。
3. **候选筛选与回验**：候选必须通过违规频点、reference holdout、全频 RMS 和 sigma 回归门；必要时才使用有限的全局或选择性阻尼回退。

该机制的原则是：被动性修复是安全网，不是用来掩盖错误极点集合的手段。

## 4. 理论继承与差异化设计

| 类别 | 内容 |
| --- | --- |
| 理论基础 | Gustavsen–Semlyen 的 Vector Fitting、共享极点多响应有理近似、固定极点 residue LS。 |
| 被动性基础 | bounded-real 条件、最大奇异值检查、Hamiltonian 型定位、residue perturbation 与 NNLS/QP 类最小扰动。 |

### 4.1 差异化创新组合

以下内容是本项目的差异化实现重点。它们是在公开 VF 与无源性理论基础上的系统集成和约束设计。

1. **端到端公共极点质量契约**：将共享极点发现、全矩阵固定极点 LS、被动性修复和最终全频 RMS 置于同一接受链。局部 residual、内部拟合分数或局部 sigma 的改善不能独立构成成功。
2. **被动性修复的多候选与留出频带决策**：不接受单一 QP/投影输出；围绕违规奇异模态生成 candidate，以 reference regularization、活动变量预算、扰动预算、频带 holdout 和全频回验共同决定接受，明确限制“压 sigma 换来 RMS 崩坏”。
3. **互易 MIMO relocation 的等价结构压缩**：对冗余响应预压缩，同时保留 multiplicity，目标是在不改变联合极点搜索统计目标的前提下减少计算量。
4. **阶数与拓扑的可审计一致性**：请求阶数、实/复极点拓扑和实际 effective order 必须一致；禁止将“请求低阶、实际导出更高阶”的结果计为低阶成功。
5. **质量约束下的离散阶数选择**：以 RMS、被动性和 effective order 而非内部 VF 停止信号决定最终模型；跨越目标后回填临界区间，降低非单调误差造成的错误低阶结论。
6. **失败仍可交付诊断资产**：最大阶数耗尽时自动导出 best-effort 模型和完整 provenance，同时 CLI 明确返回 `FAIL`，将可用诊断产物与生产接受状态严格分离。
7. **统一模型表达式的全频评价**：拟合评价、RMS、HTML 图表、最终 Touchstone 和导出模型由同一有理模型表达式产生，避免逐端口调用或不同评估路径造成的性能重复与指标漂移。

## 5. 研究结论、局限性与可审计性

### 5.1 研究结论

现有 source-attribution 结果支持如下工程判断：给定 IdEM 产生的极点，本地固定极点 residue LS 与 enforcement 能形成合格模型；以 Native 极点开始的相同后半链路则明显更差。因此当前剩余差距主要在**稳定、紧凑且适合矩阵值数据的共享极点发现**，不是单纯增加 residue solver 或 enforcement 旋钮能够消除的问题。

高频 pole injection/weight sweep、data-only pole dictionary、全局 modal initializer、stabAAA、Tangential Loewner、RKFIT、MFT-NNLS 与 modal-Z 均是已运行的研究资产，但未在固定阶数、全矩阵 S-RMS 和被动性闭环上优于生产 Native；不得在产品介绍中写成 Native 默认能力。

### 5.2 局限性

1. Native 的理论核心仍是 VF，不应声称已在公共极点发现上超过或复现 IdEM；modal、Loewner、RKFIT、stabAAA、MFT-NNLS 等研究路线均未进入生产默认路径。
2. 被动性修复是安全网，不保证从错误极点集合恢复缺失动态；修复后 RMS 超标的 trial 仍为失败。
3. 大端口成本主要来自 dense linear algebra、全频矩阵评价和被动性候选验证；Python 是编排层和部分数值实现，替换语言本身不保证线性加速。
4. `--min-order` 仅适用于同一输入、已有完整验证的重复运行，不能作为未知输入的通用阶数预测器。
5. 所有结论必须绑定输入 hash、全频点、RMS 定义、被动性策略、实际 effective order 和最终 artifact。

### 5.3 质量报告审计字段

JSON 报告应至少核验：`status`、`order_trials`、`comparison_mean_rms_error`、`passivity_max_sigma_after`、`expanded_model_order`、`best_effort_exported` 和实际输出路径。交付物只有在 `PASS` 且所选被动性策略对应的门全部满足时，才可视为生产接受模型。

## 6. S 参数交付物与使用方式

```powershell
python -m agent_spice.cli fit-sparam .\board.s19p `
  --rms-target 0.001 `
  --passivity enforce `
  --max-order 100
```

典型输出：

| 文件 | 用途 |
| --- | --- |
| `board_fitted.sp` | 可用于 SPICE 的 Native 子电路。 |
| `board_fitted.s19p` | 拟合后的 Touchstone，用于外部核验。 |
| `board_fitted.rfm` 与 wrapper | RFM 模型及引用网表。 |
| `board_fitted_report.json` | 机器可读的 RMS、阶数、被动性、配置和路径。 |
| `board_fitted_report.html` | 中文质量报告与主要误差元素。 |
| `board.log` | 按阶数搜索的过程记录。 |

对于特殊难例，可通过受控专家参数调整初始极点布局、VF 轮数、高频复极点预算和被动性预算。未传专家参数时，默认 auto 行为不变。

### 6.1 开放调试接口与 Agent 协作

相较于商业黑盒拟合器，Native 的优势不只在于可以替换算法实现，也在于将关键诊断和调节面以稳定接口显化：每次 trial 的阶数、极点拓扑、RMS、最大奇异值、被动性修复结果、耗时、配置和拒绝原因都会写入 JSON、HTML 与日志。工程人员可以据此定位问题，而不是仅得到“成功/失败”结果。

公开的专家参数采用白名单控制，覆盖初始极点布局、VF relocation 轮数、高频复极点预算、无源性修复轮数、违规采样数和活动变量预算。它们不会改变默认 auto 的质量契约；每个覆盖值都会写入 `tuning_overrides` 和 `effective_base_config`，因而可以复现、审计和回退。

项目还提供 `sparam-fit-tuning` Agent skill，可供 Codex、Claude Code 等具备本地文件与命令执行能力的 Agent 使用。该 skill 读取 auto fit 的 JSON/HTML/log，将失败分类为阶数不足、极点初始化不足、relocation 未收敛或被动性修复冲突；随后只在公开白名单内提出并运行少量单变量候选，保留原始 artifact，最终以同一 RMS/passivity 契约判定 `PASS/FAIL`。它不允许通过降低 RMS 目标、关闭被动性或降采样来伪造通过结果。

这种“算法可观测性 + 受控调参接口 + Agent 诊断工作流”的组合，使项目在**可调试性、可扩展性和自动化调优空间**上具有明显优势；这不等同于宣称所有输入上的拟合精度或速度都高于商业软件。

## 7. PI 网表仿真：实验性功能

### 6.1 定位与默认后端

PI 网表仿真当前标记为**实验性功能**。默认后端是 **ngspice 46**，适用于快速本地验证、smoke test 和受支持无源 PI/SIPI 网表的 DC/AC/TRAN 分析。Windows 离线环境默认只需安装 ngspice；Xyce 和 XDM 是本地可选工具，不是默认安装或默认执行依赖。

```text
HSPICE 风格网表
  -> include/lib 发现、.alter 展开
  -> HSPICE 到 ngspice 的受限转换与兼容性报告
  -> 可执行 case.cir
  -> ngspice batch execution
  -> stdout/stderr、waveform.csv、measure、run_summary.json
```

### 6.2 支持范围

当前 converter 面向无源 SIPI/PI 子集，包括：

- R/L/C/K、传输线；
- 理想 V/I 激励及 PWL/PULSE/SIN/EXP；
- CPM/UPM、VRM/decap；
- 相对 `.include`/`.lib` 依赖；
- `.alter` case 展开；
- 拟合后的 S 参数 SPICE 宏模型。

已处理的典型语法差异包括 `.inc -> .include`、`.probe -> .print`、Cadence/HSPICE 电流 PWL 的 `R=<time>` 重复语义，以及电流源/电容的 `M=<N>` 并联倍数。

对于没有明确 ngspice 等价物的内容，流程必须在 `compat_report.json` 中阻断，而不是静默删改。

### 6.3 不支持或尚未生产化的范围

- 工艺 MOS/BJT/二极管模型及专有 `.model` 参数；
- Verilog-A、加密 PDK、HSPICE 专有有源器件模型；
- 完整 HSPICE 语言/语义兼容；
- ngspice 原生多端口 Touchstone 瞬态卷积；
- 大规模 PDN 的性能、收敛性和跨求解器一致性签核；
- Xyce MPI 规模化后端的生产化验证。

因此，PI 仿真当前的正确使用方式是：将它视为可审计的网表预处理和 ngspice 验证链，而不是替代成熟商业 PI/PDN 仿真平台。

### 6.4 网表中的 S 参数元件

ngspice 不能把多端口 Touchstone 直接作为 transient 元件使用。若 HSPICE 风格网表出现引用 `TSTONEFILE=<*.sNp>` 的 S 元件，实验性流程将自动执行：

```text
HSPICE S 元件
  -> Touchstone 读取
  -> Native auto fit（RMS=0.001, passivity=enforce）
  -> 生成 SPICE 子电路
  -> 替换为 X 子电路实例
  -> ngspice TRAN
```

每个 case 的 `sparam/` 目录会保留拟合 SPICE、fitted Touchstone、JSON/HTML 报告和拟合 log。达到目标时记录 `FIT_PASS`；若没有达到目标但存在可导出的 best-effort 模型，则记录 `FIT_FALLBACK_BEST_RMS` 并继续仿真。无任何可导出候选时才阻断。

### 6.5 命令与输出

仅生成转换结果，不执行求解器：

```powershell
python -m agent_spice.cli run-hspice .\design.sp `
  --backend ngspice `
  --output-root .\runs
```

执行 ngspice：

```powershell
python -m agent_spice.cli run-hspice .\design.sp `
  --backend ngspice `
  --output-root .\runs `
  --execute
```

每个展开 case 的典型输出：

| 文件 | 含义 |
| --- | --- |
| `case.source.sp` | 原始 case 网表快照。 |
| `case.cir` | 实际交给 ngspice 的转换后网表。 |
| `compat_report.json` | 支持、转换、警告和阻断项。 |
| `stdout.log` / `stderr.log` | 求解器完整输出。 |
| `waveform.csv` | 从 `.print` 输出解析的可移植波形。 |
| `run_summary.json` | 退出码、日志索引、波形状态、`.measure` 结果和错误信息。 |

## 8. 交付状态总结

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| Native `fit-sparam` | 生产主线 | 已具备全频 RMS、被动性策略、SPICE/RFM 交付和可审计报告。 |
| IdEM | 研究/基准 | 仅用于能力对比，不是运行时依赖。 |
| PI 网表转换与 ngspice 执行 | 实验性 | 支持明确的无源 PI/SIPI 子集；需以 `compat_report.json` 和实际运行日志为准。 |
| Xyce/XDM | 可选实验性 | 仅显式选择时使用；不属于默认 Windows 离线链。 |
| 大规模 PDN/MPI、完整 HSPICE 兼容 | 未生产化 | 后续研究和工程化范围。 |

## 9. 参考资料

1. Gustavsen, B.; Semlyen, A. *Rational Approximation of Frequency Domain Responses by Vector Fitting*, IEEE Transactions on Power Delivery, 1999. DOI: https://doi.org/10.1109/61.772353
2. Gustavsen, B. *Fast Passivity Enforcement for S-Parameter Models by Perturbation of Residue Matrix Eigenvalues*, IEEE Transactions on Advanced Packaging, 2010. DOI: https://doi.org/10.1109/TADVP.2008.2010508
3. Gustavsen, B. *Passivity Enforcement by Residue Perturbation via Constrained Non-Negative Least Squares*, IEEE Transactions on Power Delivery, 2021. DOI: https://doi.org/10.1109/TPWRD.2020.3026385
4. 项目内独立学术报告：`docs/native-fit-algorithm-academic-report.md`，用于文献核对和技术写作。
5. 项目内仿真器工具链说明：`docs/solver-toolchain.md`
