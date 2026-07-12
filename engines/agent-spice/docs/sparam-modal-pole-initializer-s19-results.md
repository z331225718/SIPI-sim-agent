# s19 全局模态 Pole Initializer 验证结果

## 结论

**[FACT] 判定为 `NO-GO / condition_or_residue_explosion`。** 冻结的全局频率无关模态方案完成了 `24 traces x 2 spacing = 48` 次真实 Native 标量 pole discovery，48/48 均成功并形成四个精确固定阶数候选；但 order 74 full-grid raw RMS 为 `0.007696836821`，约为 canonical Native order-74 raw RMS `0.001721840685` 的 `4.47x`，且 residue/condition 数值门失败。因此 Phase A promotion gate 未通过，按计划没有运行 passivity enforcement 或 trust-region relocation。

## 冻结身份与方法

- 输入 SHA-256：`87fccc96196d8c149d1b3ba985701dd56a78f5d9904984f55f8161c39cdd7c7e`。
- 数据规模：19 ports、826 points；pole discovery 仅排除首个 0 Hz 点，fixed-pole residue LS 仍使用全部 826 点。
- 全局左右模态 rank：8；选择8条对角和16条非对角 trace。
- 每条 trace 使用 effective order 12、6轮 Native scalar VF，分别采用 linear/log 初始化。
- 固定共享阶数：`56/60/68/74`；不使用 Native/IdEM poles，不做 pole flipping 或人工补极点。
- 数值停止门：condition `<=1e12`，最大 residue/input 幅值比 `<=1e15`，raw early reject `>0.01`。

## Phase A 结果

| Order | Raw RMS | Raw max sigma | Condition | Max residue/input | LS runtime | 结果 |
|---:|---:|---:|---:|---:|---:|---|
| 56 | 0.010623162659 | 1.056195204 | 4.595e8 | 1.906e16 | 2.676 s | 数值门失败，且 raw > 0.01 |
| 60 | 0.008677236332 | 1.053757169 | 3.722e9 | 2.185e16 | 2.785 s | residue ratio 门失败 |
| 68 | 0.007745942627 | 1.044708002 | 1.599e11 | 2.076e17 | 3.032 s | residue ratio 门失败 |
| 74 | 0.007696836821 | 1.044633201 | 9.407e12 | 2.076e17 | 3.235 s | condition 与 residue ratio 门均失败 |

48次 scalar discovery 的累计 fitter runtime 为 `0.4356 s`，没有 proposal failure。order 74 不仅未满足 absolute promotion 门 `0.0015`，也没有相对 canonical Native 改善10%；其 raw sigma 为 `1.04463`，即使忽略数值爆炸也不具备直接 promotion 条件。

## 证据边界

**[FACT]** 结果仅否定当前冻结实现：全局 rank-8 左右子空间、24条能量选 trace、scalar Native VF、当前聚类及固定阶数选择。它不否定所有 modal 方法。

**[STRONG INFERENCE]** 与随机 stabAAA 投影相同，“各投影能产生稳定 poles”没有转化成适合完整矩阵的紧凑公共分母；order 增长只把 raw RMS 从约 `0.0106` 降至 `0.00770`，同时显著放大 residue 和条件数。

**[FACT]** 首次运行因 s19 含0 Hz、旧 scalar discovery 输入检查不接受DC而产生48个结构化失败。该接口缺陷已通过测试修正为只在 discovery 排除单个DC点；上述表格全部来自修正后的独立 `phase-a-v2` artifact，未把首次无效运行计入算法结论。

## 可审计 artifact

- 目录：`runs-sparam/modal-pole-initializer-s19-phase-a-v2/`
- `summary.json` SHA-256：`75a8ab1227dca6652b63645e26396835eda849ada9bc42f174b563702a98937a`
- `ledger.json` SHA-256：`fc4f246588a324dbdd98fed2073a09514835e5e0f804e3e479f02bbb2eb69961`
- fit records SHA-256：`df247304a17f78235a34039049d9a1cc0e2c4f340b85ca2578a39e49481f30a0`
- pole pool SHA-256：`ea61b256f2a6dba9be7b313611fce29ae3c42d3ba0afecb8231cec0a89136241`

最终停止规则已触发：不执行 Task 4 trust-region，不扩展 rank、trace 数或聚类参数 sweep。
