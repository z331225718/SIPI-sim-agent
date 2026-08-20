# P5-04n Equalizer-Search Support Stage — Audit

- slice: **P5-04n**（search.py 参数面/频响/候选辅助）
- date: 2026-08-16
- schema: `sipi.p5-04n.search-support-stage.v1`

## 范围

从 MIT agent-com 源 `src/agent_com/equalization/search.py` 移植 8 个辅助：

| Python | Rust |
| --- | --- |
| `_indexed_config_value` | `indexed_config_value_v1` |
| `_high_pass_candidates` | `high_pass_candidates_v1` |
| `_qualified_ctle_pair` | `qualified_ctle_pair_v1` |
| `_selected_sndr` / `_selected_accm_rms` | `selected_sndr_v1` / `selected_accm_rms_v1` |
| `_r480_system_noise_response` | `system_noise_response_v1` |
| `_ctle_frequency_response` | `ctle_frequency_response_v1` |
| `_apply_ctle_candidate` | `apply_ctle_candidate_v1` |

逐函数映射记录于 `docs/baselines/p5-04n-mit-source-map.v1.yaml`（7 项）。

## 语义要点（与源逐点对照）

- indexed：size==1 广播（忽略 index）；否则越界拒绝
- high_pass：非 CL120d → 单 (0, 0.0)；CL120d 空值拒绝
- qualified：GDC_MIN≠0 时 `dc_gain+high_pass > gdc_min` → 拒绝（**等值
  可接受**，`>` 非 `>=`）；G_Qual/G2_Qual 表按 g2qual **降序**（stable）、
  阈值窗口 `[threshold, upper)`（首行 +eps）、范围降序 `[low, high)`；
  形状 (g2qual.size, 2) 校验
- sndr/accm：WC_PORTZ → Tx_rd_sel；否则 pkg_len_select[case]−1；越界/负
  值/AC_CM_RMS 负值拒绝
- eta0 整形：USE_ETA0_PSD 时 `sinc(√2(f−1e9)/1e9)²`（归一化 sinc，x=0 → 1）
- ctle 频响：基础两极点/一零点传递 + CL120d（f_HP 增益整形）/CL120e
  （f_HP_Z/f_HP_P 零极点）复数级联
- apply_ctle_candidate：td_ctle 基础 + CL120d 级联（fz=fp1=f_HP、
  fp2=**1e100** 哨兵）/CL120e 级联（fp2=**1e99**、gain=0）

## 非声明

- `_receiver_noise`（bessel/butterworth/raised-cosine 链）
- `_crosstalk_noise` / `_td_source_crosstalk_noise`
- `_evaluate_candidate` / `_c2m_candidate_fom` / 搜索循环
- 非 profile acceptance、非 release evidence

## 验证

- sipi-com 累计 **99 测试绿**（本 stage 7 项：indexed、high_pass、
  qualified（含表外/天花板/形状拒绝）、sndr/accm、eta0、ctle 频域+时域、
  policy）
- crosscheck：`tools/run_p5_04n_search_support_crosscheck.py`，oracle 外部
  custody `agent_com.equalization.search` 私有辅助 vs 产品 runner，
  **19 用例全匹配**（indexed 2、high_pass 3、qualified 5、sndr 2、accm 1、
  eta0 2、ctle_fd 2、ctle_td 2；复数频响与 64 点时域级联容差 1e-9）
- 证据：`docs/baselines/p5-04n-search-support-crosscheck-evidence.v1.yaml`

## 门禁绑定

- `tools/verify_p5_04n_search_support.py`（charter/source-map/evidence/
  tokens/PLAN 行绑定）+ 6 项 verifier 测试
- ledger `P5-04` gate 列表 += verify_p5_04n；`total_open` 保持 31
- open-item gate coverage 107 → **108**

## 结论

P5-04n 语义达成：搜索支撑面与 MIT 源 oracle 19 用例全一致。
P5-04 剩余：receiver noise（滤波器链）、crosstalk noise、候选评估与
搜索循环（search.py `_evaluate_candidate`/`search_r480_nonmmse_no_xtalk`）。
