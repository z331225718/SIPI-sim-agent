# S 参数宏建模算法研究总复盘

日期：2026-07-12

## 1. 结论先行

本轮工作的目标不是在某个容易样例上得到更低 RMS，而是：**在固定阶数下发现更完整、更紧凑的共享极点，使 Native 接近 IdEM 的阶数与时间效率，同时保持全频 S-RMS 和无源性产品契约。**

最终结论如下。

1. **[FACT] Native 已经是可交付的生产基线，但尚未达到 IdEM 的阶数/时间效率。** 完整语料中 Test13、Test16、Test11、Test3 都能得到被动且 RMS `<=0.001` 的模型；但 Test16/Test11/Test3 的阶数比分别为 `1.30/1.67/2.25`，时间比分别为 `4.22/2.88/3.29`。[完整 benchmark](sparam-idem-full-benchmark.md)
2. **[FACT] 极点发现是已被交叉 attribution 定位的主因，不是 residue LS 本身。** Test16 上将 IdEM order-8 极点交给本地 residue LS，pre RMS 为 `0.00089444`，enforce 后为 `0.00090913` 且无需全局阻尼；Native order-10 极点用相同 LS 得到 pre RMS `0.00321001`，enforce 后 `0.00422347`。[source attribution artifact](../runs-sparam/passivity-direction-validation/source-attribution/summary.json)
3. **[FACT] 已实现并实测的三条非 VF 极点路线均未通过各自冻结门。** stabAAA 在 s19 order 74 final RMS 为 `0.0247999`；Tangential Loewner 的 40/40 候选均含 RHP 极点；RKFIT order 74 的两种初始化分别含 16/1 个 RHP 极点。stabAAA 与 IdEM 的 `26.47x` 是跨 artifact 计算，按 **[STRONG INFERENCE]** 使用，不是其 direct attribution 事实。
4. **[FACT] 大量 pole-placement、relocation、residue 修正和无源性策略只改善局部指标，没有关闭端到端契约。** 高频注入可以让 Test16 看见约 2 GHz 模态，但不能自动形成紧凑的全矩阵公共极点；projection/NNLS 可以降低 sigma，但会耗尽 RMS 余量。
5. **[STRONG INFERENCE] 当前剩余差距是“稳定、紧凑、适合矩阵值数据的共享极点发现”与其搜索效率，而非缺少更多 enforcement 旋钮。** 这是 source attribution、已编号的 D4-D11/D15、早期未编号支线、s19 三条非 VF 路线和 MFT-NNLS 共同支持的结论；它不是对 IdEM 私有实现的推断。

## 2. 证据口径与 authority

- **[FACT] 第一权威层**：机器生成的 canonical `summary.json`、每阶 `fit_report.json` 和算法 runner artifact。
- **[FACT] 第二权威层**：注明由 canonical artifact 生成的报告，例如 [完整 benchmark](sparam-idem-full-benchmark.md)、[IdEM s19 tuning](sparam-idem-s19-tuning.md) 和三份非 VF 结果报告。
- **[FACT] 第三权威层**：设计/spec 与实施报告，仅用于解释冻结契约和未运行范围，不覆盖机器数值。
- 运行目录默认不提交；本文仍给出 repo 相对路径，需在保有 canonical runs 的主工作区打开。
- 若历史报告与后续重跑冲突，以输入 SHA 相同、评估点完整、provenance 更完整的后续机器 artifact 为准。例如 stabAAA Test16 的首次 `mosek_missing` 不覆盖授权重跑后的有效 preflight；详见 [stabAAA Test16 报告](sparam-stabaaa-shared-pole-validation-results.md)。

标签含义：**[FACT]** 为 artifact 直接事实；**[STRONG INFERENCE]** 为多组事实共同迫出的工程结论；**[HYPOTHESIS]** 为尚未被实验确认的解释。

## 3. 基准：Native 与 IdEM 到底差在哪里

