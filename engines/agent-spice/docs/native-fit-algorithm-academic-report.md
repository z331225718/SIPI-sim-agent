# Native S 参数宏建模算法：架构、继承与创新报告

日期：2026-07-13
版本：`native-idem-fast-v1`
范围：生产 `fit-sparam` 路径；不将 IdEM、modal-Z、Loewner、RKFIT、stabAAA 或 MFT-NNLS 试验路径描述为 Native 默认算法。

## 摘要

Agent-Spice Native 是一个面向仅有 Touchstone 频率采样的多端口 S 参数宏建模流程。它以**稳定共享极点的多响应 Vector Fitting（VF）**为近似核心，以全频矩阵 RMS 和 S 参数被动性为验收契约，并将自动阶数搜索、被动性检查/修复、SPICE/RFM 交付和质量审计组织为单一可复现实验链。

其目标模型为

$$
\hat S(s)=D+sE+\sum_{k=1}^{K}\frac{R_k}{s-p_k},\qquad \Re(p_k)<0,
$$

其中 $\hat S\in\mathbb{C}^{m\times m}$，所有 $m^2$ 个响应共用极点集合 $\{p_k\}$，而残差矩阵 $R_k$、常数项 $D$ 和可选比例项 $E$ 保留端口耦合。有效阶数定义为实极点数加两倍复极点对数。

本工作不是提出一种脱离 VF 的新有理逼近理论；其学术贡献更准确地说是：在公开 VF/被动宏模型框架中，针对大端口、频率采样型 S 参数交付场景，形成一套以**共享极点、全频质量契约、可审计失败输出和受限被动性修复**为中心的工程算法体系。

## 1. 问题定义与验收目标

输入为频率网格 $\{\omega_i\}_{i=1}^N$ 上的 S 参数样本 $S(j\omega_i)$。生产路径只拟合 S 参数，不把 S 转为 Z/Y 后作为默认建模域，避免低参考阻抗和 $I-S$ 接近奇异时的条件数风险。

主要拟合指标为全部频点和全部矩阵元素的均方根误差：

$$
\operatorname{RMS}(\hat S,S)=
\sqrt{\frac{1}{Nm^2}\sum_{i=1}^N\|\hat S(j\omega_i)-S(j\omega_i)\|_F^2}.
$$

若策略为 `passivity=enforce`，接受条件为 RMS 不超过用户目标，且模型的最大奇异值满足

$$
\max_{\omega\in\Omega}\sigma_{\max}(\hat S(j\omega))
\le 1+\epsilon.
$$

这里 $\Omega$ 包含自适应采样、全频验证和 Hamiltonian 型检查所确定的关键区间。因而，低 RMS 本身不等价于可交付模型。

## 2. 总体架构

```text
Touchstone S(jw)
  -> 轻量解析/网络校验、全频网格冻结
  -> 目标阶数搜索（低阶起步，按误差自适应跳步）
  -> 每个候选阶数：稳定共享极点 Native VF
       -> 多响应共同极点 relocation
       -> 固定极点全矩阵 residue LS
       -> 全频 RMS 与极点拓扑核验
       -> S 参数被动性检查
       -> 可选受限 residue/constant 修复与复核
  -> 选择最低通过阶数；若没有通过则选择 RMS 最优的 best-effort
  -> SPICE、RFM、fitted Touchstone、JSON、HTML、逐阶日志
```

实现边界分别位于：

| 层 | 主要模块 | 职责 |
| --- | --- | --- |
| 输入和交付 | `fitting.py`、`artifacts.py` | Touchstone、拟合编排、SPICE/RFM/Touchstone 输出、JSON/HTML 报告。 |
| 有理近似核心 | `native_vf.py`、`pole_relocation.py` | 共享极点初始化、SK/VF relocation、稳定性/共轭结构、固定极点 residue LS。 |
| 阶数决策 | `target_fit.py` | 自适应阶数试探、回填临界区间、最低有效阶次选择、FAIL 时 best-effort 选择。 |
| 被动性 | `passivity.py` | 奇异值采样、Hamiltonian 检查、违规模态、受限残差/常数扰动、候选筛选和回退。 |
| 质量与性能 | `quality.py`、`performance.py` | signoff/explore 质量诊断、全频评价、资源与 BLAS 线程约束。 |

## 3. 核心拟合算法

### 3.1 共享极点多响应 VF

Native 使用公共分母的多响应 VF。给定当前极点 $a_k$，在每次 relocation 中构造 SK 型线性最小二乘问题，求解分子系数和辅助分母系数，再由辅助分母零点更新极点。所有矩阵元素同时参与极点更新，因此形成的不是 $m^2$ 个独立标量模型，而是一个共享极点、矩阵残差的模型。

