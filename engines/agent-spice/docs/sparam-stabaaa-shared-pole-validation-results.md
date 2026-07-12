# stabAAA 固定阶数共享极点验证结果

## 结论

**【判定】NO-GO：`fixed_order_not_better_than_native`。** Test16 的 order-10 final RMS 为 `0.08069790004418083`，超过 `0.001` 主质量门约 `80.70` 倍。更关键的是，同输入、同 order 13 的 stabAAA final RMS 为 `0.004737952989337812`，而 canonical Native 为 `0.0007073785909896621`；stabAAA 是 Native 的 `6.697902720959016` 倍，直接满足设计中的 NO-GO 条件“固定阶数不优于 Native”。

**【限制】这不是完整的 attribution 同阶 benchmark。** 控制器观测命令运行约 `3604 s` 后终止，但没有保存独立 timeout log，故该时长是控制器观测而非 artifact 内计时。四个 stabAAA attribution summary 已写完；根 `manifest.json` 的 `attribute.status` 仍为 `running`，且 attribution 下只有 `stabaaa_projection/`，没有 index、Native 或 IdEM 目录。本文的 Native order-13 对照来自既有 canonical artifact，不声称本次 attribution 已跑完三种方法。

## 事实来源

除明确标为“判定”或“限制”的文字外，下列机器数值均来自未提交的运行目录 `runs-sparam/stabaaa-shared-pole-validation/`：

- 总决策镜像：`final-decision-summary.json`，由 PowerShell 读取各 order 的 `summary.json` 后生成，不重新运行 attribution。
- 每阶结果：`attribution/stabaaa_projection/{6,8,10,13}/summary.json`。
- 投影与输入：`projections.json`、`projections.npz`。
- 原始 stabAAA 结果：`stabaaa/*.json`。
- 聚类与定阶：`pole_clusters.json`、`orders/<order>/poles.json`。
- 环境：`preflight.json`；上游示例：`upstream-examples/*/result.json`。
- Native order-13 权威对照：`../agent-spice/runs-sparam/full-corpus-target-0p001/04-91p-Test16/native/model_order13/fit_report.json`。

### Artifact authority map

| 路径 | 权威用途 |
| --- | --- |
| 根 `runs-sparam/stabaaa-shared-pole-validation/preflight.json` | 授权重试后的最终环境事实：MOSEK license `valid`、preflight `ok: true` |
| 根 `projections.json`、`stabaaa/`、`pole_clusters.json`、`orders/`、`attribution/stabaaa_projection/` | 本次授权重试的算法与 attribution 事实 |
| 根 `final-decision-summary.json` | 从上述权威 JSON 与 canonical Native fit report 生成的机器判定镜像 |
| `test16/summary.json`、`test16/preflight.json` | 首次 preflight 失败的历史产物，不参与最终判定 |

**【解释】** `test16/summary.json` 中的 `mosek_missing` 与根 preflight 的 `valid` 并不冲突：前者记录发现 MOSEK 之前的失败尝试，后者记录用户指出安装位置后、带正确 MATLABPATH 和许可的授权重试。最终判定只采用根产物。

## 环境与可复现性

| 项目 | 【事实】观测值 |
| --- | --- |
| 本仓库代码 commit | 控制器记录的运行时工作树 commit `07ab04fcebc1d7f9244c8f2170bb145fbe7c9414`；未写入 runtime manifest，不构成独立机器 provenance |
| stabAAA commit | `e070a26af59ce3fff4a0a9eed6af0fcb06c14c16` |
| 输入 | Test16，91 端口，611 个频点，0 至 2 GHz |
| 输入 SHA-256 | `f8055fe88d5aa9e1212359c53f37c9f261c07f156f1d7b1f8d4991ea08047996` |
| MATLAB | R2024b，`24.2.0.2712019` |
| YALMIP | `C:/Users/z3312/code/agent-spice-external-tools/YALMIP` |
| MOSEK | 11.2.2；微型求解 `OPTIMAL`；许可状态 `valid` |
| 无 LICENSE 处理 | 用户明确授权隔离研究运行；源码未复制进本仓库 |
| 上游示例 | Absorber exit 0，`19.5663936 s`；ISS exit 0，`14.6102959 s` |

## 投影与候选

**【事实】** 共生成 20 个非退化投影：8 个关键通道、8 个对角通道和 4 个双边随机切向投影，随机种子为 `17/29/43/71`。20 个 stabAAA 调用全部完成，每个返回 59 个极点；单投影运行时间合计 `6.6291075 s`。聚类产物含 270 个 cluster，固定选择器精确形成 order `6/8/10/13`。

**【事实】** 与约 2 GHz 对应的 cluster 中心虚部为 `12569630613.29793 rad/s`，得到 20/20 投影支持，并进入 order 8、10、13。这说明投影路径看到了目标边缘模态，但“看见模态”没有转化成合格的固定阶数矩阵拟合质量。

## 固定阶数结果

下表由四个 `attribution/stabaaa_projection/<order>/summary.json` 字段汇总；“时间”仅是 enforcement 时间，artifact 没有提供可分离的 residue LS 时间。

