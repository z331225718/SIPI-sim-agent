# P0-A Provisional Product Boundary Audit

日期：2026-08-09
审计锚点：`2ffeff1` (`build: add provisional MIT product boundary`)

## 范围

- `LICENSE`、`LICENSE-SCOPE.md` 与 `README.md` 的根许可证边界。
- `product-boundary.v1.yaml` 的规则与展开 inventory。
- `tools/verify_product_boundary.py` 与 `tools/test_product_boundary.py`。
- `PLAN.md` 的 P0-A 状态。

## 本地核验

- `python -B tools/verify_product_boundary.py`：通过；804 个 tracked paths，7 个 `product_candidate`。
- `python -B tools/verify_product_boundary.py --release`：按设计拒绝，blocker 为 provisional manifest 不可授权 release。
- `python -B tools/test_product_boundary.py`：6/6 通过。
- `python -B tools/run_all_tests.py`：64/64 通过。

## 独立审计

审计请求：Orca OMP，消息 `msg_a0cd7043b81d`。
审计结论：Orca OMP，消息 `msg_e939541ed4b6`，0 P1 / 0 P2。

审计确认：

- 根 MIT 仅覆盖 manifest 中 `product_candidate` 且 `license: MIT` 的第一方文件；其余 tracked paths 仍按 migration、oracle 或 quarantine 边界隔离。
- 规则、展开 inventory 和 tracked-path SHA-256 互相校验；未分类、冲突、漂移或不安全路径 fail-closed。
- product candidate 强制 MIT、product distribution 与 project-authored/clean-room provenance。
- `status: provisional` 与 `--release` 的阻断不会将本仓误表述为 release-ready。
- 未改变数值算法、golden、旧引擎路径或默认路由。

## 非宣称

本切片不表示整仓已 MIT、Rust candidate 已 promotion、依赖许可已完成、产品可发布，亦不改变任何既有仿真能力声明。
