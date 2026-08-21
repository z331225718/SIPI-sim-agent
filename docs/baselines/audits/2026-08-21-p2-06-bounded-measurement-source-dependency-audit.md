# P2-06 bounded measurement source/dependency audit

## 结论

第二轮审计选择了原项目语义最接近当前 typed RC/PWL core 的候选：`TRAN`
分析上固定 `V(out)` 的 `MAX`。它仍不能在当前产品面实现。原因不是缺少一个
`max()` 调用，而是原项目的 measurement 是一条完整的 parser、point-set、窗口、
插值、结果和误差语义链；当前 SIPI 冻结明确没有这条 contract。故本轮不新增
Rust API，不把 arbitrary netlist 伪装成 fixed RC/PWL，改以 source/dependency
evidence 精确记录最小缺口。

证据见
`docs/baselines/p2-06-bounded-measurement-source-dependency-audit.v1.yaml`。
产品基线绑定 `b6071779d8164e685d15ddf45c19dcb6b2553c78`，原项目绑定
`2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5`。各 `source_inventory` 的 40 字符值
都是 `mixed_tree_and_blob_git_object_ids_sha1` 下的 Git tree/blob object ID，
不是内容 SHA；内容摘要若存在则单独命名为 `*_sha256`。

## 原项目依赖图

原项目 pinned `netlist.rs`（blob
`83ffa04c90fb7c523875fb93c64b1f245793bcd1`）在 773 的
`Deck::parse_file` 进入通用 deck parser。measurement 结构和语法在 526、535、
553、623，以及 2291 的 `parse_measurement`、2619 的 target parser、2674 的
event parser。

`simulator.rs`（blob `ed5712567420013d70c39a14257e1f77004a64b4`）的
`evaluate_measurements`（378）不是单一 reduction：它先在 505 收集并按分析和
时间排序 samples，再由 579 解析 V/I、real/imaginary/magnitude/phase target；
`FIND`/`DERIV` 依赖 650 的插值，`MIN`/`MAX`/`AVG`/`RMS`/`INTEG` 依赖 712 的
窗口构造和 738 的积分规则，事件类 measurement 还依赖 crossing/interpolation
语义。`result.rs`（blob `f13c37b9fd367c5cb66a148deecedcea7d12b794`）在 22 定义
`MeasurementResult`，并在 52 将其放入 `SimulationResult.measurements`；CLI
（blob `a333857287fc093f2f1fa515b135fe31a2bc9eb1`）在 207、231、255/268 把
parser、point retention 和 measurement JSON 串到生产路径。

原引擎 `Cargo.toml`（blob `b56d29811d0293c878b22485523f03ea06dc2d91`）的直接
依赖为 `faer`、`num-complex`、`serde`、`serde_json`、`thiserror`、`vecfit`。
当前 `sipi-tran`（blob `972d8ef4c5a49da67d9dded266e0b19037cece86`）只有
`sipi-runtime` 与 `sipi-types`；依赖差异本身不是阻塞的充分理由，但它证明
原始 point/result/parser 闭包不能作为现有 typed core 的隐含能力。

## 候选 MAX 与最小缺口

若把候选收窄到 `tran`, `V(out)`, whole reported axis，仍需先定义：

1. 请求如何声明 measurement 名称、操作和目标，以及结果 schema 如何承载 scalar。
2. “reported axis”是否等于原引擎保留的全部 analysis points；当前 SIPI 只报告
   caller 请求的 output axis。
3. 原 `MAX` 的 `FROM`/`TO` 窗口端点可经过 `interpolate_measurement`；而当前
   semantic freeze 将 interpolation 标为 `not_implemented`，不能默默采用某个
   插值或端点规则。
4. 空样本、越界窗口、非有限值、重复名称、错误 stage，以及 compare tolerance
   和 artifact/provenance 绑定如何处理。

这些不是实现细节。它们分别对应新的 contract/schema、生产错误语义、比较政策
和 publication 绑定。当前 P2-03 freeze 将 `measurement_semantics` 固定为
`not_implemented`，将 `arbitrary_netlist` 固定为 `rejected`；P2-06 stage record
将 measurements 固定为 `not_implemented`、parsed circuit 固定为
`not_applicable_current_surface`。因此加一个私有 `max()` helper 既不能成为
P2-06 stage compare，也会制造未声明的生产语义。

## 剩余 blocker

- owner 尚未批准 measurement request/result schema、命名和 scalar artifact shape。
- owner 尚未批准 measurement point-set、窗口端点、插值、非有限值和错误策略。
- owner 尚未批准 measurement compare tolerance 与 provenance/publication 边界。
- generic parser 所需的 grammar、节点/ground、source、include/subckt、device
  subset 和失败分类仍不属于当前 product contract。

在这些输入出现前，主代理应保持 P2-06 generalized parsed-circuit/measurement
为 blocked；不得复制原项目 parser/evaluator，不得加入原项目 solver 依赖，也不
得通过空字段或内部 helper 声称 measurement coverage。
