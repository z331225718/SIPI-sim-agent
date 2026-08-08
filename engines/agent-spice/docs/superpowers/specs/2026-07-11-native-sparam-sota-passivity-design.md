# Native S 参数 SOTA 无源性设计规格

## 目标

将 Native S 参数路径推进到可与 IdEM 对标的产品契约：

```text
输入：.sNp + RMS 目标 + 无源性策略（off/check/enforce）
输出：满足契约的最低公共极点阶数 SPICE 宏模型
验收：全原始频点平均 S-RMS <= 目标；选择 enforce 时 max sigma <= 1 + epsilon
```

第一阶段以 19-port PDN、`RMS=0.001` 且 `enforce` 为标靶；随后必须在本地完整语料，尤其是 60/91/163 port 上复验。目标不是宣称复现 IdEM 专有实现，而是在同一输入、同一频点口径和同一验收标准下，建立可重复的性能对标。

## 已有证据

2026-07 的试验已把“原始拟合能力”和“拟合后无源性修正”分开：

| Native 候选 | 全频点 RMS | 修正前 max sigma | 结论 |
| --- | ---: | ---: | --- |
| order 100，2 对复极点，5 次 relocation | 0.0015486 | 约 1.0 | 已无源，但不满足 RMS |
| order 93，45 实极点 + 24 对复极点，12 次 relocation | 0.0009445 | 1.02149 | 拟合满足，现有修正失败 |
| order 94，46 实极点 + 24 对复极点，12 次 relocation | 0.0008711 | 1.01613 | 拟合满足，现有修正失败 |
| order 95，43 实极点 + 26 对复极点，12 次 relocation | 0.0008515 | 1.01243 | 拟合满足，现有修正失败 |

order-94 的 relocation 第 8 次接近无源、但 RMS 为 0.0010999；第 9 次 RMS 变好但 sigma 跳至约 1.02。现有 enforcement 对 order-93 连续三轮后仍有 sigma=1.00395，RMS 退化到 0.0018939，且 enforcement 约 317 秒。因此当前主瓶颈不是“是否能拟合”，而是“以足够小的保真度代价修正为无源”。

`docs/sparam-literature-survey-2026-07.md` 的调研与公开资料共同给出以下方向：

- Gustavsen 2025：面向大规模 S 参数模型的稀疏/压缩 NNLS 残差扰动无源性修正。
- Gustavsen 2026 MFT-NNLS：公开 Matlab 工具箱，以 `vectfit4` 加 NNLS residue perturbation 组织流程，并提供半尺寸评估加速思路。
- Smith 等 2024：MIMO VF 的极点压缩和自动阶数确定。
- Deschrijver 与 Dhaene 2007：近重极点导致数值问题的广义基函数处理。
- Rodrigues 等 2024：把无源约束引入 SK 拟合迭代的 Passive VF 原则。
- Bradde/Grivet-Talocia 的 AAA 路线：绕过固定阶数 SK relocation 的极点漂移问题。

## 设计决策

1. 主线是面向 S 参数的、稀疏压缩 NNLS 残差扰动，替代以 SLSQP 为中心的修正路径。
2. 拟合阶段把 RMS 与修正前 sigma 看作 Pareto 指标；不能把 `sigma >= 1.01` 的 raw-RMS 最优模型直接视为可接受候选。
3. 半尺寸/Hamiltonian 类评估仅用于产生候选违规区间和加速；最终验收始终采用全原始频点加自适应 holdout 的精确奇异值检查。
4. 暂不先做全端口 LMI 形式的 Passive VF。该原则正确，但 19--163 port 的稠密 LMI 不是可扩展的第一实现。
5. 极点压缩、广义基函数和 AAA 是独立的拟合引擎研究线；它们不阻塞 NNLS enforcement 的落地。
6. 不把实验 topology、relocation 次数或求解器旋钮暴露给公开 CLI；只有跨语料达标后才收敛成产品选项。

## 架构

### 无源性评估

新增内部评估适配层，按违规频点给出：频率、最大奇异值、超额、归一化左右奇异向量，以及到 residue/常数项扰动的一阶灵敏度。该层必须避免构造 `(ports^2 * poles)^2` 的全局稠密矩阵，并记录维度、秩、条件数和数值有效性。

### 压缩 RP-NNLS

专用修正器应满足：

1. 固定极点，保持稳定性、共轭实性、互易性与配置的 DC 策略。
2. 在活跃奇异模态上构造一阶约束。
3. 利用响应块结构与 QR/等价消元，在约束坐标中形成紧凑 NNLS，而不是以全部 residue 元素构造全 Jacobian。
4. 用最小扰动目标求解；精确复查模型后只接受真实 sigma 改善的步长。
5. 每轮记录活跃约束、压缩行列数、预测/实际 sigma 改善、RMS 改善、耗时和拒绝原因。

实现为 clean-room：可依据公开论文、说明书和数学公式验证设计，不复制第三方 Matlab 源码。

### Fit-aware 候选前沿

Native relocation 要保留有意义的迭代/拓扑 checkpoint，而非只保留 raw RMS 最优模型。排序规则：

1. 优先已在无源保护带内的候选；
2. 否则在 RMS 有足够余量时，优先预计 NNLS 修正代价最低者；
3. 若预计 sigma 修正会耗尽 RMS 余量，则拒绝该 raw-RMS 候选。

初期只作为内部诊断和实验开关；只有跨语料证据充分才变为默认选择策略。

### 后续拟合引擎研究

- 以 Smith 2024 极点压缩与 Deschrijver 2007 广义基函数处理近简并极点。
- 评估 smiAAA/MIMO AAA 作为公共极点发现或初始化器。
- 在 NNLS 与前沿选择稳定后，再研究 active-mode cutting plane 的受约束 SK 拟合。

## 非目标

- 不声称逆向或复现 IdEM 私有算法。
- 不因 Native 路径不用 scikit-rf 的 VF 就删除仍被 S 参数读写/分析使用的 scikit-rf。
- 不在受控 benchmark 前把全部拟合替换为 AAA。
- 不把未通过 enforce 的 raw fit 作为与 IdEM 的“成功对标”。

## 验收门槛

### Gate A：数值正确性

- 合成无源模型无扰动或仅有数值级扰动。
- 单一违规模型的精确 sampled sigma 降低，极点稳定性不变。
- 互易性、共轭实性、DC 策略不被破坏。
- 小问题上密集参考 QP 与 NNLS 的无源性改善和扰动范数在容差内一致。

### Gate B：S19 enforcement

固定使用 order-93 raw fit（45 实极点、24 对复极点、12 次 relocation）：

- 全输入频点加自适应 holdout 上 `max sigma <= 1 + 1e-6`；
- 最终平均 S-RMS `<= 0.001`；
- 不允许静默回退到全局阻尼；
- 报告精确 wall time 与进程峰值 RSS。

未通过也必须形成有效结论：区分“修正器不足”与“该候选的 RMS 余量在 residue-only 修正下物理上不足”。

### Gate C：跨语料证据

以相同契约运行 s19、s30、s60、s91、s163。要成为生产默认，须无已接受 case 的 order/RMS 回退，并至少在一个 60+ port case 上显著改善 enforcement 时间或内存。

## 风险

- NNLS 可能降低内存/时间，但仍无法在 s19 order-93 的 5.5e-5 RMS 余量内修正；此时转向 fit-aware candidate 选择，不增加全局阻尼旋钮。
- 半尺寸评估可能漏掉数值角落；最终验收不能跳过全频检查。
- 迭代内全频检查昂贵；搜索阶段使用自适应违规/holdout 点，最终候选才全频复核。
