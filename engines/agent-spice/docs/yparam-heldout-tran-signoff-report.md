# Y-parameter fit: held-out、enforcement 与 TRAN 签核报告

日期：2026-07-15  
结论：Y-fit 在独立频点上的 Z 域误差有改善，但本轮不能给出 enforcement 或 TRAN 通过签核。

## 范围和基准

本报告比较三条路径：

1. 原始采样 Touchstone；
2. S-fit 的 HSPICE RFM；
3. Y-fit 的 common-ground Norton/MNA SPICE 宏。

这里需要澄清术语。HSPICE 不能直接把多端口采样 `.sNp` 当作“直接卷积”元件使用；TRAN 的原始参考是 HSPICE `S` 元件读取 Touchstone 后进行的原生 IFFT 时域求解。因此它是本次可执行的 sampled-Touchstone transient reference，而不是另行实现并验证过的数学直接卷积 oracle。RFM 是有理模型格式，当前只支持 S 参数；Y-fit 不能物理正确地直接导出成 `MATRIX_TYPE Y` RFM，故第三条路径使用 Norton/MNA 宏，而不是伪造 Y RFM。

## 产物和可复现命令

完整运行目录为 `runs/yparam-tran-signoff/`。2-port 规约输入为 `vddq_port3_port10.s2p`，对应 VDDQ port 3 到 port 10；使用同一 CPM、0.8 V VRM、`method=gear`、`reltol=1e-5`、`10 ps` 输出步长、`14 ns` 停止时间。

S-fit：

```powershell
python -m agent_spice.cli fit-sparam runs/hspice-native-fit-comparison/vddq_port3_port10.s2p `
  --output runs/yparam-tran-signoff/sfit.sp `
  --fitted-touchstone runs/yparam-tran-signoff/sfit.s2p `
  --rfm runs/yparam-tran-signoff/sfit.rfm `
  --report runs/yparam-tran-signoff/sfit.json `
  --rms-target 0.005 --passivity enforce --max-order 60 --subckt-name sfit_model
```

Y-fit：

```powershell
python -m agent_spice.cli fit-yparam runs/hspice-native-fit-comparison/vddq_port3_port10.s2p `
  --output runs/yparam-tran-signoff/yfit.sp `
  --report runs/yparam-tran-signoff/yfit.json `
  --n-poles-real 0 --n-poles-cmplx 30 --fit-iterations 20 `
  --passivity check --subckt-name yfit_model
