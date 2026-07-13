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

## 4. 算法继承与本项目创新

| 类别 | 内容 |
| --- | --- |
| 理论基础 | Gustavsen–Semlyen 的 Vector Fitting、共享极点多响应有理近似、固定极点 residue LS。 |
| 被动性基础 | bounded-real 条件、最大奇异值检查、Hamiltonian 型定位、residue perturbation 与 NNLS/QP 类最小扰动。 |
| Native 的算法组织 | 将公共极点发现、固定极点 LS、被动性修复和全频矩阵验收放在同一质量契约中。 |
| Native 的工程创新 | 自适应阶数搜索与回填、effective-order 核验、FAIL 时 best-effort 导出、候选修复的 holdout 筛选、互易响应压缩、统一全频评估路径。 |
| 性能纪律 | 默认 BLAS 线程为 1，避免单个 dense fit 多层并行导致过度订阅；64 核环境更适合并发多个独立 fit 以提高吞吐。 |

准确边界：Native 的理论核心仍属于 VF 家族；当前并不声称已超过或复现商业 IdEM 的共享极点发现机制。已有 modal、Loewner、RKFIT、stabAAA、MFT-NNLS 等研究路线均未进入生产默认路径。

## 5. S 参数交付物与使用方式

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

## 6. PI 网表仿真：实验性功能

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

## 7. 交付状态总结

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| Native `fit-sparam` | 生产主线 | 已具备全频 RMS、被动性策略、SPICE/RFM 交付和可审计报告。 |
| IdEM | 研究/基准 | 仅用于能力对比，不是运行时依赖。 |
| PI 网表转换与 ngspice 执行 | 实验性 | 支持明确的无源 PI/SIPI 子集；需以 `compat_report.json` 和实际运行日志为准。 |
| Xyce/XDM | 可选实验性 | 仅显式选择时使用；不属于默认 Windows 离线链。 |
| 大规模 PDN/MPI、完整 HSPICE 兼容 | 未生产化 | 后续研究和工程化范围。 |

## 8. 参考资料

1. Gustavsen, B.; Semlyen, A. *Rational Approximation of Frequency Domain Responses by Vector Fitting*, IEEE Transactions on Power Delivery, 1999. DOI: https://doi.org/10.1109/61.772353
2. Gustavsen, B. *Fast Passivity Enforcement for S-Parameter Models by Perturbation of Residue Matrix Eigenvalues*, IEEE Transactions on Advanced Packaging, 2010. DOI: https://doi.org/10.1109/TADVP.2008.2010508
3. Gustavsen, B. *Passivity Enforcement by Residue Perturbation via Constrained Non-Negative Least Squares*, IEEE Transactions on Power Delivery, 2021. DOI: https://doi.org/10.1109/TPWRD.2020.3026385
4. 项目内详细算法报告：`docs/native-fit-algorithm-academic-report.md`
5. 项目内仿真器工具链说明：`docs/solver-toolchain.md`
