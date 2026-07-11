# Native S 参数 SOTA 无源性实施计划

**目标：** 以稀疏/压缩 NNLS 残差扰动替换现有通用修正实验路径，在已知 s19 拟合--无源性冲突上建立证据，再把通过验证的 fit-aware 前沿选择接入 Native。

**设计规格：** [Native S 参数 SOTA 无源性设计规格](../specs/2026-07-11-native-sparam-sota-passivity-design.md)

**统一 benchmark 约束：** 每份结果必须写入输入 SHA、全频点评估数、平均 S-RMS 定义、sigma 定义、请求/有效阶数、passivity 策略、wall time、峰值 RSS 和模型状态。所有变更先做代码审查，再跑对应单测与 benchmark。

## Task 1：固定可复现的 Frontier Fixture

**文件：**
- 新建：`scripts/sparam_native_frontier_probe.py`
- 新建：`tests/test_sparam_native_frontier_probe.py`
- 产物：`runs-sparam/native-sota-baseline/`（忽略，不提交）

- [ ] 对固定 topology/relocation 网格输出每个候选的 JSON 记录。
- [ ] 记录 raw RMS、pre-sigma、违规频段、fit/check 时间、峰值 RSS、极点数量、输入 hash 与完整 config。
- [ ] 复现 s19 order-94 第 8/9 次 relocation 的“接近无源/随后 sigma 跳升”。
- [ ] 用合成测试确认报表不混淆 sum RMS 与平均 S-RMS。

**验收：** 不改公开 CLI 的情况下，probe 独立复现第 8/9 次的分界现象。

## Task 2：活跃奇异模态灵敏度层

**文件：**
- 修改：`src/agent_spice/sparam/passivity.py`
- 新建：`tests/test_sparam_passivity_nnls.py`

- [ ] 从现有 checker 提取违规频率、sigma excess 和归一化左右奇异向量。
- [ ] 建立 residue 到活跃模态的一阶灵敏度，不分配 `(ports^2 * poles)^2` 稠密数组。
- [ ] 输出维度、有限性、秩、条件数、频点/模态数诊断。
- [ ] 以 2-port 模型做有限差分方向导数验证。

**验收：** 解析灵敏度与有限差分在文档化容差内一致，所有矩阵有 shape guard。

## Task 3：小问题密集 NNLS 参考求解器

**文件：**
- 修改：`src/agent_spice/sparam/passivity.py`
- 修改：`tests/test_sparam_passivity.py`
- 修改：`tests/test_sparam_passivity_nnls.py`

- [ ] 实现最小响应扰动、受活跃模态线性约束的密集参考式。
- [ ] 转换为最近距离 NNLS；保留现有 solver 作为对照 oracle，而非生产路径。
- [ ] 保持共轭 residue、互易性与 DC policy。
- [ ] 覆盖无操作、单违规、多模态和 line-search 拒绝。

**验收：** 小合成模型上，NNLS 与参考受约束求解在无源改善和扰动范数上等价。

## Task 4：稀疏/压缩 RP-NNLS

**文件：**
- 修改：`src/agent_spice/sparam/passivity.py`
- 可新建：`src/agent_spice/sparam/passivity_nnls.py`
- 修改：`tests/test_sparam_passivity_nnls.py`
- 新建：`scripts/sparam_nnls_passivity_probe.py`

- [ ] 使用响应块稀疏结构与 QR/等价消元压缩最小扰动系统，数学上对齐公开 RP-NNLS 路线。
- [ ] 采用稳定的 NNLS 或确定性 active-set 适配器，记录停止条件。
- [ ] 每轮精确刷新违规集，只有 holdout/全频 sigma 真实改善才接收。
- [ ] 记录压缩行列数、活跃约束、solver 迭代、预测/实际 sigma、RMS 和拒绝原因。

**验收：** s19 order-93 raw candidate 上不使用 SLSQP、不构造全 Jacobian、有完整诊断且不静默回退全局阻尼。

## Task 5：S19 契约 Benchmark

**文件：**
- 修改：`scripts/sparam_native_frontier_probe.py`
- 必要时修改：`scripts/sparam_full_corpus_benchmark.py`
- 新建：`docs/sparam-native-nnls-s19-results.md`

- [ ] 对 order-93/order-94 raw model 比较 current enforcement、NNLS enforcement 与 enforcement-off。
- [ ] 以全输入频点加自适应 holdout 验收。
- [ ] 报告 raw/final RMS、raw/final sigma、order、fit/check/enforcement 时间、峰值 RSS、状态。
- [ ] 将结果分类为 `accepted`、`passivity_improved_but_rms_lost`、`rms_preserved_but_nonpassive`、`solver_rejected`。

**验收：** 要么得到 RMS 0.001 且 enforced passive 的 s19 模型，要么量化证明该候选的 residue-only RMS 余量不足。

## Task 6：Fit-aware Frontier 选择

**文件：**
- 修改：`src/agent_spice/sparam/native_vf.py`
- 修改：`src/agent_spice/sparam/fitting.py`
- 修改：`tests/test_sparam_native_vf.py`
- 修改：`tests/test_sparam_fitting.py`

- [ ] 保存有限数量的 relocation/topology checkpoint，而不是只留最终 raw-RMS winner。
- [ ] 用 raw RMS、pre-sigma 和预计 NNLS 修正成本评分。
- [ ] 搜索阶段用自适应频点，finalist 才全频验证。
- [ ] Task 7 前保持当前生产默认行为。

**验收：** order-94 第 8/9 次两个候选都被保留，且按 passivity-aware policy 正确排序。

## Task 7：跨语料决策

**文件：**
- 修改：`scripts/sparam_full_corpus_benchmark.py`
- 修改：`docs/sparam-idem-full-benchmark.md`
- 新建：`docs/sparam-native-sota-decision.md`

- [ ] 相同 target/passivity policy 下运行 s19、s30、s60、s91、s163 的 baseline 与 NNLS/frontier。
- [ ] 对所有 variant 使用相同全频点评估。
- [ ] 只比较 accepted 模型；失败明确标记，不能把未无源 raw fit 当作胜利。
- [ ] 决定新路径是否升为 Native 默认、保留内部候选或撤回。

**验收：** 决策文档连接所有原始 artifacts，给出明确 promotion rule；没有 matched evidence 时不得声称 IdEM 等价。

## 延后研究线

- Smith 2024 的 pole collapsing 与 Deschrijver 2007 的广义基函数，处理 relocation 近简并极点。
- MIMO AAA/smiAAA 作为自适应公共极点发现器。
- 在 NNLS/前沿证据完成后，再尝试完整的 passivity-constrained SK/LMI 拟合。
