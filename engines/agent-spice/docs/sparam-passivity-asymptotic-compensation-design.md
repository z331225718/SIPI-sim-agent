# S 参数渐近无源补偿算法设计

日期：2026-07-14
状态：算法与导出 RFM 重读功能签核完成；大端口性能优化按当前决策暂缓
范围：Native S 参数模型的 passivity enforcement；不修改极点拟合、极点重定位和 S 参数拟合目标。

## 1. 摘要

当前 Native 模型可以在原始 Touchstone 频带内达到较低 RMS，并通过有限频带奇异值检查，但常数矩阵 `D` 可能在 `f -> infinity` 时不满足严格无源性。直接投影 `D` 会破坏 `D` 与动态残数之间的抵消；对整个模型做 uniform damping 虽然能够使模型无源，却可能显著破坏有限频带 RMS。

本设计采用两阶段修复：

1. 将 `D` 严格投影到 `sigma_max(D) < 1`。
2. 固定已有极点，通过多右端残数最小二乘补偿 `D` 的变化，使有限频带响应尽量保持不变。

补偿后继续使用现有 active-mode residue QP 修复局部有限频带违规，最后统一验证原始频点、自适应频点、Hamiltonian 交叉点和渐近 `D`。任何候选只有在严格无源并满足最终 RMS 目标时才能 PASS。

## 2. 现状与证据

### 2.1 跨端口实测基线

| 样本 | 场景 | 修复或检查结果 | RMS | 核心耗时 | 结论 |
| --- | --- | ---: | ---: | ---: | --- |
| S2P | 完整 CLI | `sigma_max=0.8099998` | `9.67e-9` | enforce `0.0033 s` | 无源通过；fixture 有 DC coverage 警告。 |
| S30P | 非无源 RFM 修复 | `1.00001267 -> 0.99999905` | `0.00094704` | 三轮约 `795 s` | 质量通过，但修复偏慢。 |
| S30P | 已修复模型复验 | `0.99999905` | `0.00094704` | `67.18 s` | 严格通过。 |
| S60P | order 8 完整拟合 | `D sigma=2.3133 -> 0.9999989` | `0.000516 -> 0.070694` | 总计约 `21.75 s` | 无源通过，但 RMS 严重失败。 |
| S163P | 已有 Native RFM 复验 | `0.9999989` | `0.00019740` | `21.75 s` | 严格通过。 |
| S166P | 已有 Native RFM 复验 | `0.99999791` | `0.00027066` | `17.24 s` | 严格通过。 |

上表是实施前基线。后续审计确认当时 S163P/S166P 的有限频带检查虽然通过，但导出 RFM 的 `D` 分别为 `1.10889` 和 `1.11045`，因此不能视为完整严格无源；这也是本次实现必须修复的漏检。

验证产物位于 `runs/passivity-cross-port-20260714/`。S163P/S166P 是已有拟合模型的严格复验，不包含重新拟合时间。

### 2.2 已确认的问题

1. 稀疏外围检查可能漏掉原始频点上的窄带违规，不能覆盖 enforcer 的密集最终验证。
2. 残数灵敏度在 SI 频率尺度下可能很小，未经归一化的对偶 QP 会把零步长误报为成功。
3. `D` 单独投影会破坏动态模型中 `D` 与残数的有限频带抵消。
4. uniform damping 同时缩放 `D` 和全部残数，能够保证无源，但可能让 RMS 超出目标数十倍。
5. 大端口模型如果在 RMS 达标后仍因渐近门反复提高阶次，会造成无意义的长时间搜索。
6. 最终签核必须要求严格 `sigma < 1`，不能用 `1 + epsilon` 作为生产接受边界。

## 3. 目标与非目标

### 3.1 目标

- 有限频带和 `f -> infinity` 均严格满足 `sigma_max < 1`。
- 最终全矩阵 mean S-RMS 不超过用户的 `--rms-target`。
- 保持极点稳定、共轭结构和 RFM/SPICE 可导出性。
- `preserve_dc=True` 时保持 DC 响应。
- 大端口实现使用共享基矩阵和分块多右端求解，避免端口平方规模的重复分解。
- 修复失败时保留可审计的原始模型或最佳候选，不把 RMS 回退模型标记为 PASS。
- 日志和 JSON/HTML 报告能够解释修复路径、耗时和失败原因。

