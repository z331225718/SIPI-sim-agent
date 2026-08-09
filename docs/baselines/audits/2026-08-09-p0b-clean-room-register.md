# P0-B Clean-Room Register Audit

日期：2026-08-09
审计锚点：`70f37bc` (`build: add clean-room material registry`)

## 范围

- `clean-room-register.v1.yaml` 与 `docs/clean-room/**`。
- `tools/verify_clean_room_register.py` 与 `tools/test_clean_room_register.py`。
- P0 状态、README 与 product boundary inventory 同步。

## 本地核验

- `python -B tools/verify_clean_room_register.py`：通过；1 个 planned scope、1 个自有模板材料、0 个 attestation。
- `python -B tools/verify_clean_room_register.py --release`：按设计拒绝。
- `python -B tools/test_clean_room_register.py`：7/7 通过。
- `python -B tools/verify_product_boundary.py`：810 个 tracked paths 通过。
- `python -B tools/run_all_tests.py`：65/65 通过。

## 独立审计

审计请求：Orca OMP，消息 `msg_f1bf948d64fb`。
审计结论：Orca OMP，消息 `msg_0c7c6893788e`，0 P1 / 0 P2。

审计确认：

- register 只是一份声明与证据边界，不被表述为个人或模型未曾接触源码的证明。
- 未知字段、不安全路径、本地 independent spec 哈希漂移、无效 provenance、allowlist 外材料、禁止祖先、阶段缺失、strict 签名缺失与角色重叠均 fail-closed。
- strict mode 使用独立 observer/implementer principal，并按状态要求对应 attestation 与材料闭包哈希。
- `--release` 仍被 v1 强制拒绝；`native/**` 保持 quarantine。
- 新增模板不含旧源码、fixture、golden、DLL 或供应商数据。

## 非宣称

本切片不指定真实人员或签名信任根，不将任何领域 scope 提升为 strict/release-eligible，也不构成法律意见、release 授权、native promotion 或数值能力认证。
