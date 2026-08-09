# SIPI-sim-agent

面向 SI/PI、串行链路和 IEEE 802.3 COM 分析的原生仿真平台。

当前状态：`v0.2` 产品重基线。终态为第一方 MIT、Rust-only 的统一平台；旧项目只作为已授权 MIT 源码候选或工作树外 oracle，不作为产品运行依赖。

## 核心文档

- [SPEC.md](SPEC.md)：产品范围、目标架构、公共契约、引擎边界和验收标准。
- [PLAN.md](PLAN.md)：纵向能力计划、任务依赖、质量门禁和旧资产处置。
- [ADR-011](docs/adr/ADR-011-native-mit-rust-product-boundary.md)：MIT 第一方源码、Rust-only 终态和旧项目 oracle 边界。

## 一句话架构

一个 Rust workspace 提供 `sipi` CLI、contracts、artifacts、runtime、pipeline 以及 TRAN、Channel、IBIS-AMI、COM 内核；旧 Python/MATLAB/可执行文件仅在发行边界外生成行为规格和比较证据。

## 旧项目定位

| 项目 | v0.2 角色 | 当前关键约束 |
| --- | --- | --- |
| `agent-spice` | MIT Rust TRAN 候选与外部 oracle | 逐文件来源/依赖审计后才可 promotion；Python/旧 bundle 不发布 |
| `Py-bert-agent` | Channel/IBIS-AMI 黑盒 oracle | BSD/非 MIT 源码和派生历史不迁入产品；Channel 由 clean-room Rust 重做 |
| `agent-com` | MIT 行为/源码参考与外部 oracle | 最终运行时移植为 Rust；MATLAB、workbook 和私有 corpus 单独管理 |

既有 M3/M4/M5 审计、S2P/RFM/AMI compare 和 source CI 继续作为迁移证据，但不等于 Rust-only 产品已经完成。

## 目标产品面

- `sipi` 单一公开 CLI，稳定 JSON schema、capabilities、errors 和 provenance。
- TRAN、Channel、IBIS、AMI、COM 独立 Rust crates。
- typed pipeline、内容寻址工件、stage compare 和 profile 级能力认证。
- MIT 第一方源码边界；compatible 依赖保留其许可证，供应商模型/DLL 默认外部提供。
- 面向 AI 的机器可发现接口，不提供隐式 fallback 或任意 shell 能力。

实施从 [PLAN.md](PLAN.md) 的 `P0` 产品/clean-room 边界开始。

## 许可边界

根 [LICENSE](LICENSE) 仅覆盖
[`product-boundary.v1.yaml`](product-boundary.v1.yaml) 中标为
`product_candidate`、`license: MIT` 的第一方文件。当前清单是
`provisional`：Python 迁移设施、旧引擎、候选 Rust crate、fixtures 和外部资产
不会因根许可证而被重新授权或纳入发行物。完整范围见
[LICENSE-SCOPE.md](LICENSE-SCOPE.md)。

## Clean-Room 门

[`clean-room-register.v1.yaml`](clean-room-register.v1.yaml) 是材料、角色和
attestation 的 fail-closed 声明门。它目前仅为 `provisional` 模板，不能证明
认知隔离、授权 release 或 promotion 任何现有 Rust candidate；完整流程见
[docs/clean-room/README.md](docs/clean-room/README.md)。

## 验证

```powershell
uv run python -B tools/sync_contracts_schemas.py  # schema 变更后同步打包副本
uv run python -B tools/run_all_tests.py           # 单元测试门禁
uv run python -B tools/run_all_tests.py --full    # 含外部探针的 M1 conformance
uv run python -B tools/clean_install_smoke.py     # M2-08：wheel 构建 + 隔离 venv 冒烟
```

仓库以 `schemas/` 为权威 schema 源，打包副本 `packages/sipi-contracts/src/sipi_contracts/_schemas` 不提交到 Git；修改任何 schema 后先运行同步脚本，否则 `sipi doctor` 会按缺失报告。