### 3.2 非目标

- 不修改 Native VF 的极点初始化、极点重定位或阶数搜索核心。
- 不修改 `fit-sparam` 的 RMS 定义。
- 不引入 IdEM、Xyce/XDM 或在线依赖。
- 第一阶段不自动增加补偿极点。
- 不修改 S 参数拟合以外的器件级模型或有源器件算法。

## 4. 模型和严格验收契约

Native 模型写为：

$$
\hat S(s)=D+\sum_{k=1}^{K}\frac{R_k}{s-p_k},\qquad \Re(p_k)<0.
$$

本阶段不处理比例项 `sE`；生产 RFM 也不允许非零比例项。

严格无源接受条件为：

$$
\max\left(
\sup_{\omega\in\Omega}\sigma_{\max}(\hat S(j\omega)),
\sigma_{\max}(D)
\right)<1.
$$

其中 `Omega` 至少包含：

- 原始 Touchstone 全频点；
- Hamiltonian 交叉频率；
- 自适应区间采样点；
- 局部曲率和峰值细化点。

数值修复目标使用：

$$
\sigma_{target}=1-\mu,
$$

其中 `mu` 至少为 `max_passivity_epsilon`，默认目标为 `0.999999`。`epsilon` 是修复安全裕量，不是允许超过 1 的验收公差。

最终质量门同时要求：

$$
\operatorname{RMS}(\hat S,S_{input})\le \texttt{rms_target}.
$$

## 5. 渐近 D 投影

对常数矩阵做奇异值分解：

$$
D=U\Sigma V^H.
$$

构造严格无源常数矩阵：

$$
D'=U\operatorname{diag}(\min(\sigma_i,1-\mu))V^H.
$$

定义需要由动态项补偿的矩阵：

$$
C=D-D'.
$$

纯常数模型可以直接使用 `D'`。只要模型包含动态极点，就不能在没有有限频带补偿和 RMS 验证的情况下单独接受 `D'`。

## 6. 固定极点残数补偿

### 6.1 补偿目标

希望新模型在有限频带保持原响应：

$$
D'+\Phi(j\omega)(R+\Delta R)
\approx
D+\Phi(j\omega)R.
$$

因此：

$$
\Phi(j\omega)\Delta R\approx C.
$$

对每个 S 参数响应 `(i,j)`，右端 `C_ij` 在所有参考频点上是同一个复常数。极点集合对所有响应共享，所以左端基矩阵只需要构造和分解一次。

### 6.2 实数化共轭基

残数变量必须与当前 Native/RFM 表示一致：

- 实极点对应一个实残数变量。
- 每个复共轭极点对对应残数的实部和虚部两个实变量。
- 复共轭成员不作为独立自由变量。

对参考频点构造复基矩阵后，将实部和虚部按行堆叠为实数系统：

$$
A\,x_{ij}\approx b_{ij}.
$$

`A` 的列数只与有效极点阶数有关，所有 `m^2` 个响应共享同一个 `A`。实现不得构造 `(frequency * m^2) x (order * m^2)` 的整体稠密矩阵。

### 6.3 目标函数

补偿求解采用带正则化的加权最小二乘：

$$
\min_X
\|W_f(A X-B)\|_F^2
+\lambda\|W_r X\|_F^2.
$$

其中：

- `X` 包含一批响应的残数补偿变量。
- `B` 是由 `C` 生成的多右端矩阵。
- `W_f` 默认保持当前原始频点 RMS 的等权定义。
- `W_r` 用于避免利用极小灵敏度产生过大的残数。
- `lambda` 使用少量归一化候选，由最终 RMS、残数扰动和 passivity 共同选择。

第一版候选集合应保持小而确定，例如归一化后的 `0`、`1e-12`、`1e-10`、`1e-8`、`1e-6`。具体尺度必须根据 `A` 的列范数归一化，不能直接作用于 SI 量纲的原始矩阵。

### 6.4 DC 保持

当 `preserve_dc=True` 时：

- 如果输入包含 DC，使用输入 DC 作为硬约束。
- 如果输入从非零频率开始，保持原模型 `S(0)`。
- 实现优先使用 null-space 或约束最小二乘；首版可使用经过尺度验证的高权重行，但必须有独立 DC 误差门。

DC 保持不能只依赖在普通频率权重中加入一个点。