| case | Native order / RMS / sigma / time | IdEM order / RMS / sigma / time | 判定 |
|---|---|---|---|
| s19 | 完整语料首轮 FAIL；后续独立 raw-only order 93 RMS `0.00094449` 但 sigma `1.02149`，不是 signoff | order 74 / `0.000936916` / `0.999999994` / `118.46s` | Native raw fit 与无源性冲突；不可写成完整语料 PASS |
| s30 | order 83 / `0.000918440` / `1.00000001` / `1820.12s` | FAIL | Native 可交付，不能做 IdEM 比值 |
| Test13 s60 | 8 / `0.000516018` / `0.999977674` / `52.78s` | 7 / `0.000737076` / `0.999696292` / `35.42s` | parity PASS |
| Test16 s91 | 13 / `0.000707379` / `0.999998900` / `335.95s` | 10 / `0.000597697` / `0.999998073` / `79.62s` | 阶数与时间 FAIL |
| Test11 s163 | 10 / `0.000197399` / `0.999965329` / `608.60s` | 6 / `0.000696815` / `0.999999875` / `211.09s` | 阶数与时间 FAIL |
| Test3 s166 | 9 / `0.000271431` / `0.999981400` / `656.73s` | 4 / `0.000902467` / `0.999999831` / `199.76s` | 阶数与时间 FAIL |

**[HYPOTHESIS] 假设：** 若差距主要来自 residue LS 或 enforcement，则把更好的极点交给本地后半链路不应显著改变结果。

**[FACT] 实现：** source-attribution 固定相同 Test16 全 611 点、本地 residue LS 与 enforcement，仅替换 pole source。

**[FACT] 验证数据与关键数值：** IdEM order-8 poles + local LS 得到 `0.00089444 / sigma 1.002174`，最终 `0.00090913 / sigma 0.999998394`；Native order-10 poles + local LS 为 `0.00321001 / 1.046433`，最终 `0.00422347 / 0.9999989`；Native order-17 poles更差，pre RMS `0.043894`，最终 `0.0691002`。

**[STRONG INFERENCE] 结论：** 本地 residue LS 和 enforcement 有能力把一组好极点变成合格模型；Native 的主要问题在 pole source。不能由此推断 IdEM 如何找极点。

**证据路径：** [source attribution](../runs-sparam/passivity-direction-validation/source-attribution/summary.json)。

## 4. 总览表

`N/A` 表示候选在稳定性或前置门被拒，不能伪填 final RMS/sigma/time。

