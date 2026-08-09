# P0-D Acceptance Candidate Inventory Audit

日期：2026-08-09
审计锚点：`6d6d820` (`build: add candidate acceptance profile inventory`)

## 本地核验

- `python -B tools/test_acceptance_profiles.py`：4/4 通过。
- `python -B tools/verify_acceptance_profiles.py --source-root ...`：4 个外部 Git object 通过 commit/blob/SHA-256 复核。
- `python -B tools/verify_product_boundary.py`：818 个 tracked paths 通过。

## 独立审计

审计请求：Orca OMP，消息 `msg_f89598230214`。
审计结论：Orca OMP，消息 `msg_94fb74500160`，0 P1 / 0 P2。

## 结论与非宣称

inventory 固定了 S2P、RFM、`example_rx` ABI 和 COM R480 四个 Windows oracle-only candidate 的 Git-object 身份与现有证据引用。所有 profile 保持 `candidate`，`required_profile_count` 为零；资产只作外部引用，未复制、运行或重录 golden。该清单不是数值 parity、用户需求确认或 release 认证。