### 6.5 分块多右端求解

大端口模型的响应数为 `m^2`。实现要求：

1. 构造一次共享 `A`。
2. 对 `A` 做一次 QR/SVD/Cholesky 分解。
3. 按响应块求解多个 RHS。
4. 块大小由内存预算决定，不改变数值结果。
5. 报告基矩阵形状、秩、条件数、正则化和分块数量。

禁止逐个响应重复分解 `A`。

## 7. Enforcement 流程

完整顺序固定为：

```text
输入 fitted model
  -> 冻结原始模型、原始 RMS 和原始频点响应
  -> 严格检查有限频带与 D
  -> D 已严格无源：跳过渐近补偿
  -> D 非无源：D 投影 + 固定极点残数补偿候选
  -> 候选 RMS、DC、稳定性和残数尺度门
  -> active-mode residue QP 修复剩余有限频带违规
  -> 原始网格 + 自适应网格 + Hamiltonian + D 最终验证
  -> 同时满足严格无源和 RMS：PASS
  -> 否则：FAIL，并保留未损坏的 best-effort
```

### 7.1 候选选择优先级

1. 严格无源并满足 RMS 目标。
2. 严格无源候选中 RMS 最低者。
3. RMS 相同时选择残数扰动更小者。
4. 没有候选满足两个门时不得 PASS。

不能为了更低 sigma 选择 RMS 更差的候选，也不能因为 RMS 好而忽略 `D >= 1`。

### 7.2 uniform damping 的定位

uniform damping 保留为最后回退，但接受条件不变：

- damping 后严格无源；
- damping 后最终 RMS 仍不超过用户目标。

S60P 当前从 `0.000516` 回退到 `0.070694` 的候选必须 FAIL。报告可以保留该诊断候选，但不能把它作为生产交付模型。

### 7.3 修复失败时的模型选择

- 原始模型不得被原地破坏。
- 每种修复候选使用独立快照。
- 没有 PASS 候选时，best-effort 默认选择 RMS 最低的稳定候选，并明确标记未通过无源门。
- 如果某个修复候选同时恶化 RMS 和 passivity，不得替换原始模型。
- CLI 退出码继续遵守 target-search 和 `--fail-on-quality` 契约。

## 8. 与现有代码的集成

主要修改限制在：

- `src/agent_spice/sparam/passivity.py`
- `src/agent_spice/sparam/fitting.py`
- `src/agent_spice/sparam/quality.py`（仅增加诊断字段时）
- 对应测试和文档

建议新增内部函数：

```text
_project_asymptotic_constant_strictly_passive(...)
_build_real_residue_compensation_basis(...)
_solve_asymptotic_residue_compensation(...)
_evaluate_asymptotic_compensation_candidate(...)
_select_passivity_candidate(...)
```

现有 `_project_asymptotic_constant_strictly_passive` 保留矩阵 SVD 职责，不在该函数中混入残数求解。

第一版不新增公开 CLI 参数。内部策略稳定并完成跨端口验收后，再决定是否公开正则化、分块大小或补偿模式。所有实际值先写入 JSON 的 effective config/diagnostics。

## 9. 日志和报告

日志至少记录：

```text
asymptotic compensation start: sigma(D)=...
D projection finished: target=..., delta_norm=...
residue compensation solve: basis=FxK rank=... condition=... rhs_blocks=...
candidate lambda=... rms=... dc_error=... finite_sigma=... asymptotic_sigma=...
candidate accepted/rejected: reason=...
final passivity validation: finite_sigma=... asymptotic_sigma=... strict_pass=...
```

JSON/HTML 新增：

- `asymptotic_sigma_before`
- `asymptotic_sigma_after`
- `asymptotic_projection_delta_norm`
- `asymptotic_compensation_solver`
- `asymptotic_compensation_rank`
- `asymptotic_compensation_condition_number`
- `asymptotic_compensation_regularization`
- `asymptotic_compensation_residue_delta_norm`
- `asymptotic_compensation_rms_before`
- `asymptotic_compensation_rms_after`
- `asymptotic_compensation_dc_error`
- `asymptotic_compensation_seconds`
- `final_validation_max_sigma_at_asymptote`
- 明确的失败原因

失败原因至少区分：