| 编号 authority / 路线 | 性质 | case / order | best RMS / sigma / time | 角色与结果 | 停止原因 |
|---|---|---|---|---|---|
| 未编号：Native production | VF，产品候选 | Test16 / 13 | S-RMS `0.000707379` / `0.9999989` / `335.95s` | signoff 可交付 | 对 IdEM 阶数 `1.3x`、时间 `4.22x` |
| 未编号：IdEM reference | 私有，基准 | s19 / 74 | S-RMS `0.000936916` / `0.999999994` / `118.46s` | canonical signoff 基准 | 非研究候选 |
| D4：高频 frequency gate | VF，候选 | Test16 / 10 | 未过 S-RMS `0.001` | NO-GO | 只限制高频极点，未补齐模态 |
| D5：residual edge injection | VF，候选 | Test16 / 10 | 未过 S-RMS `0.001` | NO-GO | 发现边缘但全矩阵质量不足 |
| D6：relocation trajectory/weight | VF，诊断 | Test16 / 8-10 | edge pair 可跌至 `1.3823GHz` | 诊断成立 | collapse 被复现，未治愈 |
| D7：静态 out-of-band `c_res` 正则 | VF，候选 | Test16 | `1e-3..1e-1` sweep | NO-GO | 未过冻结门 |
| D8：dynamic `c_res` | VF，候选 | Test16 | `1e-3..1e-1` sweep | NO-GO | 未过冻结门 |
| D9：pole distribution | VF，诊断 | Test16 | 非拟合指标 | 诊断资产 | 暴露缺少 1.8-2.0 GHz 复极对 |
| D10：full-grid baseline | VF，控制 | Test16 | 全 611 点 | 诊断控制 | 失败并非 256 点抽样独有 |
| D11：data-only manifold | 数据候选 | Test16 | 无合格稳定固定阶候选 | NO-GO | 候选选择不足 |
| D15：stacked-scalar Loewner | 非 VF，候选 | Test16 / 12 configs | final N/A | NO-GO | 12/12 `unstable_eigenvalue` |
| 未编号：MFT-NNLS Python | VF + NNLS，候选 | s19 / 8-16 | S-RMS best `0.021848` | NO-GO | RMS 约目标 22x |
| 未编号：MFT-NNLS MATLAB | VF + NNLS，候选 | s19 / 8-80 | S-RMS best `0.004539` at 80 | NO-GO | 原版也未达 `0.001` |
| 未编号：Native compressed NNLS | 固定极点修正 | s19 / 93 | S-RMS `0.00153409` / `1.00839` / `117.1s` | NO-GO | sigma 和 RMS 均未过门 |
| 早期未编号：固定极点 alternation | 后处理候选 | Test16 / 10 | S-RMS `0.00323158` / `1.02699` / `227.35s` | NO-GO | source pressure 未消除 |
| 早期未编号：fit-aware residue LS | 固定极点候选 | Test16 / 10 | S-RMS `0.00119098` / `1.03875` | NO-GO | 不被动 |
| 未编号：stabAAA projections | 非 VF，候选 | Test16 / 13 | S-RMS `0.00473795` / `0.9999989` / enforce `1594s` | NO-GO | 同阶比 Native 差 `6.70x` |
| 未编号：stabAAA projections | 非 VF，候选 | s19 / 74 | S-RMS `0.0247999` / `0.9999989` / enforce `83.50s` | NO-GO | 质量门与 seed-overlap 门均失败 |
| 未编号：Tangential Loewner | 非 VF，候选 | s19 / 56,60,68,74 | final N/A | NO-GO | 40/40 pencils 有 RHP poles |
| 未编号：RKFIT | 非 VF，候选 | s19 / 74 | internal misfit `0.00035024`; final N/A; `22.30s` | NO-GO | 最好初始化仍有 1 个 RHP pole |
| 未编号：modal-Z / orthogonal basis | 降维诊断 | s19、s30、60-166p | **Z-log metric，不能与 S-RMS 横比** | 未产品化 | s19 fit-limited，163/166p basis-limited |

## 5. 已编号 D4-D11/D15 与早期未编号支线

编号仅以 canonical artifact 目录中明确出现的名称为准：D4、D5、D6、D7、D8、D9、D10、D11 和 D15。QP/projection/alternation 等更早实验没有冻结的 D1-D3 编号，本文称为“早期未编号支线”，不补造追溯编号。canonical 根目录为 [passivity-direction-validation](../runs-sparam/passivity-direction-validation/)。

### 早期未编号支线：residue/enforcement 归因

**[HYPOTHESIS] 假设：** Native poles 基本正确，增加 QP/projection、active-mode 或 fixed-pole 交替即可达标。

**[FACT] 实现：** 在 Test16 order 10 上比较无 DC/有 DC、QP 1-2 轮、active-variable 上限、fit-aware candidate selection、projection 与 global damping；另做固定极点 LS/partial-passivity 交替。

**[FACT] 验证数据：** 固定极点 alternation 基线 `RMS 0.00321001, sigma 1.04643`，一轮后最好 `0.00323158, 1.02699`，耗时 `227.35s`；第二轮没有继续改善。

**[STRONG INFERENCE] 结论：** 修正器能压 sigma，但无法从错误 pole manifold 中恢复缺失动态；继续堆 enforcement 不是主线。

**证据路径：** [fixed-pole alternation](../runs-sparam/passivity-direction-validation/fixed-pole-alternation/summary.json)、[source attribution](../runs-sparam/passivity-direction-validation/source-attribution/summary.json)。

### D4-D6：高频极点注入、门控与 relocation collapse

