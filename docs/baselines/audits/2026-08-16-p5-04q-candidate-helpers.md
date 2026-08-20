# P5-04q Candidate-Helper Stage — Audit

- slice: **P5-04q**（候选辅助：PDF bin size / BBN Q / FOM 上界拒绝 / 候选 BER Q / DFE bounds / jitter response / jitter sigma）
- date: 2026-08-16
- schema: `sipi.p5-04q.candidate-helpers-stage.v1`

## 范围

从 MIT agent-com 源 `src/agent_com/equalization/search.py` 移植：

| Python | Rust |
| --- | --- |
| `_r480_pdf_bin_size` | `r480_pdf_bin_size_v1` |
| `_r480_bbn_q_factor` | `r480_bbn_q_factor_v1` |
| `_cannot_improve_fom` | `cannot_improve_fom_v1` |
| `_candidate_ber_q` | `candidate_ber_q_v1` |
| `_dfe_candidate_bounds` | `dfe_candidate_bounds_v1` |
| `_jitter_response` | `jitter_response_v1` |
| `_jitter_sigma` | `jitter_sigma_v1` |

逐函数映射记录于 `docs/baselines/p5-04q-mit-source-map.v1.yaml`（7 项）。

## 语义要点（与源逐点对照）

- `_r480_pdf_bin_size`：非 force 时 `min(available_signal_v/1000, configured BinSize)`
- `_r480_bbn_q_factor`：force 时校验 finite & >= 0，否则 None；非法值 fail-closed
- `_cannot_improve_fom`：**严格上界拒绝** `20·log10(avail/sigma) < best`；best 为 None 或
  sigma<=0 时 False
- `_candidate_ber_q`：Noise_Crest_Factor 非零用之，否则 `√2·erfcinv(2·specBER)`
  （erfcinv 复用 P5-04h `erfcinv_v1`）
- `_dfe_candidate_bounds`：fixed `ndfe`/bmax/bmin；floating 用 P5-04k
  `find_dfe_bank_locations_v1`（start=fixed_count, end=N_bmax-1），
  `floating_max[loc-fixed_count]=bmaxg`，max=concat(fixed_max,floating_max)，
  min=concat(fixed_min,-floating_max)
- `_jitter_response`：Eq. 93A-28 采样 jitter；`limit_to_dfe_span` 用
  `ui_offsets=-1..=dfe_tap_count`（early=cursor-1+spu·off / late=cursor+1+spu·off，
  越界报 R480-JITTER-DFE-SPAN）；否则 sampling_offset=(cursor+1)%spu、<=1 +=spu、
  early_start=offset-2 可负补 spu；结果 `(late-early)·spu/2`；num_ui pad/truncate，<1 报错
- `_jitter_sigma`：`∥(A_DD,σ_RJ)∥·σ_X·∥h_J∥`
- 参数非法 / DFE span 越界 / num_ui<1 → fail-closed（`CandidateErrorV1`）

## 非声明

- `_evaluate_candidate` / `search_r480_nonmmse_no_xtalk` 搜索循环
- 非 profile acceptance、非 release evidence

## 验证

- sipi-com 累计 **115 测试绿**（本 stage 6 项：bin size & BBN、can-not-improve、
  ber_q、dfe bounds fixed/floating、jitter response & sigma、policy）
- crosscheck：`tools/run_p5_04q_candidate_helpers_crosscheck.py`，oracle 外部
  custody `search._r480_pdf_bin_size` / `_r480_bbn_q_factor` / `_cannot_improve_fom` /
  `_candidate_ber_q` / `_dfe_candidate_bounds` / `_jitter_response` / `_jitter_sigma`
  vs 产品 runner，**16 用例全匹配**（pdf force/no_force、bbn force/off、cannot_improve
  4 分支、ber_q crest/erfcinv、dfe fixed/floating、jitter unlimited/limited/num_ui_pad、
  jitter_sigma；容差 1e-9）
- 证据：`docs/baselines/p5-04q-candidate-helpers-crosscheck-evidence.v1.yaml`

## 门禁绑定

- `tools/verify_p5_04q_candidate_helpers.py`（charter/source-map/evidence/tokens/PLAN 行
  绑定）+ 6 项 verifier 测试
- ledger `P5-04` gate 列表 += verify_p5_04q；`total_open` 保持 31
- open-item gate coverage 110 → **111**

## 结论

P5-04q 语义达成：7 个候选辅助函数与 MIT 源 oracle 16 用例全一致。P5-04 剩余：
候选评估主体（`_evaluate_candidate`）与搜索循环
（`search_r480_nonmmse_no_xtalk`）。