- `asymptotic_compensation_infeasible`
- `asymptotic_compensation_rms_regression`
- `finite_passivity_enforcement_failed`
- `strict_asymptotic_passivity_failed`
- `passivity_enforcement_timeout`

## 10. 测试策略

### 10.1 单元测试

- 纯常数矩阵的严格 SVD 投影。
- 包含动态项时不盲目投影 `D`。
- 实极点补偿基的符号和尺度。
- 复共轭极点补偿基的实数化一致性。
- 多 RHS 与逐响应参考解一致。
- 正则化和列缩放不改变简单问题解析解。
- `preserve_dc=True` 的 DC 误差门。
- RFM 收缩/展开前后响应一致。
- 候选失败时原始系数不变。
- JSON 中不得出现 `NaN` 或 `Infinity`。

### 10.2 合成集成测试

构造：

- `D > 1`，动态残数在有限频带抵消 `D` 的模型。
- 有限频带完全无源但渐近非无源的模型。
- 渐近无源但存在窄带有限频率违规的模型。
- 同时存在 D 违规和窄带违规的模型。

每个模型必须验证补偿前后响应、严格无源性、DC、稳定性和导出再导入一致性。

### 10.3 真实语料验收

| 样本 | 必须满足 | 性能目标 |
| --- | --- | --- |
| S2P | 不回退；严格无源 | enforce `< 1 s` |
| S30P | RMS `<=0.001`，严格无源，RFM 重读通过 | 非无源模型修复 `<=300 s` |
| S60P | RMS 从修复前 `0.000516` 保持在 `<=0.001`，`D<1`，全频严格无源 | enforce `<=60 s` |
| S163P | RMS 不高于当前 `0.00019740` 的合理数值容差；严格无源 | 无需修复时检查 `<=30 s` |
| S166P | RMS 不高于当前 `0.00027066` 的合理数值容差；严格无源 | 无需修复时检查 `<=30 s` |

实施后确认 S163P/S166P 的旧 RFM 都需要修复非无源 `D`，并非“无需修复”场景。当前修复实测分别约 `65.5 s` 和 `56.2 s`；功能门已通过，S163P 尚未达到修订后的 `60 s` 优化目标。

性能目标在当前 Windows 离线生产机上测量。测试必须记录 wall time 和算法分阶段时间，不能只记录总命令时间。

## 11. 实施顺序和提交边界

### 阶段 A：求解器

- 新增共享实数补偿基构造。
- 新增分块多 RHS 正则化最小二乘。
- 完成单元和合成测试。
- 不接入生产 enforce。

### 阶段 B：生产集成

- 接入 D 投影、补偿候选和候选快照。
- 接入现有 active-mode QP。
- 实现严格最终验证和失败回滚。
- 先通过 S60P 功能门，再继续性能优化。

### 阶段 C：性能

- 缓存有理基和参考响应。
- 分块 RHS 和共享分解。
- 达标候选提前终止。
- 减少 S30P 重复 Hamiltonian、SVD 和候选验证。

### 阶段 D：签核

- 跑完整相关测试和真实跨端口矩阵。
- RFM 导出后重新读取验证。
- 更新 README、性能文档和算法报告。
- 每个阶段独立提交，避免把求解器、生产接入和文档混成一个不可审查提交。

## 12. 风险和停止条件

### 12.1 现有极点基不足

固定极点可能无法在整个有限频带内逼近常数补偿 `C`。若 S60P 在合理正则化下仍不能同时满足 RMS 和无源性，则停止第一阶段，不自动增加阶数。

后续可另行评审“增加少量固定高频补偿极点”的方案。该方案必须单独评估模型阶数、瞬态刚性、RFM 兼容性和 ngspice 收敛性，不属于本设计首版。

### 12.2 条件数和残数爆炸

如果补偿依赖极小灵敏度方向，残数可能异常增大。必须使用列缩放、秩截断、正则化和残数扰动门。条件数或残数超过门限时应失败，而不是继续导出。

### 12.3 有限频带补偿引入新违规

补偿可能在采样点之间产生峰值。因此任何候选都必须经过自适应和 Hamiltonian 最终验证，不能只验证原始频点。

### 12.4 性能退化

如果实现对每个响应重复分解基矩阵，S163P/S166P 会不可接受。发现该结构时立即停止优化方向并改为共享分解，不接受通过增加超时掩盖问题。

## 13. 完成定义

