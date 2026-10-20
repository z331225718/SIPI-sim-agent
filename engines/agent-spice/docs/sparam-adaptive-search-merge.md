# 合并 IdEM-replica 自适应极点搜索（`fit-sparam --search-mode adaptive`）

日期：2026-10-20
范围：`engines/agent-spice`（S 参数 `fit-sparam` 系列）
状态：**opt-in 已交付**；默认 `native-idem-fast-v1` ladder 路径未改动

## 1. 结论

对照研究项目 `C:\Users\z3312\code\idem_research\idem_replica`（CST IdEM 的 clean-room 复刻引擎）之后的结论：

- **它不是整体更强的拟合器。** 在唯一有三方同输入实测的 30-port PDN 文件上，固定 order 78 的 raw RMS：我们 `9.863e-04`，它 `1.118e-03`（我们好 13.4%）；其无源性、报告、质量门、交付层均弱于我们。
- **它的“搜索架构 + 线性代数实现 + 轻量无源修正”明显更强。** 共享 sigma 的 Sanathanan–Koerner pole relocation（每轮一次共享 QR，而不是每个 response 一次）+ 累积式 Adding/Skimming order 搜索（每轮 1 次 SK 迭代，而不是每提高一阶从头拟合 5–14 次），恰好命中我们自己复盘认定的差距来源（`sparam-algorithm-research-retrospective.md`：对 IdEM 的 order 比 1.30/1.67/2.25、时间比 4.22/2.88/3.29）。
- 本次合并**只替换“极点发现 + 无源修正”这两层实现**；residue 求解、DC 处理、权威无源审计、质量门、JSON/HTML 报告、SPICE/RFM/Touchstone 交付层保持我们自己的实现。默认 ladder 路径不变，新能力通过 opt-in 开关启用。

## 2. 合并方式

```
fit-sparam --search-mode adaptive
        │
        ├── (vendored) _idem_sk：SK relocation + Adding/Skimming search
        │        └── 输出：rad/s 极点集（real + 每对复极点一个正虚部代表）
        │
        └── (native) fitting._fit_touchstone_execution
                 ├── residue LS（本模式不硬钉 DC，理由见 §3）
                 ├── passivity enforce：
                 │     ├── fast path  = (vendored) Hildreth-QP 残差扰动，margin=max(eps,1e-7)
                 │     ├── 失败 fallback = 完整 native dual-QP/spectral-projection enforcement
                 │     └── 权威 pre/post 审计 = native Hamiltonian（1+eps 契约）
                 ├── quality report
                 └── JSON/HTML report + .sp / .sNp / .rfm / wrapper
```

关键语义：

| 项 | 语义 |
|---|---|
| 目标 | `--rms-target` 仍是**绝对** mean S-RMS（IdEM/我方语义）；vendored 引擎内部的 `target_tol` 是相对值，由 `target_tol = target_mean_rms / rms(|S|_input)` 换算 |
| 通过判据 | 与 ladder 完全一致：post-enforcement `comparison_mean_rms_error <= target` **且** native 审计 `max_sigma <= 1 + --max-passivity-epsilon` |
| 失败重试 | 第 1 次按目标值搜极点；若“native 重解 + 无源修正后”未过契约，自动收紧搜索目标（×0.75、×0.55）重搜，最多 3 次 |
| 无源失败 fallback | 若 replica 快速修正后 native 审计仍不通过，自动对同一极点集重跑完整 native enforcement |
| DC | **不硬钉 DC 采样点**：vendored 极点族会产生较大的 direct term（s30 上 D≈1），而 native 的 DC 硬约束消元假设 D 很小（s30 上实测会把 8.2e-4 破坏成 1.2e-2）。本模式因此与 IdEM/replica search 一致地自由求解 residues，并在报告里给出 `adaptive_search.selected_model_dc_abs_error`；s30 order 82 实测 DC 误差 `1.19e-4`（约目标的 12%），s19 为 `2.2e-4` |
| native refine | 默认 `--adaptive-refine-iterations 0`：只做 residue solve，直接信任自适应极点；可显式加 1–2 轮我们自己的 relocation |
| 默认路径 | `--search-mode ladder`（默认）；不导入 vendored 引擎，不改变任何既有数值/测试 |

