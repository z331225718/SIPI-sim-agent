# P5-04s Candidate-Evaluation Stage — Audit

- slice: **P5-04s**（候选评估主体：`_evaluate_candidate` + `_c2m_candidate_fom`）
- date: 2026-08-16
- schema: `sipi.p5-04s.candidate-eval-stage.v1`

## 范围

从 MIT agent-com 源 `src/agent_com/equalization/search.py` 移植（10 项源映射见
`p5-04s-mit-source-map.v1.yaml`，多数为复用已移植 stage）：

| Python | Rust | 来源 |
| --- | --- | --- |
| `_evaluate_candidate` | `evaluate_candidate_v1` | 本 stage 主体 |
| `_c2m_candidate_fom` | `c2m_candidate_fom_v1` | 本 stage |
| `_cannot_improve_fom` | `cannot_improve_fom_v1` | 04q |
| `_dfe_candidate_bounds` | `dfe_candidate_bounds_v1` | 04q |
| `_jitter_sigma`/`_jitter_response` | `jitter_sigma_v1`/`jitter_response_v1` | 04q |
| `_candidate_ber_q` | `candidate_ber_q_v1` | 04q |
| `_r480_pdf_bin_size`/`_r480_bbn_q_factor` | `*_v1` | 04q |
| `_selected_sndr` | `selected_sndr_v1` | 04n |
| `clip_dfe`/`apply_tail_rss_bounds` | `*_v1` | 04k |
| `calculate_c2m_vertical_eye` | `calculate_c2m_vertical_eye_v1` | 04r |

## 语义要点（与源逐点对照）

- 候选进入校验：cursor 在 [spu, size) 且 >0；padding 到 `unbounded_ndfe` 所需支撑
- `available_signal = R_LM·cursor/(levels-1)`，<=0 拒绝
- sigma-ISI 乐观拒绝：precursors（UI 之前）+ far（unbounded 之后）；`_cannot_improve_fom`
  严格 `<`——等值 FOM 走有序 tie
- DFE bounds（`_dfe_candidate_bounds`）、dfe_values 量化 floor+sign、clip、
  tail-RSS 边界（N_tail_start 从 1 起，index-1）、excess 残差；sigma_isi 二次拒绝
- `sigma_j`(04q jitter_sigma)、`sndr`(04n)、sigma_tx（SNR_TXwC0 用 main_tap 归一）；
  total = ‖(σ_isi, σ_j, σ_xt, σ_n, σ_tx, σ_ne)‖；fom=20log10(avail/total)
- C2M 分支（T_O≠0 且 Min_VEO_Test≠0）：EH_1st 守卫 `2(avail-ber_q·total) ≤ MinVEO/1000-1e-3`
  拒绝；`_c2m_candidate_fom` 用 04r 垂直眼，收敛不足拒绝 (returns None)
- 严格 FOM 改进门 `fom > best`；`retain_non_improving` 仅作用于该最终门
  （早于它的 sigma-ISI 乐观拒绝与 retain 无关）
- `h_j`(04q) 返回；`NonMmseSearchResultV1` 记录候选坐标
- 非法 cursor/选值/DFE/C2M/PDF → fail-closed

## 非声明

- `search_r480_nonmmse_no_xtalk` 搜索循环
- 非 profile acceptance、非 release evidence

## 验证

- sipi-com 累计 **128 测试绿**（本 stage 7 项：policy、无效 cursor、C2M eye closed→None、
  C2M 开眼→Some、happy path、严格改进拒绝、retain 保留）
- crosscheck：`tools/run_p5_04s_candidate_eval_crosscheck.py`，oracle 外部 custody
  `search._evaluate_candidate`（search_progress=None，默认直卷积路径）vs 产品 runner，
  **4 用例全匹配**（plain_cursor、strict_improvement_reject、off_center_cursor、
  c2m_branch_open_eye；容差 5e-5 相对）
- 证据：`docs/baselines/p5-04s-candidate-eval-crosscheck-evidence.v1.yaml`

## 门禁绑定

- `tools/verify_p5_04s_candidate_eval.py`（charter/source-map/evidence/tokens/PLAN 行绑定）
  + 6 项 verifier 测试
- ledger `P5-04` gate 列表 += verify_p5_04s；`total_open` 保持 31
- open-item gate coverage 112 → **113**

## 结论

P5-04s 语义达成：候选评估主体与 MIT 源 oracle 4 用例全一致，C2M 分支贯通
P5-04r 垂直眼。P5-04 剩余：搜索循环（`search_r480_nonmmse_no_xtalk`，含
`_validate_supported_branch`/`_tx_grid_values`/`_peak_window`/`_shift_matrix`/
`_skip_local_search`/`_sweep_order`/`_r480_sample_offsets`/`_tap_numbers`/
`_anchored_cursor`）。