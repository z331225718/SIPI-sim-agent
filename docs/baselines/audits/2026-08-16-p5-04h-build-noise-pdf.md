# P5-04h r4.80 Noise-PDF Build Stage — Audit

- slice: **P5-04h**（build_r480_noise_pdf + erf 核心）
- date: 2026-08-16
- schema: `sipi.p5-04h.build-noise-pdf-stage.v1`

## 范围

从 MIT agent-com 源 `src/agent_com/noise/discrete_pdf.py` 移植非 MMSE
Create_Noise_PDF 高斯/双 Dirac 路径：

| Python | Rust |
| --- | --- |
| `build_r480_noise_pdf` | `build_r480_noise_pdf_v1` |
| `R480NoisePdf` | `R480NoisePdfV1` |
| `np.sqrt(2)*erfcinv(2*spec_ber)`（scipy） | `erfcinv_v1`（`erf_v1.rs`，自实现） |
| normal_pdf / sampled_signal_pdf / combine 复用 | 04d/04e/04f 已移植 stage |

逐函数映射记录于 `docs/baselines/p5-04h-mit-source-map.v1.yaml`（4 项）。

## 语义要点（与源逐点对照）

- controls：levels≥2、available>0、r_lm>0、tx_snr≥0、全部 sigma ≥0、
  override ≥0；h_j 非空
- sigma_tx = override 或 (levels-1)·available/r_lm·10^(-tx_snr/20)
- sigma_rj = override 或 sigma_rj_s·sigma_x·‖h_j‖
- sigma_gaussian = ‖(sigma_rj, sigma_n, sigma_tx)‖₂
- ber_q = noise_crest_factor 或 √2·erfcinv(2·spec_ber)；ne_q = bbn_q_factor
  或 ber_q
- gaussian = normal_pdf(σg, ber_q, bin) ⊗ normal_pdf(σne, ne_q, bin)；
  dual_dirac = sampled_signal_pdf(A_dd·h_j, levels, bin)；随后 Eq. 93A-45
  有序组合（04e）

## erfcinv 实现要点（自实现，无第三方代码）

- erf：|x|≤2 用 A&S 7.1 级数（自适应项数到 1e-18）；|x|>2 用 A&S 7.1.14
  连分式（40 项后向求值）
- erfinv：小参数用逆级数初始 + erf-Newton；**大参数用 erfc 侧 Newton**
  （避免 `1-erfc(x)` 灾难性抵消——实测 x~5 时 erf 面精度仅 ~5e-5，
  erfc 面达 ~1e-15）
- **erfcinv 直接对 erfc 迭代**（避免 `erfcinv(q)=erfinv(1-q)` 在 q~1e-12 的
  1-q 表示损失 2.2e-8——实测修正）
- 已知值验证：erf(1)=0.8427007929497149、erfinv(0.5)=0.4769362762044699、
  erfcinv(2e-4)=2.629741776210273、erfcinv(2e-12)=4.974131215017515（scipy）

## 非声明

- MMSE 路径（search_r480_mmse）
- 均衡搜索（search_r480_nonmmse_no_xtalk）
- conv_fct_TEST 快速 FFT 后端
- 非 profile acceptance、非 release evidence

## 验证

- sipi-com 累计 **62 测试绿**（本 stage 8 项：surface 构建、controls
  fail-closed、crest/override、policy + erf 已知值/逆/小 q/policy）
- crosscheck：`tools/run_p5_04h_noise_pdf_crosscheck.py`，oracle 外部
  custody `build_r480_noise_pdf` vs 产品 runner，4 用例
  （BER 1e-4 / 1e-5+NE / 1e-12+crest 3.9 / 3e-4+overrides+bbn-q）：
  - **ber_q 与 scipy 全一致**（3.71901649 / 4.26489079 / 3.9 / 3.4316144，
    差 <1e-11——端到端验证 erfcinv）
  - combined/gaussian/jitter PDF 逐点匹配（最长 **10039 bins**，容差
    1e-12 未放宽）；sigma 三值、peak_interference 一致
- 证据：`docs/baselines/p5-04h-noise-pdf-crosscheck-evidence.v1.yaml`

## 门禁绑定

- `tools/verify_p5_04h_build_noise_pdf.py`（charter/source-map/evidence/
  tokens/PLAN 行绑定，含 erf 模块双绑定）+ 6 项 verifier 测试
- ledger `P5-04` gate 列表 += verify_p5_04h；`total_open` 保持 31
- open-item gate coverage 101 → **102**
- 期间修复：lib.rs / discrete_pdf_v1.rs 两次 read-limit 截断重建（结构
  与 token 面经 03a/04d verifier 确认无回归）

## 结论

P5-04h 语义达成：非 MMSE 噪声 PDF 构建与 MIT 源 oracle 全表面一致
（含 ber_q 的 erfcinv 端到端验证）。该 stage 是均衡搜索（search.py）
的主要依赖；下一候选：search_r480_nonmmse_no_xtalk 切片评估。