## 3. 使用

```powershell
# 30-port PDN，绝对目标 1e-3，enforce 无源性
python -m agent_spice.cli fit-sparam .\5power_30port_....s30p `
    --output .\runs\s30_adaptive.sp `
    --rms-target 0.001 --passivity enforce --max-order 100 `
    --search-mode adaptive --adaptive-order-step 8

# 19-port PDN（本模式可达 PASS，见 §4）
python -m agent_spice.cli fit-sparam .\5power_19port_....s19p `
    --output .\runs\s19_adaptive.sp --rms-target 0.001 `
    --passivity enforce --search-mode adaptive

# 小网络（2-port 等）也可以直接用
python -m agent_spice.cli fit-sparam .\channel.s2p --rms-target 0.001 `
    --passivity enforce --search-mode adaptive
```

自适应参数（`fit-sparam --help` 的 “Adaptive search” 组）：

| 参数 | 默认 | 说明 |
|---|---:|---|
| `--search-mode` | `ladder` | `ladder` = 原有冻结路径；`adaptive` = 本次合并 |
| `--adaptive-order-step` | 8 | 每轮 Adding 增加的极点（向上取偶，按共轭对插入） |
| `--adaptive-min-order` | 4 | 累积搜索的起始 order（与 ladder 的 `--min-order` 独立） |
| `--adaptive-target-margin` | 1.0 | 首次搜索目标占 `--rms-target` 的比例；失败后自动收紧 |
| `--adaptive-init-pole-damping` | 0.05 | 初始极点阻尼（上游在 30-port 语料上测得 0.05 优于 0.01） |
| `--adaptive-seed-probe` | on | 在抽稀网格上实测 `lin/auto/log` 三种初始极点并选用最好者 |
| `--adaptive-sk-weighting` | on | vendored SK relocation 的 `1/|sigma|` 重加权 |
| `--adaptive-refine-iterations` | 0 | 极点确定后再做几轮 native relocation |

限制（v1 明确拒绝，而不是静默降级）：

- 不支持 `--priority-band`（ladder 的频带加权搜索语义无法直接映射到累积搜索）；
- 只支持 S 参数（`parameter_type` 必须为 `s`）；
- 不支持 `gate_full_band_rms=False` 的“仅频带阻塞”契约。

## 4. 实测证据（同一台机器，8 线程，post-enforcement，margin 1e-6）

原始产物：`results/idem-merge-20261020/`（`merged/s30`、`merged/s19` 为本次合并模式；
`raw/caseA` 等为 `fit-benchmarker` 的两引擎对照）。

| 输入 | 引擎/模式 | order | abs RMS (post) | max sigma (post) | 时间 | 结论 |
|---|---|---:|---:|---:|---:|---|
| s30 (30p, 826pt) | 我方 ladder（冻结基线，本次重跑） | 80 | 9.4628e-04 | 0.99999999 | fit 51 s + check 82 s + enforce 735 s；整个搜索 wall 3543 s（含竞争；文档基线 1820 s） | 基线 |
| s30 | replica 端到端（AdaptiveFitter + 其 enforce） | 82 | 8.2368e-04 | 0.99999863 | 25.4 + 5.0 s | 参考上界 |
| s30 | **本次合并（adaptive + native 审计 + 快速 enforce）** | **82** | **8.236796e-04** | **0.99999863** | search 32.8 s + 执行 87.7 s（residue 0.04 + check 80.1 + enforce 6.1）≈ **2.0 min** | **PASS；比 ladder 精度好 13%、快 15–30×** |
| s19 (19p, 826pt) | 我方 ladder | — | 文档记录 FAIL（raw order 93 σ=1.021 非签核） | — | — | 基线 |
| s19 | **本次合并** | **75** | **9.870293e-04** | **0.99965280** | search 18.3 s + 执行 19.2 s ≈ **0.7 min** | **PASS；ladder 未过、本模式通过** |

方法论注意事项：

