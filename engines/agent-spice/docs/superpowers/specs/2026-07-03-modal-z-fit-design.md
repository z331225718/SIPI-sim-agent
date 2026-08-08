# Modal Z-Domain Fit Design

日期：2026-07-03

## 背景

当前 `fit-sparam` 已完成 `Touchstone -> scikit-rf VectorFitting -> SPICE -> JSON/HTML report` 的 MVP 管线，并增加了 Z 参数对比、log-magnitude Z RMS、streaming passivity check 和 order sweep。30-port PDN 的 20/40 阶 raw-response sweep 显示：

| Order | S RMS | Z log-mag RMS | Sampled max sigma | 结论 |
| ---: | ---: | ---: | ---: | --- |
| 20 | 1.1509 | 0.9737 decades | 1.3102 | 明显欠拟合 |
| 40 | 0.4771 | 0.7582 decades | 1.3035 | 有改善但仍远离 0.1 decade |

继续扫阶只能描述现状，不能解决“为什么 30-port 需要 100+ order”的根因。根因更可能是当前拟合目标不匹配 PDN 交付目标：scikit-rf 的 `VectorFitting` 对 `nports^2` 个 S/Z/Y 元素使用公共 pole set，误差目标偏向元素级响应；PDN 工程判断通常关心 Z 参数、阻抗峰谷、端口间电源模态和低阻抗路径。

## 目标

实现一个隔离的 Modal/Z-domain 拟合实验原型，用来判断“按 Z 域模态而不是按 Sij 元素拟合”是否能在几十阶内显著降低 30-port PDN 的 Z log-magnitude error。

本阶段只做算法可行性验证，不承诺替换主 `fit-sparam` 的 SPICE 导出。

## 非目标

- 不 monkey-patch 或 fork scikit-rf 私有 `_pole_relocation()`。
- 不把 SROPEE 加入 runtime dependency；SROPEE 只作为算法参考或隔离实验对象。
- 不在本阶段实现 passivity enforcement 或 passive circuit synthesis。
- 不承诺生成可进入 transient signoff 的 SPICE 子电路。
- 不继续盲目扩大 order sweep 作为主要工作。

## 设计原则

1. **先验证算法假设**：主输出是误差报告和 HTML/JSON artifact，而不是 SPICE。
2. **保持隔离**：新增 `agent_spice.sparam.modal` 模块，不破坏现有 `fit_touchstone_to_spice()` 路径。
3. **以 Z 域为主**：默认从 S 转 Z，目标指标是 `RMS(log10(|Zfit| / |Zorig|))`。
4. **优先低秩模态**：用频点上的 Z 矩阵模态信息提取主导模式，先拟合有限数量的 modal traces。
5. **可证伪**：若 30-port 上 modal prototype 不能明显优于元素级 VF，则停止该路线，转向 MOR/Block SAPOR。

## 推荐方案

### 方案 A：Reduced-Basis Z Rational Fitting 原型

流程：

1. 读取 Touchstone，并用 scikit-rf 将 S 转 Z。
2. 对每个频点的 Z 做 Hermitian proxy：
   - 默认使用 `0.5 * (Z + Zᴴ)` 的 eigenvalues/eigenvectors，得到可解释的阻抗模态。
   - 对非 Hermitian/非互易输入，保留 fallback：直接使用 `np.linalg.svd(Z)` 的 singular values/vectors。
3. 选择前 `k` 个主导端口 basis vectors，形成固定低秩 basis `Q`。
4. 投影得到 reduced matrix：`Zr(f) = Qᴴ @ Z(f) @ Q`。
5. 对 `Zr` 的 `k^2` 个 scalar traces 做 reduced fitting：
   - `fixed`：固定稳定极点的有理最小二乘。
   - `vector`：直接在 reduced Z Network 上调用 scikit-rf VF，作为对照路径。
   - `shared-poles`：少数 modal surrogate VF 识别公共 pole，再做 reduced LS。
   - `peak-poles`：从 modal Z 峰值直接选择公共 pole，混合全带宽几何 pole，并做可调指数的相对加权 LS。