**[HYPOTHESIS] 假设：** Test16 主要缺少 1.8-2.0 GHz 边缘复极对；显式注入并提高高频 relocation 权重可以保住它。

**[FACT] 实现：** D4 frequency-gated reinjection；D5 residual-edge injection，并冻结 order 10 对照；D6 保存每轮极点、`c_res` 与条件数轨迹，再加高频权重 relocation。

**[FACT] 验证数据：** MFT 独立复现同类 collapse：order 8 的边缘复极对从第 1 轮 `2.021398GHz`，到第 4 轮 `1.606237GHz`，第 8 轮 `1.382299GHz`；第 3 轮 sigma 系数增长到约 `1.05e8`。[collapse 报告](sparam-mft-nnls-test16-collapse.md)

**[STRONG INFERENCE] 结论：** “高频模态会在 relocation 中丢失”被确认；但注入/加权只约束一个症状，不能保证固定阶数下全矩阵最优公共分母。

**证据路径：** [D4](../runs-sparam/passivity-direction-validation/pole-placement-d4-frequency-gated-reinject/summary.json)、[D5](../runs-sparam/passivity-direction-validation/pole-placement-d5-residual-edge-injection-fixed-order10/summary.json)、[D6](../runs-sparam/passivity-direction-validation/pole-placement-d6-trajectory/summary.json)。

### D7-D8：静态与动态 `c_res` 正则

**[HYPOTHESIS] 假设：** relocation collapse 来自分母系数 `c_res` 无约束增长；对带外/边缘系数加正则可稳定极点。

**[FACT] 实现：** D7 固定权重 `1e-3/1e-2/1e-1`；D8 根据边缘增长动态触发同一权重网格，保留诊断但默认关闭。

**[FACT] 验证数据：** 所有 sweep 都生成完整 artifact，但没有候选同时关闭固定阶 RMS 与 passivity 门。

**[STRONG INFERENCE] 结论：** `c_res` 爆长是 collapse 的伴随数值信号，不足以单独定义正确极点位置。

**证据路径：** [D7 1e-2](../runs-sparam/passivity-direction-validation/pole-placement-d7-out-of-band-reg-1e-2/summary.json)、[D8 1e-2](../runs-sparam/passivity-direction-validation/pole-placement-d8-dynamic-cres-1e-2/summary.json)。

### D9-D11：分布诊断、全频公平基线与 data-only discovery

**[HYPOTHESIS] 假设：** 失败可能来自抽样偏差，或可以仅从数据残差峰/极点集合流形中挑出更好公共极点。

**[FACT] 实现：** D9 对比 Native/IdEM 的复极点频带分布；D10 用全部 611 点重跑 Native；D11 禁止 IdEM pole oracle，仅从数据生成/组合固定阶候选。

**[FACT] 验证数据：** D9 显示 Native order-10 在 1.3-1.45 GHz 有一对复极点、在 1.8-2.0 GHz 为零；IdEM order-8 在约 `1.36555GHz` 与 `2.00044GHz` 各有一对。D10 没有消除差距，D11 未得到可进入产品链的合格集合。

**[STRONG INFERENCE] 结论：** 抽样不是唯一根因；数据里能看见边缘模态，也不等于能以正确权重选出紧凑共享极点。

**证据路径：** [D9](../runs-sparam/passivity-direction-validation/pole-placement-d9-pole-distribution-baseline/summary.json)、[D10](../runs-sparam/passivity-direction-validation/pole-placement-d10-full-grid-baseline/summary.json)、[D11](../runs-sparam/passivity-direction-validation/pole-placement-d11-data-only-fixed/summary.json)。

### 独立未编号路线：modal-Z / 正交降维

**[HYPOTHESIS] 假设：** 端口维度压缩、正交基和 Z-domain 模态分解可能让极点搜索看到更清晰的低秩动态。

**[FACT] 实现：** 固定全频 Hermitian basis、trace/full-pair residual、mode anchor、局部极点细化、不同 basis/order/entry budget；相关结果集中在 modal-Z v7-v24 系列。