- ladder 的 3543 s 是在 `fit-benchmarker` 测量期间与本次合并模式运行重叠的**竞争态**墙钟；文档无竞争基线为 1820 s（order 83，RMS 9.184e-4）。两者都远慢于合并模式的 ~2 min。
- 合并模式的峰值 RSS：s30 993 MB（ladder 1314 MB），s19 456 MB。
- 本模式的“执行时间”里 80 s 是 native Hamiltonian 权威审计（30 端口，`check_vector_fit_passivity_hamiltonian`），与极点搜索无关；它是我们无源契约的成本，不是算法慢。
- replica 自身端到端数字里的 σ 是其自身 enforcement 的结果；本合并模式一律用 native 审计复核，任何不达标都会 fallback 到 native enforcement。
- DC 语义差异（不硬钉 DC）见 §2；s30/s19 实测 DC 误差分别 1.19e-4 / 2.2e-4。

## 5. 为什么是“vendored 极点发现/快速修正”而不是“重写搜索”

上游 `idem_replica/core/{rational_model,vector_fitting,adaptive,passivity}.py` 是 MIT 许可的 clean-room 实现，只依赖 numpy。本次以**逐字快照**方式放入
`engines/agent-spice/src/agent_spice/sparam/_idem_sk/`（见该目录 `VENDOR.md` 与 `LICENSE`），不做修改，以保证与上游实测行为一致、并把维护成本隔离在一个明确的第三方目录里。我们只在其上写了薄 adapter（`sparam/adaptive_search.py`）和交付/审计层适配（`fitting.fit_touchstone_to_spice_adaptive` + `passivity.enforce_passivity_hamiltonian(backend="idem-replica")`）。

`_idem_sk` 参与范围：opt-in 自适应模式的极点发现 + 快速无源修正。**默认路径不导入它**；权威无源审计始终是 native。

后续若要把该 backend 提升为默认路径：

1. 用我方代码重写共享 sigma relocation / Adding-Skimming search，并把 `_idem_sk` 从运行时依赖中移除；
2. 重跑完整六 case 语料与既有 parity gate；
3. 重新生成 `docs/sparam-idem-full-benchmark.md` 基线，并存档新的冻结数值测试；
4. 提交前重跑根目录 `tools/verify_product_boundary.py --write-inventory`（`product-boundary.v1.yaml` 是生成物），并同步 `license-manifest` 链。

在此之前：**默认路径不变、旧测试全绿、新路径独立测试**。

## 6. 测试与复现

```powershell
cd engines/agent-spice
$env:PYTHONPATH='src'
python -m pytest tests/test_sparam_adaptive_search.py -q
python -m pytest tests/test_sparam_fitting.py tests/test_sparam_native_vf.py `
    tests/test_sparam_target_fit.py tests/test_cli_fit_sparam.py `
    tests/test_sparam_pole_relocation.py tests/test_sparam_passivity.py -q
```

新增测试覆盖：配置校验；1-port 无源 RC 上的极点约定（real + 正虚部代表、stable）；
native↔replica 模型桥往返（响应 1e-12 内一致）；端到端契约（RMS + `max_sigma <= 1+epsilon`
+ SPICE/Touchstone/报告产物 + `passivity_backend=idem-replica` 记录）；
priority-band/目标不一致的拒绝；CLI 开关转发与默认 ladder 回归。

## 7. 与上游“建议”的差异（记录判断）

分析报告曾建议“不合并 replica 的 passivity 栈”。实测修正：**不合并其作为交付契约**，但把它作为**自适应模式内部的快速 enforcement 实现**，并用 native enforcement 做失败 fallback、用 native Hamiltonian 审计做唯一通过判据。理由：native enforcement 在 s30 pre-σ=1.0000000115（几乎已被动）的模型上仍耗时 734.6 s，而 replica 的 Hildreth-QP 只需 5–6 s；只换实现、不换契约，是这次合并最大的时间收益来源。其余不合并项保持不变：

- vendored Touchstone/SPICE/RFM/报告层：我方已与质量门、报告、RFM wrapper 集成；
- real-pole insertion（上游实验显示会把 passivity violation 从 2.7e-2 放大到 6.1e-2）；
- skimming 作为独立精度杠杆（上游历史显示 growth pass 上 0 次生效，仅 finalization 偶尔压缩极点）。
