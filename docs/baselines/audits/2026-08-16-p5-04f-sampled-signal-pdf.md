# P5-04f Sampled-Signal PDF Stage — Audit

- slice: **P5-04f**（sampled-signal discrete PDF stage）
- date: 2026-08-16
- schema: `sipi.p5-04f.sampled-signal-pdf-stage.v1`

## 范围

从 MIT agent-com 源 `src/agent_com/noise/discrete_pdf.py` 移植 sampled-signal
离散 PDF 路径：

| Python | Rust |
| --- | --- |
| `sampled_signal_pdf` | `sampled_signal_pdf_v1`（直接逐样本 PAM 卷积路径） |
| `DiscretePdf.from_values` / `d_cpdf` | `from_values_v1`（MATLAB half-away-from-zero 舍入、合并、支撑裁剪） |
| `_accelerated_sampled_signal_pdf` | `accelerated_sampled_signal_pdf_v1`（稀疏 PAM 加速，每步归一化） |
| `_sparse_pam_component` | `sparse_pam_component_v1`（PAM4 标量 ±1/3 浮点符号保持 + 通用 unique/count） |
| `_PAM4_SYMBOL_VALUES` | `PAM4_SYMBOL_VALUES`（IEEE f64 运算顺序保留） |

逐函数映射记录于 `docs/baselines/p5-04f-mit-source-map.v1.yaml`（5 项）。

## 非声明

- `residual_channel_pdf` 未移植（独立 stage）
- `fast_noise_convolution`/`conv_fct_TEST` FFT 后端未移植（API 面拒绝）
- search.py 通道选择 / 均衡搜索未移植
- 非 profile acceptance、非 release evidence

## 验证

- sipi-com 累计 **34 测试绿**（本 stage 8 项：direct/sparse PAM4 一致、
  levels 2/3 一致、全零→delta、过滤/置零、controls/空拒绝、from_values 合并
  与裁剪、policy 固定；delta 卷积恒等沿用 04d 文档化 1e-14 容差，无放宽）
- crosscheck：`tools/run_p5_04f_sampled_signal_crosscheck.py`，
  **12 用例**，oracle 为外部 custody 下直接 import 的
  `agent_com.noise.discrete_pdf.sampled_signal_pdf`（numpy 2.4.6 / scipy 1.18.0），
  产品侧为 `p5_04f_sampled_signal_runner`（harness=false）：
  - PAM4/PAM2 direct+sparse、过滤/置零、全零、小样本、负最大（验证
    `np.max` 非 abs-max 语义）、半 bin 边界 → **位级一致 diff=0.0**
  - PAM3 direct/sparse → 1.04e-17 归一化 re-entry 漂移（容差 1e-12，
    未因比较通过而放宽）
- 证据：`docs/baselines/p5-04f-sampled-signal-crosscheck-evidence.v1.yaml`
  （hash-only：samples/oracle/product sha256 + max_abs_diff）

## 门禁绑定

- `tools/verify_p5_04f_sampled_signal_pdf.py`（charter/source-map/evidence/
  tokens/PLAN 行绑定）+ 6 项 verifier 测试
- ledger `P5-04` gate 列表 += verify_p5_04f；`total_open` 保持 31
- open-item gate coverage 95 → **96**（BAD=0，sweep TOTAL=75）
- session health 6/6；plan reference audit 161 links / 0 missing

## 结论

P5-04f 语义达成：产品 sampled-signal PDF 与 MIT 源 oracle 在 12 用例上一致
（PAM3 仅 1e-17 级归一化漂移）。剩余 P5-04 范围：residual_channel_pdf、
channel selection、equalizer search。
