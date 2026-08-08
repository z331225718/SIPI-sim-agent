# stabAAA 固定阶数共享极点验证设计

## 定位

本工作是独立的算法研究 spike，用于验证非 VF 极点发现能否缩小 Native 与 IdEM 的阶数和时间效率差距。它不阻塞 Native 产品化，不修改生产拟合后端、CLI 或默认算法。

只有在本设计规定的 Test16 与 s19 实测门槛通过后，才另开生产化设计，讨论依赖、许可、Python/Native 移植和默认策略。

## 问题定义

完整语料 benchmark 表明，Native 并非普遍存在最终 RMS 劣势：部分 case 的 RMS 优于 IdEM。当前主要差距是 Native 为达到同一误差契约需要更多极点或更多搜索时间。Test16 的 attribution 进一步表明，使用高质量外部极点后，现有 residue LS 与 enforcement 可以得到明显更好的结果；因此本 spike 只检验极点发现，不重新设计 residue LS 或被动性强制。

公开 `tomBradde/stabAAA` 实现只接受标量频率响应，不能直接拟合 `P x P x F` 的多端口 S 参数矩阵。本设计通过多个标量观测发现候选极点，再把候选合并为固定阶数的全局共享极点，以实测方式判断 AAA 支持点机制能否发现 Native VF 丢失或低估的模态。

## 目标

1. 在固定阶数 `6`、`8`、`10`、`13` 下，从 Test16 与 s19 的完整频率响应中生成稳定、共轭闭合的共享极点集。
2. 判断多投影 stabAAA 是否稳定发现 Test16 约 2 GHz 的边缘复极对，并避免向既有低频模态坍缩。
3. 在不修改现有 residue LS 与 enforcement 数学的前提下，比较 stabAAA 共享极点、Native 极点与 IdEM 极点的 pole-only、pre-enforcement 和 final 结果。
4. 以阶数、端到端时间和数值条件为主要指标，形成可复现的 go/no-go 结论。

## 非目标

- 不实现或声称实现 MIMO stabAAA、smiAAA 或 sketchAAA。
- 不把 stabAAA、YALMIP 或 MOSEK 接入生产依赖。
- 不修改 Native relocation、residue LS、passivity enforcement、CLI 或默认配置。
- 不在本轮验证 pH-Loewner、RKFIT、KARMA、Partitioned-OVF 或其他候选。
- 不根据最终 RMS 动态增加阶数，也不以不同阶数结果冒充同阶比较。
- 不从公开论文作者关系推断 IdEM 的私有实现。

## 前置门

### 仓库与运行环境

验证固定到 stabAAA 仓库的具体 commit SHA，记录 MATLAB、YALMIP 和 MOSEK 版本。先运行仓库 Absorber 与 International Space Station 示例，保存命令、退出状态、运行时间和误差轨迹。

公开仓库当前没有 LICENSE 文件，因此本 spike 只允许隔离运行和记录输出，不复制源码进入本仓库。若组织政策不允许在许可证缺失时运行该代码，则直接给出 `NO-GO: license_blocked`。

### 数据与基准

- Test16：使用现有 attribution 所用输入、原始频点、端口顺序、参考阻抗和 RMS 定义。
- s19：使用现有 Native/IdEM 调优报告对应的输入 hash、原始频点和 RMS 定义。
- IdEM 极点、Native 极点和 attribution 脚本只从已有 canonical artifact 读取；缺少 provenance 或输入 hash 不匹配时不得比较。

## 总体架构

研究管线分成五个有边界的阶段：

1. Python 生成带完整元数据的标量投影数据包。
2. MATLAB runner 对每个投影独立运行原版 stabAAA，输出候选极点与诊断。
3. Python 对候选进行稳定性校验、共轭补全、聚类和固定阶数选择。
4. 现有 attribution 适配器使用共享极点运行 Native residue LS 与 enforcement。
5. 报告器汇总同阶对比、失败原因和 go/no-go 决策。

各阶段通过 JSON/NPZ/MAT artifact 通信，不通过进程内私有对象耦合。所有随机过程使用显式种子，任何报告结果都能追溯到输入 hash、投影定义、stabAAA commit 和配置指纹。

