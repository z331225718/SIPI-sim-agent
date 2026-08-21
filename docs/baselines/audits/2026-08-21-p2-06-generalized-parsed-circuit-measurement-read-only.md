# P2-06 generalized parsed-circuit/measurement read-only audit

## 结论

在当前 SIPI 产品契约下，没有可以合法落地且无需 owner 新决定的最小
parsed-circuit/measurement 纵向切片。本次只提交 exact Git object、许可边界和
生产语义的只读证据，不新增 API，不改变 `crates/sipi-tran`、contracts 或 CLI。

证据记录见
`docs/baselines/p2-06-generalized-parsed-circuit-measurement-read-only-evidence.v1.yaml`。
它绑定产品提交 `fbec03c7cc370a630a0869329263caf0f1294731` 与原项目提交
`2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5`，并绑定相关 tree/blob 对象。证据中
`source_inventory_kind: mixed_tree_and_blob_git_object_ids_sha1` 明确 40 字符值是按路径类型校验的 Git tree/blob object ID，另行
记录的 `fixture_content_sha256` 才是内容摘要。验证器默认只检查产品 Git 对象和
证据中的拒绝结论；只有显式传入 `--agent-spice-root` 才检查外部 Git 对象，不读取
共享 dirty tree 的构建产物。

## 原项目对象与语义

- `native/agent-spice-sim/src/netlist.rs`（blob
  `83ffa04c90fb7c523875fb93c64b1f245793bcd1`）在 `Deck::parse_file`（773）、
  `Parser::parse_line`（1844）、`Parser::parse_line_inner`（1857）构造并解析通用
  deck；元素、分析、源、受控源、端口、子电路和 directive 均在该 parser 路径中。
- 同一文件的 `Parser::parse_measurement`（2291）解析 `.measure`，模型包含
  `Find`、`Derivative`、`Min`、`Max`、`Average`、`Rms`、`Integral`、`When`、
  `Delay`、`Parameter` 等操作。
- `native/agent-spice-sim/src/result.rs`（blob
  `f13c37b9fd367c5cb66a148deecedcea7d12b794`）定义 `MeasurementResult`（22）与
  `SimulationResult.measurements`（52）。`native/agent-spice-sim/src/simulator.rs`
  （blob `ed5712567420013d70c39a14257e1f77004a64b4`）在
  `evaluate_measurements`（378）从仿真点计算测量值。
- `native/agent-spice-sim/src/main.rs`（blob
  `a333857287fc093f2f1fa515b135fe31a2bc9eb1`）在 207 调用 `Deck::parse_file`，
  在 231 根据 `.measure` 决定保留 points，并在 255/268 输出带 measurements 的
  结果。这是原项目 generic simulator 的生产路径，不是当前 SIPI 的 typed TRAN
  contract。

原项目 `native/agent-spice-sim/Cargo.toml`（blob
`b56d29811d0293c878b22485523f03ea06dc2d91`）声明 MIT；顶层 `LICENSE`（blob
`55aac2e4f8c36a978d315efb02815972579b8293`）和 `LICENSE-MANIFEST.md`（blob
`2b549451fdf28b4fbaf524010efbe33c6d49b385`）把 Rust engine 标为本仓
`authorized_private`。这确认了 provenance/classification，但当前 clean-room
边界仍只允许 comparator/reference custody；许可记录本身不构成把 parser 或
measurement evaluator 引入 SIPI 的 owner 决定。

## 当前产品边界

产品提交中：

- `crates/sipi-tran/src/lib.rs`（blob `faa836467dc0e83a9b831c73ce637c03b76b8f59`）
  的 `RcPulseTransientResultV1`（379）只暴露 `time_axis`、`voltage_in`、
  `voltage_out`；模拟入口（489、506、523）只服务固定 one-node RC/PULSE/PWL。
- `crates/sipi-contracts/src/lib.rs`（blob
  `54194613628aafb6cf45c626ee5612e716257dd0`）的 request types（813、845、861）
  都是 `deny_unknown_fields` 的 typed bounded topology，明确不是 netlist 或
  generic circuit。
- P2-03 freeze（blob `123e6a68558e1b56880e6c27b0047776bd6b8de5`）把
  `measurement_semantics` 固定为 `not_implemented`，把 `arbitrary_netlist` 固定
  为 `rejected`；acceptance（blob `52231bb2ca98aa50a530a91dd955717f61164d2f`）
  将 measurements 与 netlist text compatibility 列为 out-of-scope。
- CLI（blob `75e1a028a5c37db4120535c44b839fd79dc17e84`）只发布 bounded result
  JSON；对应测试（blob `11b6c8e7db71260c2b9135001ac1ba18cd0b2830`）验证未知
  `netlist`/`hold_last` 字段被拒绝。P2-06 coverage（blob
  `4002dcc6f6f5e5736577affc09bae5b18c904b30`）因此仍把 parsed circuit 标为
  `not_applicable_current_surface`、measurements 标为 `not_implemented`。

因此，空的 measurements 字段、`.measure` 解析、`MeasurementResult` 转换或
任何 generic netlist fallback 都不是“最小结果面”实现，而是新的 schema/语义
和产品边界。实现它们前至少需要 owner 对 measurement schema/operation、
tolerance/compare policy、parsed-circuit request/device subset 及 publication
boundary 作出决定。

## 未解决输入与后续动作

当前交付是 `read_only_audit_no_product_api`。主代理不应将此记录升级为
publication 或 oracle acceptance；仍保持 specified/non-oracle/source-drift
blocked。未来若 owner 明确授权，应先新增独立 contract/schema 与 provenance
规则，再以清洁来源和独立测试实现受限切片；在此之前不得扩写 fixed RC/PULSE
为 generic SPICE，也不得从原项目复制 parser、measurements、fixture 或旧 binary。