**[FACT] 验证数据：** 30p 上 V7 bounded auto order 52 的 **Z-domain log-magnitude RMS** 略优于原版 raw order 120，运行约 `9.5-9.6s`，而原版约 `680s`；但 s19 明确 fit-limited，163p/166p 固定 basis 明确 basis-limited。该指标不是 S-RMS，不能与总览中的 S 参数数值横向比较，也没有 SPICE/passivity/signoff 闭环。

**[STRONG INFERENCE] 结论：** 正交/模态降维是有价值资产，但不能作为“已缩小 IdEM S 参数共享极点差距”的证据。

**证据路径：** [modal-Z 优化报告](sparam-modal-z-optimization-report.md)、[original vs modal V7](sparam-original-vs-modal-v7-comparison.md)。

### D15：stacked-scalar Loewner

**[HYPOTHESIS] 假设：** 多个随机标量投影的 Loewner blocks 纵向堆叠，可以形成公共极点。

**[FACT] 实现：** Test16 上 12 个 partition/projection/rank 候选，禁止 pole flipping。

**[FACT] 验证数据：** 12/12 因 `unstable_eigenvalue` 被拒，没有候选进入 residue LS。

**[FACT] 冻结门结果：** D15 的 12 个候选全部被拒；后来矩阵值双侧 Tangential Loewner 的 40 个候选也全部被拒。**[STRONG INFERENCE]** 两条不同 Loewner 构造在禁止反射的纪律下都没有提供可用稳定极点集。

**证据路径：** [D15](../runs-sparam/passivity-direction-validation/pole-placement-d15-loewner/summary.json)、[Tangential Loewner 报告](sparam-tangential-loewner-s19-validation-results.md)。

## 6. MFT-NNLS：原版、Python port 与 passivity 路线

**[HYPOTHESIS] 假设：** Gustavsen MFT 的 `vectfit4 + RP-NNLS` 能避免 Native relocation collapse，并以更小代价完成无源修正。

**[FACT] 实现：** Python clean-room port 覆盖一轮 VF parity、QR-compressed homogeneous NNLS、weight mode 1、D/E、渐近约束、bandwidth/pole subset 和 outer/inner perturbation；同时运行 MATLAB 原版作归因对照。

**[FACT] 验证数据：** Python s19 order `8/10/12/14/16` 最好 order 12 RMS `0.021848`，约目标 22 倍；Test16 relocation collapse 被复现。MATLAB 原版在更有利的去 DC 825 点下，port-parity profile 最好 `0.020503`，reference-strength profile 到 order 80 最好 `0.004539`，仍高于 `0.001`。

**[FACT] 冻结门结果：** Python Gate B 失败，MATLAB 已测试到 order 80 也未达标，因此未跑 promotion corpus。**[STRONG INFERENCE]** Python 失败不能仅归咎于移植；在已测试数据、阶数和配置内没有观察到低阶质量优势。

**证据路径：** [总决策](sparam-mft-nnls-conclusion.md)、[Python Gate B](sparam-mft-nnls-s19-gate-b.md)、[MATLAB 原版](sparam-matlab-mft-s19-benchmark.md)、[Test16 collapse](sparam-mft-nnls-test16-collapse.md)。

## 7. 无源性尝试全景

### QP / spectral projection / active-mode / global damping

**[HYPOTHESIS] 假设：** 对违规奇异模态做局部最小扰动，配合候选筛选和 line search，可比统一缩放保留更多拟合质量。

**[FACT] 实现：** QP 1-2 轮、current clip、reference-band equalization、active-mode min-norm/regularized、candidate screen、adaptive holdout、全局/选择性 damping fallback。

**[FACT] 验证数据：** Test16 的策略能最终达到 sigma `0.9999989`，但 Native order-10 RMS 从约 `0.00321` 退化到约 `0.00422`；s19 order-93 current projection 从 `0.00094449/1.02149` 到 `0.00146364/1.00890`。