## 投影设计

### 输入表示

令每个频点的 S 参数矩阵为 `S_k in C^(P x P)`。每个投影产生一个标量频率响应 `y_k`，并保存投影类型、端口索引或向量、归一化系数和随机种子。

### 投影族

首轮包含三类投影：

1. **关键通道投影**：从现有 attribution 的逐通道误差和目标 2 GHz 模态响应中，确定性选择固定数量的 `S_ij(f)`；选择规则必须由输入数据和已保存诊断计算，不允许人工挑选最终效果最好的通道。
2. **对角投影**：选择具有最高频率变化能量的 `S_ii(f)`，补充反射模态观测。
3. **双边随机切向投影**：使用固定随机种子生成单位范数复向量 `u`、`v`，计算 `u^H S_k v`。Test16 与 s19 使用相同种子列表，但按端口数分别生成向量。

首轮不使用随频率变化的奇异向量投影，因为它可能把投影基自身的变化误判为系统极点。若本 spike 失败，频率无关的全局低秩投影可作为后续独立研究，不在本设计中追加。

### 归一化

每个投影只允许乘以一个与频率无关的非零复标量进行归一化。归一化不得改变极点位置。零响应或动态范围低于配置阈值的投影标记为 `projection_degenerate` 并跳过，不交给 stabAAA。

## stabAAA Runner

Runner 必须调用固定 commit 的原版 `stab_AAA.m`，不得修改其支持点选择、LMI、停止条件或极点计算。每个投影独立运行，并输出：

- 输入 artifact 指纹和投影 ID；
- 容差、最大支持点数和约束类型；
- 支持点、重心权重、误差轨迹和返回极点；
- MATLAB/MOSEK 状态、运行时间和峰值内存；
- 成功或结构化失败原因。

Runner 失败不得静默降级为普通 AAA 或 VF。单个投影失败可以继续其他投影；若成功投影少于配置要求，整个 case 标记为 `insufficient_projections`。

## 候选极点处理

### 合法性检查

仅接受有限、稳定且可形成实系数模型的极点。数值上接近实轴的极点规范化为实极点；非实极点必须补齐共轭。任何右半平面极点都记录为 stabAAA 稳定性失败，不允许通过 pole flipping 掩盖。

### 聚类

在归一化复平面距离上聚类候选极点。每个 cluster 至少记录：

- 中心极点；
- 来自多少个独立投影；
- 覆盖哪些投影类型；
- stabAAA 标量误差改善量；
- 跨随机种子的重复率；
- 与 Native、IdEM 参考极点的最近距离，仅用于事后诊断。

IdEM 极点不得参与候选生成、聚类中心计算或选择评分，避免数据泄漏。

### 固定阶数选择

选择器以实状态阶数计费：实极点成本为 1，共轭复极对成本为 2。对每个目标阶数 `6`、`8`、`10`、`13`，按预先定义的综合分数选择 cluster，分数只使用跨投影支持度、投影类型覆盖、标量误差改善和频带覆盖。

选择器必须精确满足目标阶数；若候选结构无法组成该阶数，则该 trial 标记为 `order_unavailable`，不得临时提高阶数或从 Native/IdEM 补极点。

为防止候选都集中在低频，选择过程使用固定的对数频带覆盖约束。该约束只保证候选频带多样性，不指定 2 GHz 目标位置，也不读取 IdEM 极点。

## Attribution 与对照实验

每个 case、方法和固定阶数组合都运行相同数据链：

1. 使用给定共享极点运行现有 Native residue LS。
2. 在全部原始频点计算 raw RMS、逐频误差和 pre-enforcement 最大奇异值。
3. 使用现有 Native enforcement，计算 final RMS、最终最大奇异值、步数、时间和内存。

同阶对照至少包括：

- `stabaaa_projection`：本设计生成的共享极点；
- `native`：现有 Native 在该固定阶数产生的极点；
- `idem`：仅在 canonical artifact 存在该阶数且 provenance 匹配时纳入。

