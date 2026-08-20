# P5-04o Receiver Noise Stage — Audit

- slice: **P5-04o**（滤波器链 + eta_0/ACCM 噪声积分）
- date: 2026-08-16
- schema: `sipi.p5-04o.receiver-noise-stage.v1`

## 范围

从 MIT agent-com 源（`signal/filters.py`、`equalization/search.py`）移植：

| Python | Rust |
| --- | --- |
| `bessel_thomson_filter` | `bessel_thomson_filter_v1` |
| `butterworth_filter` | `butterworth_filter_v1` |
| `tukey_window` / `raised_cosine_filter` | `tukey_window_v1` / `raised_cosine_filter_v1` |
| `_rx_ffe_frequency_response` | `rx_ffe_frequency_response_v1` |
| `_receiver_noise` | `receiver_noise_v1` |

逐函数映射记录于 `docs/baselines/p5-04o-mit-source-map.v1.yaml`（5 项）。

## 语义要点（与源逐点对照）

- bessel：系数 `(2n−k)! / (2^(n−k)·k!·(n−k)!)`、复 polyval（Horner）、
  `c0 / polyval(coeffs[::-1], jf/(cutoff·baud))`；order<0/截止≤0/波特≤0 拒绝
- butterworth：四阶固定系数 `[1, 2.613126, 3.414214, 2.613126, 1]`
- tukey/RC：`f < start → 1`、transition `0.5·cos(2π(f−end)/period − π)+0.5`、
  `f > end → 0`；end ≤ start 拒绝
- **rxffe 频响**：offsets = `arange(size) − precursor_count`（非
  cursor-centered——初版用 cursor 形式被 crosscheck 1 ulp 级相位差捕获，
  修正为源形式；幅值平方积分等价但相位面需忠实）
- receiver_noise：h_r = BT×BW×RC、h_ctf（04n）、h_rxffe、eta0 =
  `sqrt(eta_0·Σ|h_sy·h_r·h_ctf·h_rxffe|²·Δf/1e9)`（**从 index 1 起**）；
  ACCM 分量 `sqrt(2·rms²·Σ|factor·|dc||²·Δf / f_last)`（searchsorted-right
  带界 `[1, end)`）；总噪声 = `‖(eta0, components)‖₂`

## 非声明

- `_crosstalk_noise` / `_td_source_crosstalk_noise`
- `_evaluate_candidate` / 搜索循环
- 非 profile acceptance、非 release evidence

## 验证

- sipi-com 累计 **104 测试绿**（本 stage 5 项：bessel 已知响应、BW/RC、
  rxffe 相量 DC、eta0 only、policy）
- crosscheck：`tools/run_p5_04o_receiver_noise_crosscheck.py`，oracle 外部
  custody `signal.filters` + `search._receiver_noise` vs 产品 runner，
  **9 用例全匹配**（bessel o3/o5/off 64 点复数、butterworth、RC、rxffe
  频响、eta0 only、eta0+RxFFE taps、ACCM 共模分量；容差 1e-9）
- 证据：`docs/baselines/p5-04o-receiver-noise-crosscheck-evidence.v1.yaml`

## 门禁绑定

- `tools/verify_p5_04o_receiver_noise.py`（charter/source-map/evidence/
  tokens/PLAN 行绑定）+ 6 项 verifier 测试
- ledger `P5-04` gate 列表 += verify_p5_04o；`total_open` 保持 31
- open-item gate coverage 108 → **109**

## 结论

P5-04o 语义达成：接收机噪声积分与 MIT 源 oracle 9 用例全一致（含
RxFFE 相位面实测修正）。P5-04 剩余：crosstalk noise、候选评估与
搜索循环。