6. 从 fitted reduced matrix 重建近似 Z：`Z_fit(f) = Q @ Zr_fit(f) @ Qᴴ`。
6. 输出 JSON/HTML 报告：
   - full-matrix Z log-magnitude RMS
   - basis projection Z log-magnitude RMS
   - selected modal trace log-magnitude RMS
   - per-port diagonal Z log-magnitude RMS
   - worst frequency and worst port pair
   - comparison plots for top diagonal/off-diagonal entries

优点：实现快，能直接验证“低秩端口模态 + 共享固定极点”是否减少有效阶数；`k^2` 个 reduced traces 比 `nports^2` 个 full matrix traces 更可控。缺点：固定 basis 对强频变模态可能不够准确，且不保证 passivity。

### 方案 B：Loewner/Data-Driven MIMO Prototype

用 Loewner framework 从频响数据构造 MIMO reduced model。优点是理论上更直接面向数据驱动 MOR，可根据数值秩判断 reduced order。缺点是实现复杂，passivity 和 SPICE 综合仍需单独解决；本阶段成本高于方案 A。

### 方案 C：SROPEE/Block SAPOR 隔离实验

把 SROPEE 作为外部研究工具运行，观察其 full synthesis -> Passive MOR -> reduced synthesis 是否能在 30-port 上得到可接受 reduced netlist。优点是目标最终接近电路综合；缺点是 GPL-3.0 和工程成熟度风险高，不能直接进入项目 runtime。

## 决策

先做方案 A。方案 A 是当前仓库最小可验证算法突破：它改变拟合目标和数据表述，能直接回答“元素级 VF 是否是导致高阶的主要原因”。

方案 B、C 作为下一轮研究线，只有当方案 A 明确失败或不足以解释 30-port 高阶需求时再启动。

## 组件设计

### `src/agent_spice/sparam/modal.py`

职责：

- 从 `skrf.Network` 或 Z samples 构造 modal basis。
- 计算 modal traces。
- 对 modal traces 执行 scalar fitting。
- 重建 `Z_fit(f)`。
- 计算 Z-domain metrics。

主要数据结构：

```python
@dataclass(frozen=True)
class ModalZFitConfig:
    mode_count: int = 8
    basis_frequency_indices: tuple[int, ...] | None = None
    basis_frequency_sample_count: int = 9
    basis_frequency_sampling: str = "linear"
    decomposition: str = "hermitian"
    scalar_fit_order: int = 12
    frequency_sample_count: int | None = None
    frequency_sample_head_count: int = 0
    pole_damping: float = 0.05
    reduced_fit_method: str = "fixed"
    shared_pole_trace_count: int = 3
    relative_weight_power: float = 1.0
    relative_weight_mode: str = "trace"
    relative_weight_iterations: int = 1
    relative_weight_update: str = "original"
    auto_order_candidates: tuple[int, ...] | None = None
    auto_order_max_z_log_magnitude_rms_error: float | None = None
    auto_order_max_diagonal_z_log_magnitude_rms_error: float | None = None
```

```python
@dataclass(frozen=True)
class ModalZFitResult:
    ports: int
    frequency_points: int
    mode_count: int
    scalar_fit_order: int
    z_log_magnitude_rms_error: float
    basis_projection_z_log_magnitude_rms_error: float
    diagonal_z_log_magnitude_rms_error: float
    worst_error_frequency_hz: float
    worst_error_port_pair: tuple[int, int]
    fitted_z: np.ndarray
```

### `src/agent_spice/sparam/modal_report.py`

职责：

- 写 JSON 报告。
- 写 HTML 报告。
- 复用现有 Z log-log 图风格，但聚焦 Z-domain。

### CLI：`agent-spice fit-modal-z`

参数：