**[STRONG INFERENCE] 结论：** enforcement 是有效的安全网，但无法补偿 pole-set 带来的大拟合误差；global damping 的“最终被动”不能被当成算法质量胜利。

### NNLS / GLM / port compression

**[HYPOTHESIS] 假设：** 在 active singular modes 上用压缩 NNLS，可避免完整 Jacobian 并降低修正成本。

**[FACT] 实现：** port/response 坐标压缩、QR/NNLS、top-response active modes；order-93 从完整 33,573 变量压到 372 列。

**[FACT] 验证数据：** order-93 NNLS 最终 `RMS 0.00153409, sigma 1.00839, 117.1s, 549.2MB`；order-94 为 `0.00183628, 1.002285, 117.9s, 543.8MB`。端到端成本仍由 legacy candidates、全频评估和 line search 主导。

**[FACT] 冻结门结果：** 变量压缩已执行，Gate B 未通过，因而不升为默认。**[STRONG INFERENCE]** 压缩子问题不是当前端到端成本和质量的充分解。[Native NNLS 结果](sparam-native-nnls-s19-results.md)

### alternation 与 fit-aware residue LS

**[HYPOTHESIS] 假设：** 固定极点反复 residue refit/passivity，或把违规频带加权进 LS，能够降低修正压力。

**[FACT] 实现：** 1-2 轮 fixed-pole alternation；active-frequency rows，lambda `1e-4..100`，adaptive rounds 与 DC 约束。

**[FACT] 验证数据：** 基础 reweighting 最低 RMS 约 `0.00119098`，但 sigma 仍约 `1.03875`；强 lambda/adaptive 可继续压 sigma，却把 RMS 推至 `0.0037-0.0072`。固定极点 alternation 最好 sigma `1.02699`。

**[FACT] 冻结门结果：** 已测试的 alternation 与 reweighting 均未同时过 RMS/sigma 门。**[STRONG INFERENCE]** 这些结果表现出同一 pole set 上的 RMS/sigma Pareto 冲突，继续增加同类交替轮数缺乏正向证据。

**证据路径：** [fit-aware LS](../runs-sparam/passivity-direction-validation/passivity-aware-residue-ls/summary.json)、[adaptive LS](../runs-sparam/passivity-direction-validation/passivity-aware-residue-ls-adaptive-dc/summary.json)、[alternation](../runs-sparam/passivity-direction-validation/fixed-pole-alternation/summary.json)。

## 8. 非 VF 极点发现的最终三次验证

### stabAAA 多投影

**[HYPOTHESIS] 假设：** 标量 stabAAA 对关键通道、对角和随机双边投影的支持点可聚类成稳定共享极点，并发现 VF 丢失的边缘模态。

**[FACT] 实现：** 固定随机种子、多投影独立 stabAAA、共轭补全/聚类/固定阶选择，再接同一 residue LS 与 enforcement；没有把公开标量代码虚称为 MIMO stabAAA。

**[FACT] 验证数据：** Test16 20/20 投影成功，约 2 GHz cluster 获 20/20 支持；order 13 final RMS `0.00473795`，比同输入同阶 Native `0.000707379` 差 `6.70x`。s19 17/20 投影成功；order 74 final RMS `0.0247999`、sigma `0.9999989`。四个 tangential seeds 均完成，但 selected-cluster overlap 为 `0.2340..0.3191`，低于 `0.5`，因此 reproducibility/seed-overlap gate 失败。

**[FACT] 冻结门结果：** Test16 与 s19 质量门失败，s19 seed-overlap 门也失败，路线 NO-GO。**[STRONG INFERENCE]** 在该投影/聚类实现中，“看见目标模态”没有转化成全矩阵紧凑公共分母。

