# Original VF vs Modal-Z V7 Comparison

日期：2026-07-03

## 结论

当前 V7/modal-Z 已经证明了一个重要收益：在 30-port PDN 上，较低 reduced order 能达到或略优于原版 full-matrix scikit-rf VF 的高阶 Z-domain 误差，且运行时间低两个数量级左右。

但还不能说 V7 已经完成“同一 S 参数用远低于原版的 order 达到交付质量”这个目标，原因是：

- V7 目前还是 report-only reduced Z fit，不输出 SPICE，也不证明 passivity。
- 原版 30p raw order120 已补齐 `z_log_magnitude_rms_error`，但 scaled AC-only 交付报告仍缺同口径 Z log RMS。
- V7 在 19p/163p/166p 上仍失败，说明算法还没有泛化。

所以准确判断是：**V7 在 30p 上已经有明确的 order/runtime 改进信号；还需要补齐 synthesis/passivity 才能替代原版交付链。**

## 比较口径

原版：

- `fit-sparam`
- full-matrix scikit-rf `VectorFitting.auto_fit()`
- 拟合 S 参数，再评估 S/Z 误差
- order 口径：`model_order_max`
- 可输出 SPICE，可进入 passivity/quality gate

V7/modal-Z：

- `fit-modal-z`
- Z-domain modal basis + `peak-poles` + relative LS
- report-only，不输出 SPICE
- order 口径：`scalar_fit_order`，即 reduced modal matrix entry 的 pole budget
- bounded auto-order 在候选集合里逐步加阶并早停

两个 order 数字不是严格同一种数学量；合理比较方式是：**同一输入、同一 Z-domain 误差指标下，达到目标所需的候选阶数、运行时间和失败模式。**

## 30-Port：硬可比结果

输入：

```text
user_input/spara/5power_30port_wocap_121124_221036_4876_DCfitted.s30p
```

30p 是当前最公平的对比对象，因为原版低阶 sweep 和 V7 都记录了 full original frequency points 上的 Z log-magnitude RMS。

| Algorithm | Auto behavior | Order | Z log RMS | Diag Z log RMS | Runtime | Report |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Original VF | auto up to max | 20 | 0.9737 | n/a | 117.4s | `runs-sparam/order-sweep-30p-z/...order20/fit_report.json` |
| Original VF | auto up to max | 40 | 0.7582 | n/a | 438.4s | `runs-sparam/order-sweep-30p-z/...order40/fit_report.json` |
| Original VF | auto up to max | 60 | 0.5287 | n/a | 718.6s | `runs-sparam/original-vf-30p-z-curve-v2/...order60/fit_report.json` |
| Original VF | auto up to max | 80 | 0.5625 | n/a | 793.8s | `runs-sparam/original-vf-30p-z-curve-v2/...order80/fit_report.json` |
| Original VF | auto up to max | 100 | 0.7005 | n/a | 1024.1s | `runs-sparam/original-vf-30p-z-curve-v2/...order100/fit_report.json` |
| Original VF | auto up to max | 120 | 0.4606 | n/a | 680.0s | `runs-sparam/original-vf-30p-order120-z-v1/...order120/fit_report.json` |
| Modal-Z V7 | bounded auto, first pass `<0.5` | 44 | 0.4870 | 0.1355 | 9.5s | `runs-sparam/modal-z-30p-auto-v1-rerun/fit_report.json` |
| Modal-Z V7 | bounded auto, first pass `<0.46` | 52 | 0.4547 | 0.1197 | 9.6s | `runs-sparam/modal-z-30p-auto-v2-target046/fit_report.json` |
| Modal-Z V7 | fixed V7 reference | 56 | 0.4439 | 0.1081 | 5.7s | `runs-sparam/modal-z-30p-order56-v7-rerun/fit_report.json` |
| Original VF | auto up to max, scaled AC-only | 120 | Z log n/a | n/a | 775.5s | `runs-sparam/attack-30port/order120-scale0992-bandpass/fit_report.json` |

直接可证收益：

