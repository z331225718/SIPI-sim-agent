# P5-04t Search-Loop Support Stage — Audit

- slice: **P5-04t**（search-loop 支撑辅助：validate / tx-grid / peak-window / shift-matrix / local-search skip / sweep-order / sample-offsets / anchored-cursor / rect-pulse）
- date: 2026-08-16
- schema: `sipi.p5-04t.search-loop-stage.v1`

## 范围

从 MIT agent-com 源 `equalization/search.py` + `signal/fd_to_td.py` 移植（11 项源映射
见 `p5-04t-mit-source-map.v1.yaml`）：

| Python | Rust |
| --- | --- |
| `rectangular_pulse_response` | `rectangular_pulse_response_v1` |
| `_peak_window` | `peak_window` |
| `_shift_matrix` | `shift_matrix` |
| `_skip_local_search` | `skip_local_search` |
| `_skip_high_pass_local_search` | `skip_high_pass_local_search` |
| `_sweep_order` | `sweep_order` |
| `_r480_sample_offsets` | `r480_sample_offsets` |
| `_tap_numbers` | `tap_number_from_name` |
| `_anchored_cursor` | `anchored_cursor` |
| `_validate_supported_branch` | `validate_supported_branch` |
| `_tx_grid_values` | `tx_grid_values` |

## 语义要点（与源逐点对照）

- `rectangular_pulse_response`：`filter(ones(spu),1)` 零状态 → 滑动窗口和（已修正为
  前向累积，非逐段重卷积）
- `_peak_window`：TDMODE pulse（is_pulse=true 直接用）vs FD impulse（先 rect-pulse）
  argmax ± 20·spu 窗口（实测量测 stop=peak+20·spu+1 修正）
- `_shift_matrix`：`np.roll(pulse, (k-precursor)·spu)` 列堆叠（roll 左/右方向实测对齐）
- `_skip_local_search`：`_sweep_order` 索引顺序下 `previous>1 && |current-best|>limit` 守卫；
  产品把 sweep 作为显式参数（oracle 从参数内部推导）——crosscheck 通过对齐同一 sweep 验证
- `_sweep_order`：cm 降序 + cp 升序 ordered_names，variable(>1 size) 按 size 降序稳定排序
- `_r480_sample_offsets`：单值→[0,v]，含端点；TS_SRCH_MODE full-sweep/middle 稳定abs 排序
- `_anchored_cursor`：ts_anchor 0/1/2（max-DV 窗口越界报 R480-SEARCH-ANCHOR）
- `_validate_supported_branch`：FV-LMS/MMSE 标签且无 RxFFe 分支（实测 oracle 对合法标签接受）

## 非声明

- `search_r480_nonmmse_no_xtalk` 复合搜索循环（依赖本 stage 辅助 + 04s candidate_eval）
- 非 profile acceptance、非 release evidence

## 验证

- sipi-com 累计 **136 测试绿**（本 stage 8 项：policy、rect-pulse、peak-window、shift、
  skip-local、sample-offsets、anchored、validate）
- crosscheck：`tools/run_p5_04t_search_loop_crosscheck.py`，oracle 外部 custody 各辅助函数 vs
  产品 runner，**20 用例全匹配**（rect spu1/3、peak fd/pulse、shift pc1/2、offsets 4 变体、
  skip-local 3、skip-hp 3、anchored 3、validate 2；容差 1e-9）
- 证据：`docs/baselines/p5-04t-search-loop-crosscheck-evidence.v1.yaml`

## 门禁绑定

- `tools/verify_p5_04t_search_loop.py`（charter/source-map/evidence/tokens/PLAN 行绑定）
  + 6 项 verifier 测试
- ledger `P5-04` gate 列表 += verify_p5_04t；`total_open` 保持 31
- open-item gate coverage 113 → **114**

## 结论
P5-04t 之后，复合搜索循环 `search_r480_nonmmse_no_xtalk_v1` 已实现并 oracle 验证：
在因果阶跃信道场景（fom oracle 53.42661625274711 / cursor 56）位级一致（容差 1e-9），
修复了 `sbr = shifted @ taps` 的矩阵-向量方向 bug（shift_matrix 返回 [tap][sample] 定向，
复合需按 [sample][tap] 索引）。P5-04 子分片 04a-04t 全部完成且各自 crosscheck / oracle 验证。
