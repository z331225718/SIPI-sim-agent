# P5-04i Equalizer Front-End Stage — Audit

- slice: **P5-04i**（cursor sampling + CTLE）
- date: 2026-08-16
- schema: `sipi.p5-04i.equalizer-frontend-stage.v1`

## 范围

从 MIT agent-com 源（`equalization/cursor.py`、`equalization/ctle.py`）移植：

| Python | Rust |
| --- | --- |
| `cursor_sample_index` | `cursor_sample_index_v1` |
| `CursorSample` | `CursorSampleV1` |
| `fd_ctle`（FD_CTLE） | `fd_ctle_v1` |
| `td_ctle`（TD_CTLE）/ `scipy.signal.lfilter` | `td_ctle_v1` |

逐函数映射记录于 `docs/baselines/p5-04i-mit-source-map.v1.yaml`（4 项）。

## 语义要点（与源逐点对照）

- cursor：峰值窗 argmax（首个最大）、`sign(x - 0.01·max)` 差分上升沿、
  最后上升沿为零交叉、`2·spu+1` 采样点、MM/Mod-MM 度量（`dfe_first_max`）、
  argmin 首项、MM 跨度检查（`R480-CURSOR-MM-RANGE`）；无上升沿 →
  `no_zero_crossing`；峰值索引零基
- fd_ctle：`(10^(gain/20) + jf/fz) / ((1+jf/fp1)(1+jf/fp2))`，复数逐点
  （sipi-types Complex64 手动乘除）
- td_ctle：双线性系数（p1d/p2d/zd/kd 与原式运算顺序一致）、
  `b = -p2·kd·poly((zd,-1))`、`a = poly((p1d,p2d))`、**lfilter 差分
  方程精确顺序** `y[n] = b0·x[n]+b1·x[n-1]+b2·x[n-2]-a1·y[n-1]-a2·y[n-2]`
  （零初始条件）

## 非声明

- TX FFE 网格（tx_ffe.py）、DFE bank（dfe.py）、RX FFE（rx_ffe.py）
- 均衡搜索（search.py）
- 非 profile acceptance、非 release evidence

## 验证

- sipi-com 累计 **69 测试绿**（本 stage 7 项：MM/Mod-MM 确定性、
  无上升沿、controls fail-closed、fd_ctle DC/形状、td_ctle 有限性、policy）
- crosscheck：`tools/run_p5_04i_frontend_crosscheck.py`，oracle 外部
  custody `agent_com.equalization` 模块 vs 产品 runner：
  - cursor 3 用例（MM / Mod-MM+dfe_first_max / peak 范围）**全一致**
    （cursor_index/零交叉/峰值/无交叉标志）
  - fd_ctle 2 用例 × 16 点复数**全匹配**（容差 1e-12）
  - td_ctle 2 用例 × **256 点 lfilter 输出全匹配**（容差 1e-12——
    差分方程顺序与 scipy 位级一致）
- 证据：`docs/baselines/p5-04i-frontend-crosscheck-evidence.v1.yaml`
- 期间修复：lib.rs read-limit 截断（第 3 次）→ 完整重建（03a/04d verifier
  无回归）；equalizer 文件传输截断 → 追补尾部

## 门禁绑定

- `tools/verify_p5_04i_equalizer_frontend.py`（charter/source-map/evidence/
  tokens/PLAN 行绑定）+ 6 项 verifier 测试
- ledger `P5-04` gate 列表 += verify_p5_04i；`total_open` 保持 31
- open-item gate coverage 102 → **103**

## 结论

P5-04i 语义达成：cursor 采样与 CTLE（含 lfilter 差分方程）与 MIT 源 oracle
全一致。P5-04 剩余：TX FFE 网格 / DFE bank / RX FFE / 均衡搜索。