- V7 auto order44 的 Z log RMS 比原版 order40 低约 **35.8%**：`0.7582 -> 0.4870`。
- V7 auto order44 优于原版 order60/order80/order100，但略差于原版 raw order120：`0.4870` vs `0.4606`。
- V7 auto target 0.46 在 order52 停止，已经略优于原版 raw order120：`0.4547` vs `0.4606`。
- V7 fixed order56 略优于原版 raw order120：`0.4439` vs `0.4606`，order 约减半。
- V7 auto 的 wall time 比原版 order40 快约 **46x**：`438.4s -> 9.5s`；比原版 order60 快约 **76x**。
- V7 fixed order56 比原版 raw order120 快约 **119x**：`680.0s -> 5.7s`。
- V7 order24 的 Z log RMS 已经是 `0.6151`，比原版 order20 的 `0.9737` 低约 **36.8%**。
- V7 bounded auto 确实保留了 auto-fit 行为：候选 order 为 `8,12,16,24,32,44,56`，在 order44 首次过 `0.5 decade` 后停止，没有继续跑到 56。
- 原版 high-order Z log curve 非单调：order60 优于 order80/order100，order120 又改善。这说明 full-matrix VF 继续加 `model_order_max` 不稳定，不能用“再加阶”作为默认策略。

V7 30p auto trials：

| V7 candidate order | Z log RMS | Diag Z log RMS | 结果 |
| ---: | ---: | ---: | --- |
| 8 | 0.7128 | 0.5085 | 未达标 |
| 12 | 0.7979 | 0.5286 | 未达标 |
| 16 | 0.7222 | 0.3404 | 未达标 |
| 24 | 0.6151 | 0.2385 | 未达标 |
| 32 | 0.5475 | 0.1747 | 未达标 |
| 44 | 0.4870 | 0.1355 | 首个通过 0.5-decade 目标 |

V7 30p finer auto trials against original raw order120:

| V7 candidate order | Z log RMS | Diag Z log RMS | 结果 |
| ---: | ---: | ---: | --- |
| 44 | 0.4870 | 0.1355 | 略差于原版 raw order120 |
| 48 | 0.4639 | 0.1167 | 接近原版 raw order120 |
| 52 | 0.4547 | 0.1197 | 首个通过 0.46-decade 目标，优于原版 raw order120 |

30p 尚未证明的事：

- 原版 raw order120 同口径 Z log 已补齐，但原版 scaled AC-only order120 的同口径 Z log 尚未补齐。
- 原版 scaled order120 已可生成 AC-only SPICE，V7 还只是 Z-domain fitted response。
- V7 仍未达到暂定 signoff 目标 `0.1 decade`，只是比原版低阶显著好。

## 19-Port：V7 没有提升

输入：

```text
user_input/spara/5power_19port_withcap_122324_202459_11476_DCfitted.s19p
```

原版历史结果显示，19p 可以通过 order100 + response scaling 得到 AC-only PASS：

| Algorithm | Order / strategy | Metric | Result |
| --- | --- | --- | --- |
| Original VF | order80 raw | S RMS | 0.0244 |
| Original VF | order100 + scale=0.99 | S RMS | 0.0430, AC-only PASS |
| Modal-Z V7 | bounded auto up to 56 | Z log RMS | 2.9473, failed |

V7 19p auto trials：

| V7 candidate order | Z log RMS | Diag Z log RMS | 结果 |
| ---: | ---: | ---: | --- |
| 8 | 3.7379 | 0.9153 | 未达标 |
| 12 | 3.3565 | 0.7247 | 未达标 |
| 16 | 3.4681 | 0.7258 | 未达标 |
| 24 | 3.3419 | 0.6852 | 未达标 |
| 32 | 3.2113 | 0.5137 | 未达标 |
| 44 | 2.9762 | 0.5063 | 未达标 |
| 56 | 2.9473 | 0.6004 | best observed，但仍失败 |

判断：

