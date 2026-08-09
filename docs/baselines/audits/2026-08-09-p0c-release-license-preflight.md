# P0-C Release-License Preflight Audit

日期：2026-08-09
审计锚点：`8e82e4c` (`build: add release license preflight`)

## 本地核验

- `python -B tools/verify_release_license_preflight.py`：通过，`release_ready: false`。
- `python -B tools/verify_release_license_preflight.py --release`：按设计拒绝。
- `python -B tools/test_release_license_preflight.py`：5/5 通过。
- `python -B tools/verify_product_boundary.py`：814 个 tracked paths 通过。

## 独立审计

审计请求：Orca OMP，消息 `msg_340ac10beee3`。
审计结论：Orca OMP，消息 `msg_7c01d772cf5a`，0 P1 / 0 P2。

审计确认：

- v1 legacy records 只能作为 migration/oracle evidence，不能作为 v2 release dependency。
- boundary SHA、schema、引用安全性、依赖-NOTICE 一对一决策、owner action、artifact/SBOM 字段和 pending 状态均 fail-closed。
- `release_ready` 需要 strict/final/approval/resolved snapshot 等完整输入；`--release` 对该 preflight 仍拒绝。
- 当前没有已 promotion 的 Rust 运行依赖，故清单只作 preflight，不作法律或发行声明。

## 非宣称

本切片不改变 v1 的资产状态，不批准任何依赖、NOTICE、SBOM、native candidate、fixture、DLL 或模型，也不代表 release-ready。
