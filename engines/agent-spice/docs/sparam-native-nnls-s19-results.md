# S19 Native NNLS 无源性试验结果

日期：2026-07-11

## 契约与口径

- 输入：[5power_19port_withcap_122324_202459_11476_DCfitted.s19p](/C:/Users/z3312/code/agent-spice/user_input/spara/5power_19port_withcap_122324_202459_11476_DCfitted.s19p)
- 拟合与验收频点：原始 826 点；最终无源性验证额外加入自适应频点（报告中为 927 点）。
- RMS：所有 S 通道与频点的平均型 complex S-RMS。
- 无源性：最终 `max sigma <= 1 + 1e-6` 才算 accepted。
- 所有 enforce trial 禁用 global damping；因此没有通过时不能把结果包装成“被动”。

## 对照结果

| raw topology | enforcement | raw RMS | raw sigma | final RMS | final sigma | enforce s | RSS MB | 状态 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 93 = 45 real + 24 complex | off | 0.000944489 | 1.021486 | 0.000944489 | 1.021486 | 0.0 | 110.2 | `rms_preserved_but_nonpassive` |
| 93 = 45 real + 24 complex | current projection | 0.000944489 | 1.021486 | 0.001463640 | 1.008899 | 114.1 | 548.9 | `passivity_improved_but_rms_lost` |
| 93 = 45 real + 24 complex | NNLS, top-1 response/mode | 0.000944489 | 1.021486 | 0.001534091 | 1.008390 | 117.1 | 549.2 | `passivity_improved_but_rms_lost` |
| 94 = 46 real + 24 complex | off | 0.000871138 | 1.016127 | 0.000871138 | 1.016127 | 0.0 | 110.7 | `rms_preserved_but_nonpassive` |
| 94 = 46 real + 24 complex | current projection | 0.000871138 | 1.016127 | 0.001824883 | 1.000439 | 116.9 | 548.8 | `passivity_improved_but_rms_lost` |
| 94 = 46 real + 24 complex | NNLS, top-1 response/mode | 0.000871138 | 1.016127 | 0.001836277 | 1.002285 | 117.9 | 543.8 | `passivity_improved_but_rms_lost` |

原始与 current order-93 artifact：

- [raw order-93 report](/C:/Users/z3312/code/agent-spice/runs-sparam/native-topology-order-search-s19-full-v1/order93-real45-complex24-it12/fit_report.json)
- [current order-93 enforcement report](/C:/Users/z3312/code/agent-spice/runs-sparam/native-topology-order-search-s19-full-v1/order93-real45-complex24-it12-enforce/fit_report.json)

本轮可复现 NNLS artifact：

- [order-93, top-1 response](/C:/Users/z3312/code/agent-spice/runs-sparam/native-nnls-passivity/s19-order93-response1/order93-real45-complex24-it12/summary.json)
- [order-94, current projection](/C:/Users/z3312/code/agent-spice/runs-sparam/native-nnls-passivity/s19-order94-current/order94-real46-complex24-it12/summary.json)
- [order-94, top-1 response](/C:/Users/z3312/code/agent-spice/runs-sparam/native-nnls-passivity/s19-order94-response1/order94-real46-complex24-it12/summary.json)

## 压缩是否真的发生

order-93 的 NNLS candidate 在本次记录中将完整变量空间从 33,573 列压缩为 372 列：4 个响应、每个响应 93 个 residue 坐标；随后仍受现有 `passivity_active_variables=3072` 上限约束，但压缩后的实际活跃列为 372。该信息已写入 `selected_source_diagnostic`。因此“没有构造完整 active-mode Jacobian”这一点已被实测 artifact 证明。

但本轮整体 RSS 仍约 544--549 MB，enforcement 时间也仍约 117 秒。原因是当前整个 enforcement pipeline 仍同时生成 legacy matrix-projection 候选、全频候选评估和多轮 line search；NNLS 子问题压缩本身尚未成为端到端主导成本。

## 结论

1. NNLS 的数学路径和响应坐标压缩已接通，且能真实降低 sigma；并非只停留在小合成测试。
2. 它尚未满足 Gate B：两个 frontier raw model 都未达到 `sigma <= 1+1e-6`，且 RMS 都越过 0.001。
3. 当前结果不支持把 NNLS 升为 Native 默认，也不支持声称它已解决 IdEM 差距。
4. 该实验更强地支持规格中的下一步：在 fitting 阶段保留并排序“RMS 有修正余量、pre-sigma 低”的候选，而不是继续向同一 raw candidate 叠加 residue 修正器。NNLS 可作为那个前沿评分的修正成本估计器。

## Fit-aware frontier 首次验证

新增的内部 `native_relocation_frontier_enabled` 会保留每轮 relocation 的公共极点 checkpoint，以 `raw RMS + passivity_weight * max(0, sigma-1)` 排序；默认关闭，未改变生产路径。s19 的 `46 real + 24 complex`、order-94 试验结果为：

| 最大 relocation | 保存 checkpoint | 被选 checkpoint | 最终 RMS | pre sigma |
| ---: | ---: | ---: | ---: | ---: |
| 8 | 8 | 7 | 0.001137921 | 1.024933 |
| 9 | 9 | 8 | 0.001127640 | 1.020566 |

两个 artifact：

- [iteration 8 frontier report](/C:/Users/z3312/code/agent-spice/runs-sparam/native-sota-baseline/s19-order94-iter8-fit-aware/order94-real46-complex24-it8-lin/fit_report.json)
- [iteration 9 frontier report](/C:/Users/z3312/code/agent-spice/runs-sparam/native-sota-baseline/s19-order94-iter9-fit-aware/order94-real46-complex24-it9-lin/fit_report.json)

这个 topology 在当前代码下没有复现旧的“第 8 轮近无源、第 9 轮跳升”形态，而是 sigma 单调改善；因此它验证的是 checkpoint 保留、排序和阶数上限不被破坏，不是对旧结论的重新确认。完整语料下需要以候选的实际 NNLS 修正结果，而不是只靠 pre-sigma 代理，决定是否启用该选择器。
