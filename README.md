# SIPI-sim-agent

面向 SI/PI、串行链路和 IEEE 802.3 COM 分析的统一仿真平台规划仓库。

当前状态：`v0.1` 设计基线。此目录暂不导入三个原项目的源码，先冻结平台契约、迁移门禁和实施顺序，避免把仍在演进且带有本地修改的工作树直接拼接成一个不可验证的大仓库。

## 核心文档

- [SPEC.md](SPEC.md)：产品范围、目标架构、公共契约、引擎边界和验收标准。
- [PLAN.md](PLAN.md)：分阶段迁移计划、任务依赖、质量门禁、投入估算和回滚策略。

## 一句话架构

`SIPI-sim-agent` 立即成为目标治理与产品集成仓，但第一阶段只冻结设计、证据和契约；到 M3 才成为可运行的统一产品入口。数值引擎在通过各自 golden、性能和许可门禁后，才带历史逐步迁入目标 monorepo。

## 已审计来源

| 项目 | 审计 HEAD | 平台角色 | 当前关键约束 |
| --- | --- | --- | --- |
| `agent-spice` | `90f0374` | Circuit/SPICE、RFM、S 参数拟合 | Rust 当前是 binary crate；工作树有本地修改；完整测试尚未执行 |
| `Py-bert-agent` | `5bf6d7e` | Channel、BER、眼图、IBIS-AMI、现有 Rust link core | v1 契约和 Agent-Spice 桥接已落地；native parity gate 尚未解锁 |
| `agent-com` | `034b21b` | IEEE 802.3 COM r4.80 行为复刻 | 当前代码与旧 capability 测试存在策略漂移；大型 MATLAB oracle 需独立工件管理 |

这些提交号只作为审计锚点，不代表可直接迁入的发布基线。正式导入必须来自 clean tag，并记录依赖锁、测试结果、工件哈希和许可来源。

## 目标产品面

- `sipi` 统一 CLI 和后续本地服务。
- Circuit、Channel、COM 三个独立分析引擎。
- 统一的项目文件、能力协商、运行状态、结果信封、工件存储和比较报告。
- 受约束的 Agent 工具层，用于运行、比较、诊断和参数扫描，不绕过仿真契约直接操作数值内核。

实施从 [PLAN.md](PLAN.md) 的 `M0` 基线门禁开始。

## 验证

```powershell
uv run python -B tools/sync_contracts_schemas.py  # schema 变更后同步打包副本
uv run python -B tools/run_all_tests.py           # 单元测试门禁
uv run python -B tools/run_all_tests.py --full    # 含外部探针的 M1 conformance
uv run python -B tools/clean_install_smoke.py     # M2-08：wheel 构建 + 隔离 venv 冒烟
```

仓库以 `schemas/` 为权威 schema 源，打包副本 `packages/sipi-contracts/src/sipi_contracts/_schemas` 不提交到 Git；修改任何 schema 后先运行同步脚本，否则 `sipi doctor` 会按缺失报告。