| order | pre RMS | final RMS | pre max sigma | final max sigma | enforcement (s) | peak memory (MiB) | LS condition |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 6 | 0.0585349536 | 0.0800425718 | 2.89330220 | 0.97291205 | 487.4805 | 317.8477 | 1.535568 |
| 8 | 0.0578874452 | 0.0803652060 | 2.84321613 | 0.96041153 | 555.4779 | 328.2500 | 2.315852 |
| 10 | 0.0578477891 | 0.0806979000 | 2.84050665 | 0.96329741 | 677.6262 | 333.1289 | 2.374060 |
| 13 | 0.00364174764 | 0.00473795299 | 1.08425585 | 0.99999890 | 1594.3904 | 364.9570 | 12.636123 |

**【事实】** 四个阶数的 enforcement 都把最大奇异值压到 1 以下，但均增加 RMS。order 10 的 final RMS/门槛比为 `80.69790004418083`；order 13 为 `4.737952989337812`。

## 与 canonical Native 的同阶核验

**【事实】** canonical Native order-13 `fit_report.json` 记录：输入 SHA-256 为 `f8055fe88d5aa9e1212359c53f37c9f261c07f156f1d7b1f8d4991ea08047996`，与本次 Test16 完全相同；`expanded_model_order` 为 13；final mean RMS 为 `0.0007073785909896621`；`passive_after_enforce` 为 `true`，final max sigma 为 `0.9999988999999995`。

| 同输入、同 order 13 | final RMS | final max sigma | 被动 |
| --- | ---: | ---: | --- |
| stabAAA projection | 0.004737952989 | 0.9999989000000004 | 是 |
| canonical Native | 0.000707378591 | 0.9999988999999995 | 是 |

**【判定】** 两者均被动，但 stabAAA final RMS 是 Native 的 `6.6979` 倍。因此即使本次 Native attribution 子阶段没有启动，canonical artifact 已提供同输入、同阶、同 RMS 定义的机器可核验证据，足以判定“固定阶数不优于 Native”。

## 验收逐条对照

| 设计验收条款 | 结果 | 证据与边界 |
| --- | --- | --- |
| Test16 order 10 final RMS `<= 0.001` 且被动 | **FAIL** | final RMS `0.0806979000`；final sigma `0.96329741`。被动性通过，但质量决定性失败。 |
| Test16 order 10 不高于 canonical IdEM order 10 的 1.25 倍 | **未执行** | IdEM attribution 阶段未开始。主绝对质量门已失败，无需依赖 IdEM 比值即可 NO-GO。 |
| s19 至少一个共同阶数改善，final RMS 回退不超过 10% | **early reject，未执行** | Test16 首要质量门已经决定性失败；继续 s19 不能把本候选变成 GO，只会额外消耗数小时。不得把该状态表述为完成了跨 case 验证。 |
| 预定随机种子可复现 | **投影执行通过，端到端 GO 条件不成立** | 四个固定种子均运行成功；目标高频 cluster 获 20/20 投影支持。没有质量合格的成功结果可供复现。 |
| 时间单独报告，超过 IdEM 5 倍时仅 `quality_only` | **仅部分报告** | stabAAA 调用合计 `6.6291 s`，四阶 enforcement 合计 `3314.9750 s`；IdEM 阶段未开始，不能计算倍数，也不能声称达到时间效率。 |

### NO-GO / PARTIAL 分类核验

| 分类条件 | observed | 是否触发 |
| --- | --- | --- |
| NO-GO：固定阶数不优于 Native | order 13 stabAAA `0.004737952989`，Native `0.000707378591`，输入 hash 相同且均被动 | **是，决定性** |
| NO-GO：依赖 IdEM 极点或人工挑选 | 候选评分未读取 IdEM；投影按预定规则生成 | 否 |
| NO-GO：投影不足或高频模态多数种子不可见 | 20/20 成功，约 2 GHz cluster 获 20/20 支持 | 否 |
| NO-GO：LS 显著病态导致 enforcement 失败 | 条件数 `1.54` 至 `12.64`；四阶 enforcement 均完成 | 否 |
| PARTIAL：极点诊断改善但 final RMS 未过门 | 约 2 GHz cluster 可见，但 order 10/13 质量不合格 | 是，但被更强的同阶 Native NO-GO 覆盖 |
| PARTIAL：仅 Test16 改善或质量过门但过慢 | Test16 同阶未改善，且质量未过门 | 否 |

## 超时与 early reject

**【事实】** 控制器观测顶层 attribution 约运行 `3604 s` 后终止，未保存独立 timeout log。可审计 artifact 只证明阶段未完成：manifest 仍为 `running`，四个 stabAAA summary 存在，而 index、Native、IdEM attribution 目录不存在。已完成的 enforcement 时间合计约 `3314.975 s`，其中 order 13 为 `1594.390 s`。

**【判定】** 不运行 s19 是一次基于预先主门槛的 early reject，而不是“s19 验证通过”或“跨 case 结论”。GO 要求 Test16 与 s19 同时满足；Test16 的 order 10 和 13 已远高于 `0.001`，任何 s19 结果都无法逆转本 spike 的 NO-GO。

## 最终决定

**【判定】`NO-GO: fixed_order_not_better_than_native`。** 当前“多投影标量 stabAAA -> 聚类 -> 固定阶数共享极点”的候选生成方式能稳定捕获约 2 GHz 模态，但 order 13 的矩阵拟合误差仍为同阶 canonical Native 的 `6.6979` 倍。按照批准的研究 spike 范围，本路线在此结束，不接入 Native 后端；后续候选应另开 Loewner 或 RKFIT 的独立 spec。