**证据路径与 authority：** [Test16 报告](sparam-stabaaa-shared-pole-validation-results.md)、[s19 结果报告](sparam-stabaaa-s19-validation-results.md)、[canonical IdEM s19 tuning](sparam-idem-s19-tuning.md)。s19 结果报告固化了 runtime summary 中的 stabAAA fixed-order 结果和 overlap；其中 IdEM direct attribution 状态为 `artifact_unverifiable`（canonical metadata SHA 无效），不能作为一级对照。IdEM order-74 `0.000936916` 来自独立 canonical tuning artifact；据此跨 artifact 计算 `0.0247999 / 0.000936916 = 26.47x`，标为 **[STRONG INFERENCE]**。被忽略的 runtime artifacts 不随实验 worktree 清理进入 Git，结论由本报告和 s19 结果报告保留。

### 矩阵值双侧 Tangential Loewner

**[HYPOTHESIS] 假设：** 真正的 `l_i^H H(mu_i) r_j` / `l_i^H H(lambda_j) r_j` 双侧 pencil 比 D15 stacked scalar 更适合 MIMO 公共极点。

**[FACT] 实现：** 两种 interleaved partition，随机 seeds `17/29/43/71` 与 global-SVD directions，orders `56/60/68/74`；禁止 pole flipping。

**[FACT] 验证数据：** 40/40 候选有 RHP eigenvalues；order 74 每个 config 有 17-23 个 RHP poles，`cond(E_r)` 达 `7.09e5..1.15e7`，截断处无清晰 singular gap。

**[FACT] 冻结门结果：** 没有合法候选进入 LS；NO-GO，未做极点反射。[结果报告](sparam-tangential-loewner-s19-validation-results.md)

### RKFIT / RKToolbox 2.9

**[HYPOTHESIS] 假设：** 正交有理 Krylov 的共享分母优化可以避开 VF/SK 基函数病态，在 order 74 给出稳定公共极点。

**[FACT] 实现：** 官方 RKToolbox 2.9，多响应矩阵数据，两种冻结初始化，`stable=0, reduction=0`；synthetic smoke 以机器精度恢复已知 4 poles。

**[FACT] 验证数据：** `log_damped`：16 RHP poles、internal misfit `0.00793432`、`23.50s`；`linear_damped`：1 RHP pole、misfit `0.000350241`、`22.30s`。二者都未形成完整共轭稳定集合；internal misfit 不是最终 S-RMS。

**[FACT] 冻结门结果：** 原始稳定 pole discovery NO-GO；`stable=1` 的事后反射不属于冻结主路径。[结果报告](sparam-rkfit-s19-validation-results.md)

## 9. 为什么 Test16 不能单独区分算法，s19 如何校准

**[FACT] Test16 很容易在较低 order 达到产品 RMS。** Native order 13 与 IdEM order 10 都低于 `0.001`，完整谱主要差异集中在少数高频边缘模态。它非常适合诊断 relocation collapse、2 GHz 模态覆盖和 source attribution，却容易产生两种误判：

- 低 order 选择器没有足够容量表达投影候选，会把“候选聚类策略”误判成“算法本体失败”；
- 单个边缘模态被看见后，容易把局部频带改善误判成全矩阵公共分母改善。

**[FACT] s19 更适合 fixed-order efficiency gate。** 它有 19 ports、361 响应、826 点、DC 到 2 GHz；IdEM 的阶数曲线提供 `56: 0.00145259`、`60: 0.00124456`、`68: 0.00103769`、`74: 0.000936916` 的清晰校准。order 74 是质量门，`<=68` 达标才是阶数效率胜利。

**[STRONG INFERENCE] 正确分工：** Test16 用于机制诊断，s19 用于算法优劣主门，完整 corpus 用于产品 promotion。stabAAA 的 s19 补跑正是对早期 Test16 判断的必要校准；它证明 NO-GO 并非只因 Test16 order 太小。

## 10. 已排除路线、保留资产与剩余差距

### 已排除为当前生产候选

- [FACT] 高频注入/门控、relocation weighting、静态/动态 `c_res` 正则：不再继续旋钮 sweep。
- [FACT] D11 data-only pole set、D15 stacked-scalar Loewner：没有合法或合格固定阶候选。
- [FACT] MFT-NNLS Python 与 MATLAB 原版：s19 拟合质量决定性失败。
- [FACT] stabAAA projection、Tangential Loewner、RKFIT `stable=0`：均按预定门停止，不生产化。
- [FACT] current projection、active-mode、compressed NNLS、alternation、fit-aware residue LS：作为默认 enforcement 替代均未过 Gate B。