```

HSPICE 使用 PrimeSim HSPICE `T-2022.06-1 win64`，许可证为 `27000@zzm-minicenter`。执行过的网表是 `sfit_vs_raw_tran.sp` 和 `three_way_tran.sp`，测量窗口均为 CPM presimulation 后的 `3.5 ns` 至 `14 ns`。

## Held-out 频点结果

S19 用每 5 个频点留出 1 个（从索引 1 开始），总共 826 个频点，其中 165 个未参与拟合。比较指标是从拟合的 S/Y 换算得到的 Z 的逐元素对数 RMS；数值越低越好。

| 数据集 | S-fit held-out Z-log RMS | Y-fit held-out Z-log RMS | Y-fit 改善 |
| --- | ---: | ---: | ---: |
| S19 | 1.45682 | 1.20810 | 17.1% |

这说明“先拟合 Y、再以 Z 指标评估”的方向对未见频点是有价值的；并不等价于已经获得可用于 transient 的稳定、被动有理模型。完整的固定预算 S19/S30 对比见 `docs/yparam-s19-s30-benchmark.md`。

## Enforcement 结果

S-fit 请求了 `--passivity enforce`，但目标 RMS `0.005` 未达到：有效阶数 60 时 S 参数平均 RMS 为 `0.00602983`。实现按策略跳过 enforcement（`pre_rms_above_target`），所以 `passive_after_enforce` 和 after-passivity 指标均为 unknown。该 RFM 可用于比较，但不得标为“已 enforcement”。

Y-fit 的采样 positive-real 检查通过：最小 Hermitian 特征值为 `0.4274696 S`（2 GHz），违规数为 0；但当前实现只有 `off/check`，报告明确记录 `enforcement: not implemented`。采样点 PR 检查也不能证明连续频带上的正实性。因此，Y-fit 同样不得标为“已 enforcement”。

## HSPICE TRAN 结果

S-fit RFM 与原始 sampled-Touchstone 在同一 HSPICE 网表中完成至 14 ns：

| 测量（3.5-14 ns） | 结果 |
| --- | ---: |
| 原始 Touchstone `V(cpm_raw)` 最小值 | 0.6969 V |
| S-RFM `V(cpm_sfit)` 最小值 | 0.6975 V |
| S-RFM 对原始参考 RMS 差 | 0.0006793 V |
| S-RFM 对原始参考峰值差 | 0.001294 V |

对应证据为 `runs/yparam-tran-signoff/sfit_vs_raw_tran.mt0` 和 `.lis`。该项仅说明此 2-port CPM 激励下 S-RFM 与 HSPICE 原始参考接近，不替代被动性签核。

Y-fit Norton/MNA 宏没有通过 TRAN：三路网表在约 `4.2 ns` 中止，未生成 `.mt0`，也没有 `hspice job concluded`。将 `RESMIN` 从默认值降低到 `1e-20` 后仍复现。日志同时记录宏中大量极小电阻和巨大伴随电容；HSPICE 对这些元件进行了恢复/限制，说明当前非缩放的直接电路实现数值刚性很强。故无法给出 Y-fit 对原始参考的完整 3.5-14 ns RMS，也不能将其视为 transient 合格。

## 最终判定

- Held-out：**Y-fit 改善 17.1%，通过研究性比较。**
- S-fit enforcement：**未通过/未完成。** enforcement 因拟合精度门限未满足而跳过。
- Y-fit enforcement：**未实现，未通过。** 仅完成采样 PR 检查。
- S-fit TRAN：**完成比较，但不是完整 signoff。**
- Y-fit TRAN：**失败。** 当前宏在标准 14 ns CPM 场景无法完成。

因此本功能的研究性目标已经验证：Y-fit 对 held-out Z 指标有提升；生产签核目标尚未完成，不能把本轮结果宣称为 “enforced” 或 “TRAN signed off”。

## Y-derived S enforcement 试跑

按后续确定的交付路线，已在同一 2-port 上执行 `Y fit -> 严格 LFT 采样 S -> S refit + --passivity enforce`。中间 S 与最终 S-RFM 的平均 RMS 为 `0.0070106`，S-RFM 相对原始 S 的平均 RMS 为 `0.252786`，而 Y-derived S 相对原始 S 为 `0.252912`。因此 enforcement/refit 没有显著恶化转换后的原始 S 误差（变化 `-0.000126`），但两者相对原始 S 都过大，绝不能以“前后接近”取代绝对质量门。

该试跑的 `passivity_max_sigma` 在 enforcement 前后均约 `0.995113`；它验证了 S-domain 路径可执行，而非证明 Y 已 enforcement。命令、字段定义与门槛见 `docs/yderived-s-enforcement-workflow.md`。

该 Y-derived S-RFM 也已完成 HSPICE 14 ns TRAN：相对原始 sampled-Touchstone reference 的波形 RMS 差为 `3.474 mV`，峰值差为 `5.169 mV`。它避开了 Y Norton/MNA 宏在 4.2 ns 的数值中止，但在这个 CPM 场景中仍明显劣于直接 S-fit RFM 的 `0.6793 mV` RMS；因此它是可运行的交付路径验证，不是质量签核通过。

## KYP-enforced exact Y-to-S RFM

现在新增的交付路径不再执行 `Y -> sampled S -> S refit`。对 2-port 规约使用 8 对复极点、proper Y（关闭 proportional 项）时，KYP SDP 给出连续频率 PR certificate：32 个状态、`P` 最小特征值 `3.999e-4`、KYP 最大特征值 `1.178e-8`、校正量为零。随后直接通过状态空间 LFT 生成 S 的新极点/残差；直接矩阵 LFT 与该有理 S 的最大误差 `4.65e-13`，RFM 回读 RMS `2.67e-13`。

HSPICE 14 ns CPM TRAN 也已完成：Y-KYP-exact-S-RFM 相对原始 sampled-Touchstone 的 RMS 差为 `4.326 mV`、峰值差为 `8.720 mV`。这证明 `Y-fit -> KYP Y PR -> exact rational Y-to-S -> S-RFM -> HSPICE` 已端到端可执行；该低阶模型的原始网络保真度仍不够，因此不是最终质量 signoff。

CLI 使用 `fit-yparam --no-fit-proportional --exact-s-rfm <model.rfm>`。它在 KYP 状态数超过 128、存在 proportional/descriptor 项、或所需 KYP 校正超过预算时硬失败，避免静默降级回采样 S refit。

## 直接 S 目标打磨与带外反例（2026-07-15）

随后在 Y 的固定极点/残差坐标中直接最小化 `S=(I-Z0Y)(I+Z0Y)^-1` 的采样误差。该实验说明转换本身并不是主要精度瓶颈：未约束的候选在输入频点上达到 S RMS `0.0047380`、Z-log RMS `0.0098635`，均优于直接 S-fit 的 `0.0060298` 和 `0.0570181`。

但该候选的 S 高频常数为非被动矩阵，虽然被有限采样频点的动态项抵消，HSPICE IFFT 所需的带外响应会显著失真。14 ns TRAN 的 RMS 差为 `26.0008 mV`、峰值为 `26.6743 mV`。将 Y 的常数项固定为正实值后，频点 S RMS 仍为 `0.0048252`，但 TRAN RMS 仍为 `25.7171 mV`。因此，单独改善输入频点 RMS 或 Z-log RMS 不能作为 transient 质量代理。

又以已验证 S-fit RFM 的 `1.47-36.57 GHz` 响应作为尾部锚点。低阶（160 阶 S）Y 基线无法同时满足两组约束，优化后输入频点 S RMS 退化为 `0.04075`；完整 S-fit 逆变换的 Y 基线则可保留输入/尾部精度，但 exact LFT 后为 240 阶 S-RFM，在本机 HSPICE Windows TRAN 接近结束时异常退出。这两项均不构成可交付候选。

这给出下一轮的硬门：Y 优化必须同时约束 HSPICE IFFT 频带的尾部，并在导出前限制 RFM 的有效阶数；随后才可谈 KYP PR enforcement。上述所有候选均未通过 KYP enforcement，不得作为 signed-off 模型。

## 受限压缩后的 TRAN 超越（研究候选，2026-07-15）

以直接 S 目标打磨得到的 Y 候选为源，将其 exact-LFT S 响应与 S-fit 的带外响应一起压缩为 60 阶 S-RFM；再以十个低频实极点校正 DC/低频残差。最终 RFM 有效阶数为 70。对低频残差的四组幅度仅做很小的 HSPICE 黑盒校正后，连续三次同一 HSPICE TRAN 的结果一致：RMS `0.3667 mV`、峰值 `0.6253 mV`。

这已经优于直接 S-fit RFM 的 RMS `0.6793 mV` 与峰值 `1.294 mV`。输入频点的 S RMS 为 `0.0046296`，Z-log RMS 为 `0.0416332`，输入频点最大奇异值为 `0.9951643`。产物为 `runs/yparam-tran-signoff/ybootstrap_blackbox.rfm`，重复网表输出为 `ybootstrap_best1.mt0` 至 `ybootstrap_best3.mt0`。

但它仍只是研究候选，不得称为最终 signoff：低频校正系数用完整频点和同一个 TRAN 场景调出，因而当前的 held-out 数值不是独立验证；更重要的是，扩展到 `36.57 GHz` 的最大奇异值为 `2.90`，没有连续频带的 S 被动性，也尚未取得 Y KYP PR certificate。下一步需要在真正留出频点、带外被动性与 KYP 三个硬约束下复现或超过该波形误差。

## 下一步

1. 为 Y 有理模型实现真正的连续频带正实 enforcement（例如 KYP/LMI 或等价有理 PR 判定与受约束校正），并将未完成 enforcement 作为硬失败而非 warning。
2. 先做 HSPICE AC 宏对解析 Y 的逐点回归，量化 `RESMIN` 前后的误差；随后重标度每个状态（固定目标电阻，再同步调整电容、输入 VCCS 与复极点交叉项），并让 exporter 拒绝会触发 `RESMIN` 的元件。通过 AC 后先用半程 TRAN 回归，再恢复至 14 ns。
3. S-fit 需在 RMS `<=0.005` 前提下真正完成 passivity 后检查，再重跑同一张 TRAN 网表。
4. 若需要“直接卷积”字面意义的黄金基准，应单独实现并验证 Touchstone IFFT/convolution 参考；在此之前，报告应明确使用 HSPICE 原生 sampled-Touchstone reference。

## 带限验收范围（用户确认，2026-07-15）

用户确认本轮不要求带外延拓。因此，`ybootstrap_blackbox.rfm` 的验收范围明确限制为原始 Touchstone 的 `0-2.0 GHz` 输入频带，以及已定义的 14 ns HSPICE CPM transient 场景；不再将 `2.0 GHz` 以外的响应纳入本轮通过条件。

在该范围内，候选的 Hamiltonian 被动性检查扩展至 `2.3 GHz` 仍未发现违规，最大奇异值为 `0.9951643`；输入频点 S RMS 为 `0.0046296`，优于直接 S-fit 的 `0.0060298`，Z-log RMS 为 `0.0416332`，优于直接 S-fit 的 `0.0570181`。三个独立重复的 HSPICE 运行均得到 `0.3667 mV` RMS 和 `0.6253 mV` 峰值误差，也优于 S-fit 的 `0.6793 mV` RMS 和 `1.294 mV` 峰值误差。

这是一项带限静态精度与指定 TRAN 场景的性能验收，不宣称全频带 S 被动性、带外 IFFT 保真度或最终低频黑盒校正的独立 held-out 成绩。此前 S19 的独立 held-out Y-fit 改善 `17.1%` 仍是该方向的泛化证据；最终候选若要升级为生产签核，仍需以冻结参数在独立 held-out 网络/激励上复跑。

## 带限残差细调（2026-07-15）

在不改动极点、常数项或带内门限的前提下，进一步将十个低频实极点的残差按三个频段（DC/慢、中、transient-facing）和三个互易 S 矩阵分组做局部搜索。搜索中的每个候选都要求输入频点 S RMS 不超过原候选的 `1.003` 倍，且采样最大奇异值小于 `0.999`；共评估 150 个 HSPICE 点。

最佳冻结候选为 `runs/yparam-tran-signoff/ybootstrap_band_tuned.rfm`。它的输入频点 S RMS 为 `0.0046296113`，Z-log RMS 为 `0.0416331855`，与原候选实质相同；Hamiltonian 检查至 `2.3 GHz` 无违规，最大奇异值为 `0.9951635`。同一 14 ns HSPICE 网表连续三次均得到 RMS `0.3337 mV`、峰值 `0.6148 mV`，相对原 `0.3367 mV`、`0.6253 mV` 分别再降约 `0.9%` 和 `1.7%`。

可复现的搜索入口是 `scripts/tune_ybootstrap_tran.py`，搜索记录在 `runs/yparam-tran-signoff/ybootstrap_band_tune/summary.json`；正式复跑网表为 `ybootstrap_band_tuned.sp`。该改进仍属于当前已声明的带限、同场景调参范围，不改变本报告此前关于独立 held-out 和生产签核的限制。

## CLI 化的显式 TRAN 细调（2026-07-15）

研究脚本现已收敛为 `agent-spice tune-yparam-tran`。该命令不把 CPM、电流激励或测量窗口写进 `fit-yparam` 默认行为；调用者必须提供签核网表、网表中待替换的输入 RFM 文件名、RMS/峰值 measure 名、允许调节的实极点以及频段边界。每个候选先经过输入 Touchstone 的 S RMS 和最大奇异值门限，再进入 HSPICE 目标函数。

当前 CPM 的完整调用如下：

```powershell
python -m agent_spice.cli tune-yparam-tran runs/yparam-tran-signoff/vddq_port3_port10.s2p `
  runs/yparam-tran-signoff/ybootstrap_blackbox.rfm `
  runs/yparam-tran-signoff/ybootstrap_blackbox.sp `
  --output-rfm runs/yparam-tran-signoff/ybootstrap_cli_tuned.rfm `
  --rfm-token ybootstrap_blackbox.rfm `
  --rms-measure yfit_vs_raw_rms --peak-measure yfit_vs_raw_peak `
  --residual-poles 0.0628318530718,0.8115045878714,10.48098478623,135.3671238969,1748.33363523,22580.59720916,291639.6276132,3766670.63349,48648421.94905,628318530.718 `
  --band-boundaries 22580.59720916,3766670.63349 `
  --hspice-bin C:/synopsys/Hspice_T-2022.06-1/WIN64/hspice.exe `
  --license-file 27000@zzm-minicenter --max-evaluations 150
```

该命令复现了冻结的 `ybootstrap_cli_tuned.rfm`：搜索最佳 RMS `0.33366 mV`，正式网表 `ybootstrap_cli_tuned.sp` 连续三次复跑均为 `0.3337 mV` RMS、`0.6148 mV` 峰值。它是显式场景优化命令，而非仅凭 Touchstone 的通用生产签核。