极点初始化可为线性分布、对数分布或残差共振 seed；默认生产 auto 采用保守的线性布局。复极点以共轭结构保存，出现右半平面极点时按稳定性约束处理。频率按均值归一化以改善线性系统尺度。

在矩阵互易结构可用时，relocation 会压缩冗余响应并以 multiplicity 保留其权重；这是减少大端口公共极点搜索成本的关键实现策略，而不是改变拟合目标。

### 3.2 固定极点残差最小二乘

完成 relocation 后，算法以最终极点固定，重新对全部 $m^2$ 通道进行 residue/constant/proportional 系数求解。DC 约束可被显式纳入该线性问题。此分离符合 VF 的经典思想：非线性的难点集中在公共分母，给定极点后的分子求解保持线性。

### 3.3 自动阶数搜索与选择

生产 CLI 不把一次 VF 的内部 `auto_fit` 直接当作最终决策，而是外层按有效阶数做目标驱动搜索：默认从 order 4 起步；当 RMS 与目标相差很大时增加步长，接近目标时使用更小步长；发现首个通过点后，回填此前失败点与首个通过点之间的阶数，并选择有效阶数最小的通过模型。

这是一种**质量约束下的离散模型阶数选择**，而非假定误差严格单调的二分法。若直到 `max_order` 仍失败，流程仍输出 RMS 最优 trial 的完整产物，并以 `FAIL` 退出，从而避免“无可审计输出的长时间失败”。

## 4. 被动性层：检查优先、修复受限

被动性层分三步：

1. **定位**：流式批量计算 $\sigma_{\max}$，结合 Hamiltonian/state-space 检查确定违规区间和候选频点。
2. **低扰动修复**：主要调整 residue 与常数项；可构造针对违规奇异向量的 active-mode 灵敏度系统，并用 QP/NNLS 类最小范数或参考误差正则化子问题生成候选。
3. **拒绝劣化候选**：每个候选都经过违规点、reference holdout、全频 RMS 和 sigma 回归门；必要时尝试有限的全局/选择性阻尼回退。只有同时满足误差与被动性契约的候选才可交付。

这里的创新不应表述为“发明了被动性 enforcement”。经典的 residue perturbation、Hamiltonian assessment 与最小扰动思想已有充分先例。Native 的区别是将它们置于全频 RMS 保留、活动变量预算、候选筛选与可报告拒绝原因的产品级闭环中。

## 5. 借鉴关系

| Native 组件 | 主要借鉴 | 本项目的落地方式 |
| --- | --- | --- |
| 共享极点有理模型、SK relocation | Gustavsen–Semlyen Vector Fitting | 对 S 矩阵全响应联合拟合，显式稳定/共轭结构，最后固定极点 residue LS。 |
| 初始极点与复极点处理 | VF 的线性/对数/共振初值传统 | 对困难输入开放 `lin/log/resonance`，但默认保持保守生产路径。 |
| 被动性验证 | bounded-real 条件、Hamiltonian 型定位、最大奇异值 | 采样与 Hamiltonian 两类证据并存，输出 sigma 与违规区间。 |
| residue perturbation / NNLS 思想 | FRP、NNLS passivity enforcement | 仅作为受限修复候选，不把局部 sigma 降低误判为模型通过。 |
| 低阶选择 | 误差约束模型选择 | 外层离散 target search，RMS、被动性和有效阶数共同参与接受。 |

## 6. 本次 Native 的创新点

### 6.1 算法级创新

1. **端到端的“公共极点质量契约”**：将公共极点发现、全矩阵 residue LS、被动性修复和最终全频 RMS 放在同一接受链。极点候选即使局部 residual 或内部拟合分数较好，也必须经过最终矩阵级验收。
2. **被动性修复的多候选、留出频带决策**：不接受单一 QP/投影结果；使用 active-mode、reference regularization、扰动预算、频带 holdout 和全频回验选择候选，显式约束“压 sigma 换来 RMS 崩坏”。
3. **共享极点 relocation 的结构压缩**：针对互易 MIMO 数据预压缩响应并保留 multiplicity，使极点 relocation 的统计目标保持不变而减少冗余计算。
4. **有效阶数一致性核验**：请求阶数、极点拓扑和实际 effective order 必须一致；不将“请求了低阶、实际导出更高阶”的结果记为低阶成功。

### 6.2 工程与可复现性创新

