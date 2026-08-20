# P5-04g Residual-Channel PDF Stage — Audit

- slice: **P5-04g**（residual-channel discrete PDF stage）
- date: 2026-08-16
- schema: `sipi.p5-04g.residual-channel-pdf-stage.v1`

## 范围

从 MIT agent-com 源 `src/agent_com/noise/discrete_pdf.py` 移植 residual-channel
离散 PDF 路径：

| Python | Rust |
| --- | --- |
| `residual_channel_pdf` | `residual_channel_pdf_v1`（THRU DFE 消除、phase 采样与选择） |
| `_dfe_bounds` | `dfe_bounds_v1`（私有；负 count 在 API 面拒绝） |
| `ResidualPdfResult` | `ResidualPdfResultV1`（pdf / residual_pulse / selected_phase） |
| `sqrt(sum(x²·prob))` + `np.argmax` | `pdf_rms_v1` + 首个最大选择 |

逐函数映射记录于 `docs/baselines/p5-04g-mit-source-map.v1.yaml`（4 项）。

## 语义要点（与源逐点对照）

- controls：kind ∈ {THRU, FEXT, NEXT}、spu ≥ 1、levels ≥ 2、bin > 0；THRU 光标越界或 dfe_step < 0 → 拒绝
- THRU DFE：cancellation_count = dfe_max_count（floating）或 dfe_tap_count（含负值拒绝）；
  DFE-SPAN / DFE-WINDOW / 边界缺失或越界（lower > upper）逐项 fail-closed；
  dfe_step 量化保持 IEEE 除法语义（cursor·step == 0 时与 NumPy 相同）；
  bounds clamp 与 `np.repeat` 回减逐元素复刻
- 整 UI 支撑：nui = matlab_round(len/spu)，nui < 3 或 (nui-2)·spu+spu > len → PULSE-SHORT
- phase：THRU 单相 `((cursor+1) % spu or spu) - 1`；FEXT/NEXT 全相候选；
  未指定 phase 时选最大 PDF-RMS 相（tie 取首个）；`phase_index` 越出候选 → 拒绝

## 非声明

- `build_r480_noise_pdf` 未移植（独立 stage）
- MMSE 串扰相位供应路径未移植（`phase_index` 值语义已支持）
- search.py 通道选择 / 均衡搜索未移植
- 非 profile acceptance、非 release evidence

## 验证

- sipi-com 累计 **41 测试绿**（本 stage 8 项：THRU 无 DFE 光标消除与 phase 6、
  DFE 量化+clamp、FEXT 确定性选择、强制相位、floating DFE、10 类错误路径、
  policy；另含 DFE-WINDOW 与 PULSE-SHORT 区分语义，均与源一致）
- crosscheck：`tools/run_p5_04g_residual_pdf_crosscheck.py`，**10 用例**，
  oracle 为外部 custody 下直接 import 的
  `agent_com.noise.discrete_pdf.residual_channel_pdf`（numpy 2.4.6 / scipy 1.18.0），
  产品侧为 `p5_04g_residual_pdf_runner`（harness=false）：
  无 DFE / 带 DFE / step 量化 / floating DFE / THRU phase 6·7 / FEXT·NEXT
  相选择 / 强制相位 3·6 / spu 16 → **10/10 匹配，max diff 2.78e-17**
  （sampled PDF 归一化 re-entry 已知漂移，容差 1e-12 未放宽）
- 证据：`docs/baselines/p5-04g-residual-pdf-crosscheck-evidence.v1.yaml`
  （hash-only：pulse/oracle/product sha256 + max_abs_diff + selected_phase）

## 门禁绑定

- `tools/verify_p5_04g_residual_channel_pdf.py`（charter/source-map/evidence/
  tokens/PLAN 行绑定）+ 6 项 verifier 测试
- ledger `P5-04` gate 列表 += verify_p5_04g；`total_open` 保持 31
- open-item gate coverage 96 → **97**

## 结论

P5-04g 语义达成：产品 residual-channel PDF 与 MIT 源 oracle 在 10 用例上
一致（含 DFE 量化/浮动/相位选择），漂移仅 1e-17 级。剩余 P5-04 范围：
channel selection、equalizer search（search.py）。