“排除”仅指**本次已实现配置与已冻结数学路径**，不构成对算法所有可能变体的数学不可能性证明。

### 产品化保留的 Native 能力

- [FACT] 目标驱动 auto order、全原始频点评估、稳定/共轭/互易模型表达。
- [FACT] `off/check/enforce` 无源策略、adaptive holdout、final sigma audit、受控 global damping 安全网。
- [FACT] 大端口低内存/分块 residue LS、流式评估、SPICE export 与可审计 fit report。
- [FACT] 高频 pair、frequency gate、residual injection、dynamic `c_res`、relocation frontier、NNLS/active-mode 等实验能力保留为默认关闭的研究资产，不冒充生产胜利。
- [FACT] fixed-pole attribution、projection artifacts、Loewner/RKFIT/stabAAA adapters、输入 hash/provenance/resume machinery 可复用于未来有具体实现的候选。

### 与 IdEM 的剩余差距

- **[FACT] 阶数效率：** 91/163/166 port 分别落后 `1.30x/1.67x/2.25x`。
- **[FACT] 搜索时间：** 同三例分别落后 `4.22x/2.88x/3.29x`；s30 Native 虽成功但耗时 `1820s`。
- **[FACT] s19 前沿：** Native 能在 order 93-95 得到 raw RMS 低于 `0.001`，但 sigma `1.012-1.021`；IdEM order 74 已满足最终契约。
- **[STRONG INFERENCE] 共同根因：** Native 用更多 poles 和更多 relocation 工作换取质量，且得到的 raw model 更难低代价 enforce。
- **[HYPOTHESIS]** IdEM 可能使用更好的初始化、极点管理、停止或候选选择；没有 artifact 支持进一步描述其私有算法。

## 11. 建议

1. **停止无前置审计的算法枚举。** 任何候选在通过许可证、可调用 API、矩阵值/块 MIMO 公共分母能力和稳定性语义审计前，不进入实现 spike。本文不按算法名称封禁未来路线。
2. **把 source attribution 固化为所有新候选的第一门。** 新方法必须先输出稳定、共轭、固定阶 pole artifact，再走相同 full-grid residue LS；禁止用自己的 residue/enforcement 混淆 pole quality。
3. **继续维护 Native 产品线，而不是替换它。** 优先优化已成功路径的共享计算、分块评估、checkpoint early stop 和大端口 runtime；这些是已证实能缩短时间且不改变数学结果的工程工作。
4. **只有出现具体可运行实现或明确新数学约束时再立算法 spike。** 合格触发条件包括：原生稳定约束而非事后 pole reflection；矩阵值/块 MIMO 公共分母；可审计许可证；s19 order-74 smoke 能直接产出稳定共轭 pole set。
5. **保持三级 case 纪律。** Test16 做机制诊断；s19 orders `56/60/68/74` 做主算法门；只有 s19 通过，才跑完整 corpus 和 production promotion。

## 12. 最终判断

**[FACT] 在本轮冻结实现和门槛内，我们没有找到优于 Native 的新 pole-discovery backend。** 已明确停止的候选包括 D4/D5/D7/D8/D11/D15、MFT-NNLS、stabAAA projection、Tangential Loewner、RKFIT `stable=0`，以及未通过 Gate B 的无源修正路线；D6/D9/D10 和 source attribution 是诊断/控制，不写成被“排除的算法”。

**[STRONG INFERENCE] 当前最理性的工程决策是保留 Native 作为唯一生产后端，保留研究基础设施，不再用 enforcement 或局部高频补丁掩盖 pole discovery 问题。** 下一次算法研究应由一个满足上述稳定 MIMO 前置条件的具体实现触发，而不是由候选算法名称触发。