1. **目标驱动自适应阶数搜索**：以产品 RMS/passivity 门驱动，而非依赖内部 auto-fit 的停止条件；首个通过后回填临界区间。
2. **失败也导出最佳模型**：`max_order` 耗尽时输出 best-effort 文件、逐阶报告和明确 CLI `FAIL`，便于诊断和后续专家调参。
3. **单一全频评估路径**：拟合、报告、RMS、最终 Touchstone 与交付模型采用同一模型表达式，避免逐端口评价造成的重复计算与指标漂移。
4. **性能纪律**：默认将 BLAS 线程固定为 1，避免单任务多层并行过度订阅；64 核环境通过进程级并发多个独立 fit 获得吞吐提升，而不是假设单个 dense LS 会线性加速。
5. **受控专家参数**：只公开初始极点布局、VF 轮数、高频复极点预算及被动性预算等白名单；默认 auto 不因专家接口存在而改变。

## 7. 已证伪或未进入默认路径的方向

这些实验是研究资产，不是 Native 默认能力：高频 pole injection/weight sweep、data-only pole dictionary、全局模态 initializer、stabAAA、Tangential Loewner、RKFIT、MFT-NNLS 与 modal-Z。综合实验证据表明，它们尚未在固定阶数、全矩阵 S-RMS 与被动性闭环上优于生产 Native，因此不应在论文或产品说明中写成“Native 已采用”。详细证据见 [算法研究总复盘](sparam-algorithm-research-retrospective.md)。

特别地，source-attribution 已支持如下工程判断：给定 IdEM 产生的极点，本地 residue LS 与 enforcement 可以形成合格模型；而以 Native 极点开始的同一后半链路明显更差。因此当前性能差距主要位于**稳定而紧凑的 MIMO 共享极点发现**，并非仅靠增加 enforcement 轮数可消除。

## 8. 局限性与准确表述

1. Native 的理论核心仍是 VF 家族；不应声称在公共极点发现上已经超过或复现 IdEM。
2. 被动性修复是安全网，不保证能从错误极点集合恢复缺失动态；修复后 RMS 超标的 trial 仍为失败。
3. 大端口问题的主成本来自 dense linear algebra、全频矩阵评价和被动性候选验证；Python 是编排层与部分数值实现，并非“改用另一语言即可线性加速”的充分解释。
4. `--min-order` 只适用于已验证相同输入的重复运行，不能作为未知输入的通用阶数预测。
5. 交付结论必须以输入 hash、全频点、RMS 定义、被动性策略、实际 effective order 和最终 artifact 为准。

## 9. 复现命令与报告证据

```powershell
python -m agent_spice.cli fit-sparam .\board.s19p `
  --rms-target 0.001 `
  --passivity enforce `
  --max-order 100
```

输出 `*_fitted.sp`、`*_fitted.sNp`、`*_fitted.rfm`、JSON/HTML 报告和逐阶 log。JSON 中应检查 `status`、`order_trials`、`comparison_mean_rms_error`、`passivity_max_sigma_after`、`expanded_model_order` 与 `best_effort_exported`。

相关仓库证据：

- [Native 与 IdEM 完整基准](sparam-idem-full-benchmark.md)
- [算法研究总复盘](sparam-algorithm-research-retrospective.md)
- [Native 单任务性能结果](sparam-native-single-fit-50pct.md)
- [Native 线程性能结论](sparam-native-64core-performance.md)
- [质量门计划](sparam-quality-gate-plan.md)

## 参考文献

1. B. Gustavsen, A. Semlyen, “Rational Approximation of Frequency Domain Responses by Vector Fitting,” *IEEE Transactions on Power Delivery*, 14(3), 1052–1061, 1999. DOI: [10.1109/61.772353](https://doi.org/10.1109/61.772353).
2. B. Gustavsen, “Fast Passivity Enforcement for S-Parameter Models by Perturbation of Residue Matrix Eigenvalues,” *IEEE Transactions on Advanced Packaging*, 33(1), 257–265, 2010. DOI: [10.1109/TADVP.2008.2010508](https://doi.org/10.1109/TADVP.2008.2010508).
3. B. Gustavsen, “Passivity Enforcement by Residue Perturbation via Constrained Non-Negative Least Squares,” *IEEE Transactions on Power Delivery*, 36(5), 2758–2766, 2021. DOI: [10.1109/TPWRD.2020.3026385](https://doi.org/10.1109/TPWRD.2020.3026385).
4. D. Deschrijver, T. Dhaene, “Fast Passivity Enforcement Technique for Common-Pole S-Parameter Multiport Systems,” *IEEE Workshop on Signal Propagation on Interconnects*, 2009.