- 19p 是 V7 的明确反例。
- 该 case 的 basis projection floor 约 `0.2499`，但 rational fit 后变成 `2.9473`，说明问题主要是 pole selection/weighting，不是 order 不够。
- 对 19p 继续提高 V7 order 不是正确方向，应先修 pole/weighting。

## 其它 S 参数：泛化情况

这些 case 目前只有原版 preview S RMS 或 V7 Z log RMS，指标不完全一致，不能做硬胜负判定；但可以看 V7 的失败模式。

| Case | Ports | Original available result | V7 result | 判断 |
| --- | ---: | --- | --- | --- |
| `Test13.s60p` | 60 | preview S RMS 1.3667, sampled | V7 full raw Z log RMS 0.5812, projection floor 0.5797 | V7 fit 贴近 projection floor，主要受 basis 限制 |
| `Test16.s91p` | 91 | preview S RMS 8.3921, sampled | V7 full raw Z log RMS 0.4790, projection floor 0.4626 | V7 有希望，主要受 basis 限制 |
| `Test11.s163p` | 163 | preview S RMS 0.4552, sampled | V7 full raw Z log RMS 1.6603, projection floor 1.6620 | V7 basis 失败 |
| `Test3.s166p` | 166 | preview S RMS 0.3035, sampled | V7 full raw Z log RMS 1.4817, projection floor 1.4816 | V7 basis 失败 |

判断：

- 60p/91p 说明 V7 在大端口上不是必然失败。
- 163p/166p 说明固定全频 hermitian basis 不够，必须做 frequency-partitioned basis 或端口分组 basis。
- 这些结果还不能说明 V7 相对原版完整 auto-fit 的 order 改进，因为原版目前只有 preview/采样报告。

## 当前答案：V7 性能有没有提升？

有，但限定在 30p 上、限定在 report-only Z-domain fitting 阶段：

- **精度提升**：30p 上 V7 auto order52 和 fixed order56 的 Z log RMS 均略优于原版 raw order120；V7 auto order44 略差于原版 raw order120，但优于原版 order100 以内。
- **速度提升**：30p V7 bounded auto 约 9.5-9.6s，fixed order56 约 5.7s；原版 raw order120 约 680s。
- **自动选阶已具备**：V7 会从小 order 候选逐步增加，并在首个达标 order 停止。

还没有完成：

- **泛化没有完成**：19p 明确失败，163p/166p basis 失败。
- **交付链没有完成**：V7 没有 SPICE export、没有 passivity enforcement、没有 AC-only/signoff gate。
- **最终交付改进还没证明**：Z-domain fit 已有 order/runtime 改进，但 V7 还没有 SPICE export/passivity/AC-only gate。

## 下一步 Benchmark 计划

为了真正回答“同样 S 参数是否能比原版少很多 order”，下一步应做以下 benchmark：

1. **30p V7 auto-order 目标改成更接近原版 order120**
   - `--auto-order-max-z-log-rms-error 0.5` 会在 order44 停止，略差于原版 raw order120。
   - `--auto-order-candidates 44,48,52,56 --auto-order-max-z-log-rms-error 0.46` 会在 order52 停止，并略优于原版 raw order120。
   - 下一步应把 coarse-to-fine auto-order 做成内置策略：先粗扫 `8,12,16,24,32,44`，接近目标后自动细扫 `48,52,56`。

2. **V7 bounded auto 固化为 benchmark preset**
   - 候选 order：`8,12,16,24,32,44,56`
   - 目标：先用 `0.5 decade` 探索，再尝试 `0.3 decade`
   - 记录 trials、first passing order、runtime、projection floor

3. **19p 单独作为 fit-limited debug case**
   - 不继续扫高 order
   - 优先修 pole budget 分配、低频 pole、weighting

4. **163p/166p 单独作为 basis-limited debug case**
   - 不继续扫高 order
   - 优先 frequency-partitioned basis 和端口分组 basis

5. **只有当 V7 在 Z log curve 上稳定优于原版后，再做 SPICE/passivity**
   - 否则过早 synthesis 会把算法问题藏到 passivity/synthesis 问题里。
