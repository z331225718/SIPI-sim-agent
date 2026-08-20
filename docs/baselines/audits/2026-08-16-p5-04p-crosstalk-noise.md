# P5-04p Crosstalk Noise Stage — Audit

- slice: **P5-04p**（FEXT/NEXT 功率积分 + TDMODE 外积路径）
- date: 2026-08-16
- schema: `sipi.p5-04p.crosstalk-noise-stage.v1`

## 范围

从 MIT agent-com 源 `src/agent_com/equalization/search.py` 移植：

| Python | Rust |
| --- | --- |
| `_crosstalk_noise` | `crosstalk_noise_v1` |
| `_td_source_crosstalk_noise` | `td_source_crosstalk_noise_v1` |
| `np.searchsorted(fb, right)` | `partition_point(<= fb)` |

逐函数映射记录于 `docs/baselines/p5-04p-mit-source-map.v1.yaml`（3 项）。

## 语义要点（与源逐点对照）

- FD 路径：channels 空 → 0；index_f2（fb 右侧带界）；TX-FFE 相量
  （argmax 首大光标、非零系数）；归一化 sinc（πf/fb）；frequency ≥ 11
  样本校验；RxFFE 成对校验；Δf = f[10]−f[9]；每 channel 形状校验；
  FEXT 权重 `|sinc²·tx_filter·h_rxffe|`、NEXT 权重 `|sinc²·h_rxffe|`；
  `2·Δf/f2·amp²·Σ` 累加；结果 `√(f+next)·σ_X`
- TD 路径（TDMODE）：count = first-above-fb+1（无 → 全长）；
  **外积** `response[:,None]·h_ctf[None,:]` 的 |·|² 按 role 累加；
  **末通道 amplitude 约定**（同 role 多通道时最后一次覆盖）；
  **列主序展平** `reshape(-1,'F')[:count]` 与 weight 逐元素乘
  （实现初版用 C 序索引，双 role 用例捕获 NEXT 矩阵 4 倍分量差并修正）
- role 非法 / 空响应 / rxffe TD 未认证 → fail-closed

## 非声明

- `_evaluate_candidate` / 搜索循环
- 非 profile acceptance、非 release evidence

## 验证

- sipi-com 累计 **109 测试绿**（本 stage 5 项：空通道、FD 积分、TD 外积、
  role/频率/rxffe 配对错误、policy）
- crosscheck：`tools/run_p5_04p_crosstalk_crosscheck.py`，oracle 外部
  custody `search._crosstalk_noise` / `_td_source_crosstalk_noise` vs
  产品 runner，**5 用例全匹配**（FD FEXT+NEXT、FD+RxFFE、NEXT only、
  TD 单 role、TD 双 role；容差 1e-9）
- 证据：`docs/baselines/p5-04p-crosstalk-crosscheck-evidence.v1.yaml`

## 门禁绑定

- `tools/verify_p5_04p_crosstalk_noise.py`（charter/source-map/evidence/
  tokens/PLAN 行绑定）+ 6 项 verifier 测试
- ledger `P5-04` gate 列表 += verify_p5_04p；`total_open` 保持 31
- open-item gate coverage 109 → **110**

## 结论

P5-04p 语义达成：串扰噪声积分（含 TDMODE 外积/列主序消费）与 MIT 源
oracle 5 用例全一致。P5-04 剩余：候选评估与搜索循环
（`_evaluate_candidate`/`search_r480_nonmmse_no_xtalk`）。