- `touchstone`
- `--report`
- `--html-report`
- `--mode-count`
- `--basis-frequency-sample-count`
- `--basis-frequency-sampling linear|log`
- `--scalar-fit-order`
- `--frequency-sample-count`
- `--frequency-sample-head-count`
- `--decomposition hermitian|svd`
- `--reduced-fit-method fixed|vector|shared-poles|peak-poles`
- `--shared-pole-trace-count`
- `--relative-weight-power`
- `--relative-weight-mode trace|full-projected`
- `--relative-weight-iterations`
- `--relative-weight-update original|max|geometric`
- `--auto-order`
- `--auto-order-candidates`
- `--auto-order-max-z-log-rms-error`
- `--auto-order-max-diag-z-log-rms-error`

MVP 允许只输出报告，不输出 SPICE。

## 数据流

```text
Touchstone
  -> skrf.Network
  -> S to Z
  -> select/sample frequencies
  -> build modal basis Q
  -> project Z to reduced matrix Zr
  -> reduced rational fit per reduced matrix entry
  -> reconstruct Z_fit
  -> metrics and HTML report
```

## 误差指标

主指标：

```text
z_log_magnitude_rms_error = RMS(log10(max(|Z_fit|, eps) / max(|Z_orig|, eps)))
```

辅助指标：

- diagonal-only Z log-magnitude RMS
- selected modal trace RMS
- basis projection Z log-magnitude RMS
- worst frequency
- worst port pair
- max absolute Z error, 仅作参考

## 失败模式与保护

- 如果 input Z 包含 NaN/Inf：直接失败并报告输入质量问题。
- 如果 modal basis 维度超过端口数：CLI 报错。
- 如果 fixed basis 重建误差已经很大：报告 `basis_projection_error`，避免把 basis 选择失败误判为 scalar fitting 失败。
- 如果稀疏采样漏掉低频 raw 点：用 `--frequency-sample-head-count` 强制把前 N 个 raw 频点纳入 LS fit sample。
- 如果启用自动选阶：只在 bounded candidate set 内选择最小过门阶数；如果没有候选过门，则返回已尝试候选中 Z log RMS 最好的结果，并在报告里列出所有 trials。
- 如果 scalar fit 不收敛：报告对应 mode，不阻断其他 mode 的评估。
- 如果 result 不能反变换为 S 或不能导出 SPICE：这是本阶段可接受限制。

## 验收标准

1. 单元测试覆盖 modal basis、projection/reconstruction、Z log metric、CLI 报告写出。
2. `python -m pytest -v` 全量通过。
3. 对 `5power_30port_wocap_121124_221036_4876_DCfitted.s30p` 生成 `runs-sparam/modal-z-30p/fit_report.json` 和 `fit_report.html`。
4. 优化报告必须比较：
   - 当前元素级 VF 20/40 阶结果。
   - modal-Z prototype 结果。
   - 是否值得继续方案 A。
5. 如果 modal-Z prototype 没有显著改善，报告必须明确建议转向方案 B/C，而不是继续盲扫阶。

## 资料依据

- scikit-rf `VectorFitting` 文档说明其包含 VF、relaxed pole relocation 和 fast solving，并提供 passivity/report/export API：<https://scikit-rf.readthedocs.io/en/latest/api/generated/skrf.vectorFitting.VectorFitting.html>
- SINTEF Vector Fitting/Matrix Fitting 说明 multi-port rational modeling 和 passivity enforcement 的经典流程：<https://www.sintef.no/en/software/vector-fitting/>
- SINTEF VFIT3 说明 FRVF 对多元素响应的 fast pole identification 改进：<https://www.sintef.no/en/software/vector-fitting/downloads/vfit3/>
- Gustavsen/Heitz Modal Vector Fitting 论文摘要指出 MVF 关注 eigenpairs/modes 和相对精度，适合高动态范围多端口模型：<https://digitalcollection.zhaw.ch/server/api/core/bitstreams/28bce669-7902-4558-be38-14539a5368cd/content>
- SROPEE README 说明 full synthesis、Passive MOR/Block SAPOR、reduced synthesis 的三阶段路线及 GPL-3.0 许可证：<https://github.com/RasulChoupanzadeh/SROPEE>

## 自审

- 无 TBD/TODO。
- scope 明确限定为算法原型，不替换现有 SPICE 导出。
- 验收标准包含代码、报告和决策。
- 风险和非目标明确，避免把研究代码直接放进生产路径。
