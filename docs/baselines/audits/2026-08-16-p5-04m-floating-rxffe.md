# P5-04m Floating RxFFE Stage — Audit

- slice: **P5-04m**（floating RxFFE bank force）
- date: 2026-08-16
- schema: `sipi.p5-04m.floating-rxffe-stage.v1`

## 范围

从 MIT agent-com 源 `src/agent_com/equalization/rx_ffe.py` 移植 floating 分支：

| Python | Rust |
| --- | --- |
| `force_floating_rx_ffe` | `force_floating_rx_ffe_v1` |
| `_r480_rxffe_floating_locations` | `rxffe_floating_locations_v1`（私有） |
| `np.linalg.solve` | `lu_solve`（复用 04l） |
| `apply_rx_ffe` 复用 | `apply_rx_ffe_v1`（04l） |

逐函数映射记录于 `docs/baselines/p5-04m-mit-source-map.v1.yaml`（4 项）。

## 语义要点（与源逐点对照）

- controls：max_post > fixed_post、floating_start ≥ 1、tpb/bank ≥ 1 等
- 求解矩阵与 forcing 同 fixed；basis = raw（taps 选择）或 matrix[:, pc]（ISI）
- **RxFFE 版 findbankloc**：one-based 候选坐标（argsort+1）、stable 降序、
  bank==1 前缀有序特例、相邻 bank 启发式（bad/good/next_bank）、
  `bad_positions.min() < position` 的 one-based 位置比较
- **源缺陷如实复刻**：`energy[new_bank-1] = -inf` **无边界防护**（DFE 版有
  `candidate < energy.size` 防护，RxFFE 版没有）→ 候选起点靠后时源抛
  IndexError；产品以 `BankRange` 拒绝相同输入（**拒绝奇偶性**一致）
- 结果：retained（fixed 段 + floating 落位）、filtered、one-based locations

## 非声明

- 均衡搜索（search.py）
- 非 profile acceptance、非 release evidence

## 验证

- sipi-com 累计 **92 测试绿**（本 stage 3 项：locations 基本、floating force
  保留 fixed taps、controls fail-closed）
- crosscheck：`tools/run_p5_04m_floating_rxffe_crosscheck.py`，oracle 外部
  custody `force_floating_rx_ffe` vs 产品 runner，**3 用例全匹配**：
  taps 选择（拒绝奇偶性：源 IndexError ↔ 产品 BankRange）、ISI 选择
  +unity+tap_step（locations [2,3,4]，taps/filtered/matrix 容差内）、
  无 filtered（locations [6,4]）
- **期间修复**：Cargo.toml read-limit 截断导致 p5_04k/04l 的 `[[test]]`
  harness=false 声明丢失 → 陈旧 harness 版二进制被 crosscheck 选中
  （假拒绝/假 matrix drift）→ 清理全部陈旧二进制 + 补齐声明后
  04k/04l/04m crosscheck 全部重跑通过
- 证据：`docs/baselines/p5-04m-floating-rxffe-crosscheck-evidence.v1.yaml`

## 门禁绑定

- `tools/verify_p5_04m_floating_rxffe.py`（charter/source-map/evidence/
  tokens/PLAN 行绑定）+ 6 项 verifier 测试
- ledger `P5-04` gate 列表 += verify_p5_04m；`total_open` 保持 31
- open-item gate coverage 106 → **107**

## 结论

P5-04m 语义达成：floating RxFFE 与 MIT 源 oracle 全一致（含源越界缺陷的
拒绝奇偶性）。P5-04 剩余：均衡搜索（search.py）。
