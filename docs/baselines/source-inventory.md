# M0-A Source Inventory

采集时间：2026-08-05。范围仅为只读 Git、锁文件和工具链检查；未运行测试、未复制任何源仓源码到本仓。

| Source | HEAD / tree | Branch | Worktree | Lockfiles |
| --- | --- | --- | --- | --- |
| `agent-spice` | `90f0374` / `b5db1cb` | `main` / `origin/main` | 6 tracked modified，44 untracked | `native/agent-spice-sim/Cargo.lock` |
| `py-bert-agent` | `5bf6d7e` / `5faef6b` | `master` / `origin/master` | 19 tracked modified，2 untracked | `uv.lock`、requirements、2 Cargo locks、PyAMI locks |
| `agent-com` | `034b21b` / `dc6e552` | `main` / `origin/main` | clean | `uv.lock` |

完整的 machine-readable evidence 位于 `source-snapshot.v1.json`。它包括 lock/build-input hash、脱敏后的 remote identity hash 和本地缓存的 upstream OID/ahead-behind；本轮未 fetch，remote 状态不是实时远端事实。PyBERT 比本地缓存的 `origin/master` ahead 2 commits。

## 已保护的 Dirty State

M0-02 的非破坏性备份位于目标仓之外：`C:\Users\z3312\code\SIPI-m0-backups\20260804T225059608Z`。

- manifest SHA-256：`D5AC6A9590CC66679F02CE7FC726B8B37E8F80D55F8B409D7853CB4106050E44`
- restore rehearsal SHA-256：`42A58FEE07E69253607F1B4727FD8F981FDEAFE1E5437EABFFB44CAB981624E7`
- 三个仓都在独立 clone 中恢复并匹配 capture 时的 NUL-delimited porcelain-v2 status digest。

`dirty-disposition.v1.yaml` 只记录事实与备份证据。所有 disposition 仍为 `pending`，因此 M0-02 的所有权决策尚未关闭，任何 dirty path 都不得作为迁入来源。

## Toolchain Observation

当前默认解释器为 Python `3.14.5`；`uv` 已安装 CPython `3.12.13`。Node/npm 为 `24.16.0` / `12.0.1`；Git 为 `2.54.0.windows.1`；`rustc` 和 `cargo` 不在 `PATH`。这些是观察值，不构成 `toolchains.lock`，也不表示 M0-03 已完成。

## 下一步

本轮是保护性 checkpoint：M0-01 的完整 source inventory 和 M0-02 的 disposition owner 决策都保持 open。M0-03 起应在与原工作树隔离的 scratch clone 中恢复 Rust toolchain 并采集测试证据；M0-04 至 M0-11 保持未开始。