只有同时满足以下条件，算法才算完成：

1. 相关单元和集成测试通过。
2. S30P、S60P、S163P、S166P 达到表中的质量门。
3. 所有最终 RFM 重读后仍严格无源且 RMS 达标。
4. 报告不存在假 PASS、非有限 JSON 或被修坏模型覆盖原模型的问题。
5. S60P 不再通过 uniform damping 以 RMS 回退换取无源性。
6. S30P 修复时间达到阶段性能目标，或报告明确的剩余瓶颈和证据。
7. README、算法文档、性能文档和可复现命令同步更新。

## 14. 2026-07-14 实施结果

### 14.1 已实现

- 固定极点实数补偿基，保持实极点和复共轭残数结构。
- 列归一化共享 SVD，多 RHS 按响应块求解；不再构造完整 `frequency * port^2` RHS。
- 频率分块计算补偿残差，避免大端口完整前后响应同时驻留内存。
- D 严格投影后，用残数补偿保持原始频带响应；候选受最终 RMS 和独立 DC 误差门约束。
- 对补偿后的大端口微小有限频带违规，使用 DC 保持微阻尼：缩放模型后，通过最慢稳定实极点精确补回 DC。
- 最终验收对有限频带和 D 都使用严格 `sigma < 1`；`1 < sigma <= 1 + epsilon` 不再允许 PASS。
- target-search 日志明确记录 D 投影、补偿基规模、秩、分块数、RMS 前后值和接受/拒绝原因。

### 14.2 真实语料结果

| 样本 | mean S-RMS | 最终最大 sigma | D sigma | enforce 时间 | 结果 |
| --- | ---: | ---: | ---: | ---: | --- |
| S30P | `0.00094704` | `0.99999905` | `0.00419527` | `66.54 s` | 无回退；无需渐近补偿。 |
| S60P order 8 | `0.00054079` | `0.99999900` | `0.99999900` | `1.77 s` | PASS；替代旧 uniform damping 的 `0.07069` RMS。 |
| S163P 旧 RFM 修复 | `0.00019944` | `0.99999019` | `0.99992759` | `65.49 s` | PASS；DC 误差 `8.9e-16`。 |
| S166P 旧 RFM 修复 | `0.00027466` | `0.99998898` | `0.99996937` | `56.17 s` | PASS；DC 误差 `7.8e-16`。 |

S60P 完整 order-8 命令耗时 `22.48 s`。导出 RFM 重新读取后，mean S-RMS 为 `0.00054079`，原始网格最大 sigma 为 `0.99997767`，D sigma 为 `0.999999000000026`，Hamiltonian 检查没有违规带。

S163P/S166P 修复模型也已导出为 RFM 并重新读取签核：

| 样本 | 重读 mean S-RMS | 重读全网格最大 sigma | 重读 D sigma | 自适应最终最大 sigma | 结论 |
| --- | ---: | ---: | ---: | ---: | --- |
| S163P | `0.0001994433` | `0.9999901943` | `0.9999275923` | `0.9999901943` | 严格 PASS。 |
| S166P | `0.0002746562` | `0.9994015531` | `0.9999693709` | `0.9999889789` | 严格 PASS。 |

两者的 RFM 重读 DC 误差分别为 `3.53e-13` 和 `4.00e-13`，最终违规数均为 `0`。签核产物位于 `runs/passivity-cross-port-20260714/final-rfm-signoff/`。

### 14.3 已淘汰路径

- 大端口补偿后直接进入 active-mode QP：超过 5 分钟仍未完成，已停止作为微小违规的默认路径。
- 仅在少量违规频点做无正则谱投影并回写残数：S163P RMS 恶化到 `0.189`，证明高条件数下局部精确投影会造成残数爆炸，未接入生产。

### 14.4 剩余工作

- 缓存补偿前后的参考基和自适应验证结果，减少大端口两次密集验证；当前按决策暂不作为提交阻断项。
- 将归一化正则化候选和残数尺度门接入生产候选选择；当前生产路径使用无正则共享 SVD，并由 RMS/DC 门拒绝坏候选。
- 后续再将 S163P 修复时间从 `65.49 s` 优化到 `<=60 s`，并评估文档最初的 `30 s` 快路径目标。
- README、算法文档、S163P/S166P 最终 RFM 重读签核均已同步完成。
