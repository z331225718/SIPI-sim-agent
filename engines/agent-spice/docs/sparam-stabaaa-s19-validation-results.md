# stabAAA s19 固定阶数补充验证结果

## 结论

**NO-GO：s19 主验证集确认公开标量 stabAAA 多投影路线不具备固定阶数质量竞争力。** Test16 的历史结论降为辅助证据后，s19 order 74 的 final RMS 仍为 `0.024799875064760273`，是 `0.001` 主质量门的 `24.80` 倍，也是 accepted IdEM order-74 RMS `0.0009369159680584244` 的 `26.47` 倍。四个阶数最终均被动，但没有 order `<=68` 的阶数胜利，也没有 order 74 的质量平价。

## 冻结契约与环境

- 输入 SHA-256：`87fccc96196d8c149d1b3ba985701dd56a78f5d9904984f55f8161c39cdd7c7e`，19 端口、826 点、0 至 2 GHz。
- 固定阶数：`56/60/68/74`；四个 `orders/<order>/poles.json` 均为 `selected` 且精确满足目标阶数。
- stabAAA commit：`e070a26af59ce3fff4a0a9eed6af0fcb06c14c16`；MATLAB R2024b、YALMIP、MOSEK 11.2 许可证均通过 preflight。
- 无 LICENSE 代码仅按用户授权隔离运行，未复制源码。
- `mmax=40` 在运行前写入 addendum 和 case config；17 个成功投影均返回 79 个极点，因此没有发生 `order_unavailable`，也没有人工补极点。

## 实测结果

| order | pre RMS | final RMS | pre max sigma | final max sigma | enforcement s | LS condition |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 56 | 0.01739724763 | 0.04129888105 | 1.384717832 | 0.9999989000 | 78.4748 | 343.678 |
| 60 | 0.01396046544 | 0.03037779783 | 1.441990983 | 0.9999989000 | 149.7456 | 1,862.991 |
| 68 | 0.009256977433 | 0.05087643307 | 1.353726404 | 0.9999989000 | 64.4810 | 28,605.507 |
| 74 | 0.007061903781 | 0.02479987506 | 1.303845134 | 0.9999989000 | 83.5020 | 483,591.706 |

enforcement 合计 `376.2034 s`；20 个 stabAAA runner 的算法内计时合计 `7.9228 s`。峰值内存最高 `257.47 MiB`。随着阶数上升，pre RMS 改善，但 LS 条件数与 residue 尺度快速恶化；enforcement 后误差放大，order 68 甚至比 order 60 更差。这表明候选集合不是可用于被动全矩阵逼近的紧凑共享极点集。

## Machine decision

`runs-sparam/stabaaa-s19-validation/summary.json` 现由 s19 专用判定器从 attribution 与投影 artifacts 聚合，不再复用 Test16 验收模板。其最终标签为 `s19_fixed_order_quality_failed`，五项条件分别记录：order-74 RMS `0.024799875064760273 <= 0.001`（失败）、相对 IdEM 比值 `26.46968982304056 <= 1.25`（失败）、最小合格阶数 `unavailable <= 74`（失败）、最差随机种子 cluster overlap `0.23404255319148937 >= 0.5`（失败）、order-74 sigma `0.9999988999997765 <= 1.000000001`（通过）。所有 `observed/threshold/passed` 字段均为非空 artifact 聚合值。

## 投影与复现性

20 个投影中 17 个完成，三个确定性通道因 `runner_output_failed` 失败；四个随机切向种子全部完成并各返回 79 个极点。聚类形成 256 个 cluster。四个随机投影对最终所选 cluster 的覆盖率为 `0.2340` 至 `0.3191`，低于冻结的 `0.5` 复现门，因此即便忽略质量失败，也不能给出稳定共享极点结论。

## IdEM 证据边界

accepted IdEM order 74 数值来自 canonical `docs/sparam-idem-s19-tuning.md` 及对应 `stagnation-alpha0p01` artifacts。管线尝试直接把原 `trial.json` 当 attribution metadata 读取时，因其没有顶层 `input_sha256` 被严格 loader 标记为 `artifact_unverifiable`；本报告不把该失败误写成 IdEM 算法失败，也不声称重新运行了 IdEM residue attribution。路线判定并不依赖细微的同阶差值：stabAAA order 74 已比绝对 `0.001` 门差 24.80 倍。

## 与 Test16 历史的关系

Test16 结果继续保存在 `docs/sparam-stabaaa-shared-pole-validation-results.md`，只证明路线能发现局部高频模态。s19 是本次路线级主门；其结果排除了“Test16 阶数太小导致误判”的可能。因此结论从“Test16 early reject”升级为“难例 s19 独立 NO-GO”，后续应转向 Tangential Loewner，再按既定顺序验证 RKFIT。

## 运行 artifact

机器事实位于未提交目录 `runs-sparam/stabaaa-s19-validation/`：`preflight.json`、`projections.*`、`stabaaa/*.json`、`pole_clusters.json`、`orders/*/poles.json`、`attribution/*/*/summary.json`、`summary.json` 与 `report.md`。`summary.json` 是 machine decision 的权威来源，`report.md` 由它只读生成；本文表格逐项读取 attribution summary，并明确引用该 machine decision。runtime artifacts 不纳入 Git。