不得把 IdEM 不同阶数的结果放入“同阶胜负”字段；它可以作为单独的产品基线展示。

## 指标

### 主要指标

- 固定阶数 raw RMS 与 final RMS；
- 达到共同 RMS/passivity 契约所需的最小阶数；
- pole discovery、residue LS、enforcement 和端到端时间；
- 峰值内存。

### 极点与数值诊断

- Test16 目标高频频带内的复极对数量与跨投影重复率；
- 与 Native collapse 低频 cluster 的归一化距离；
- residue LS 设计矩阵条件数或稳定的条件估计；
- residue 范数和最大 residue 幅值；
- pre-enforcement 最大奇异值与 enforcement 扰动后的 RMS 增量。

“发现 2 GHz 模态”是诊断结论，不单独构成通过；最终仍以固定阶数端到端结果判定。

## 验收与决策

### GO

必须同时满足：

1. Test16 的 stabAAA 投影路径在 order 10 达到 `final RMS <= 0.001` 且权威 passivity 检查通过；或者在相同契约下将 Native 所需 order 13 降到不高于 10。
2. Test16 order-10 的 final RMS 不高于 canonical IdEM order-10 final RMS 的 `1.25` 倍。
3. s19 在至少一个共同固定阶数上，相对 Native 的 raw RMS 或达到契约的最小阶数有改善，且 final RMS 不恶化超过 `10%`。
4. 成功结果在预先规定的随机种子集合上可复现；不能只依赖单个幸运 sketch。
5. 端到端时间单独报告。研究 spike 不设硬时间门，但若超过 IdEM `5` 倍，GO 结论必须标记为 `quality_only`，不得声称已达到时间效率。

### PARTIAL

出现以下任一情况：极点诊断明显改善但 final RMS 未过门；仅 Test16 改善而 s19 不复现；质量过门但所有种子运行不稳定；质量过门但时间超过 IdEM `5` 倍。

PARTIAL 只允许提出下一轮有限验证，不允许直接进入生产化。

### NO-GO

包括：前置许可或示例门失败；成功投影数量不足；目标高频模态在多数种子中不可见；固定阶数不优于 Native；依赖 IdEM 极点或人工挑选才能过门；或者 residue LS 条件显著恶化导致 enforcement 失败。

## Artifact 与可复现性

每次运行创建独立目录，至少包含：

- `manifest.json`：输入 hash、代码 commit、外部仓库 commit、环境与配置；
- `projections.npz` 和 `projections.json`：标量响应及其定义；
- `stabaaa/<projection-id>.json|mat`：原版运行输出；
- `pole_clusters.json`：候选、聚类和评分；
- `orders/<order>/poles.json`：固定阶数共享极点；
- `attribution/<method>/<order>/summary.json`：LS/enforcement 结果；
- `summary.json`：机器可读总表和决策；
- `report.md`：中文证据报告。

失败运行也必须写 manifest、已完成阶段和结构化原因。报告中的每个数值必须来自 summary artifact，不允许手工抄写形成第二事实源。

## 测试策略

1. 使用合成共享极点 MIMO 数据验证投影不会改变极点位置，候选聚类能恢复已知实极点和共轭复极对。
2. 使用确定性假 stabAAA 输出验证共轭补全、稳定性拒绝、固定阶数计费和频带覆盖。
3. 使用固定种子验证投影与选择结果逐字节或数值可复现。
4. 使用故障注入验证 MATLAB 失败、MOSEK infeasible、NaN 极点、投影退化和 provenance 不匹配均产生明确状态。
5. 复用 attribution 的小型 fixture 验证同一组极点进入现有 LS/enforcement 后指标定义不变。
6. 真实 Test16 与 s19 运行属于受环境约束的研究 benchmark，不进入默认单元测试。

## 交付物

1. 隔离的研究脚本与测试，不被生产 CLI 导入。
2. Test16、s19 的完整 artifact 与中文报告。
3. 对每个验收条款给出证据链接的 GO、PARTIAL 或 NO-GO 决策。
4. 若为 GO，另写生产化 spec；若为 PARTIAL/NO-GO，本计划到此结束，不顺势扩展算法范围。
