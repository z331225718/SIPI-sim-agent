# Y 参数拟合、RFM 交付与 Z-log 门禁使用说明

## 适用范围

`fit-yparam` 从标准 Touchstone `.sNp` 读取 S 参数及参考阻抗，转换为 Y 参数后执行共享极点有理拟合。它适合以阻抗质量为主要判据的 PDN/SIPI 场景。

这条路径不改变 `fit-sparam` 的任何默认行为。Y-domain SPICE、精确 Y-to-S RFM 与针对某个 HSPICE 场景的 TRAN 残差细调是三个独立层次：不要把它们混为同一份“天然可签核”的模型。

## 快速开始

最小 Y-domain 拟合：

```powershell
python -m agent_spice.cli fit-yparam .\board.s19p `
  --output .\deliverables\board.y.sp `
  --derived-s-touchstone .\deliverables\board.y-derived.s19p `
  --report .\deliverables\board.y.json `
  --html-report .\deliverables\board.y.html `
  --log .\deliverables\board.y.log
```

输入必须是标准 Touchstone `.sNp`。Y 拟合使用输入的参考阻抗；不要先把 S 参数手工改写为非标准 `.yNp` 文件。

`fit-yparam` 默认不是固定阶次单次拟合。初始有效阶次按 `n_poles_real + 2 * n_poles_cmplx` 计算；某阶没有同时满足 mean Y RMS 门限和 sampled Y 正实性门限时，命令按 `--order-step`（默认 `2`）提高到 `--max-order`（默认 `40`），第一个通过的阶次立即停止。指定 `--exact-s-rfm` 时，每个通过基础门限的候选还必须通过 KYP enforcement 和精确有理 Y-to-S 转换，失败后继续升阶。最大阶次仍不通过时，命令输出评分最佳的诊断模型并返回失败。每阶结果写入 JSON 的 `order_search.trials`，也会实时追加到 `.y.log`。

建议先为探索运行保留 `--passivity check`（默认），并显式设置极点预算和迭代次数，使结果可复现：

```powershell
python -m agent_spice.cli fit-yparam .\board.s19p `
  --output .\deliverables\board.y.sp `
  --derived-s-touchstone .\deliverables\board.y-derived.s19p `
  --n-poles-real 0 --n-poles-cmplx 10 `
  --max-order 40 --order-step 2 `
  --fit-iterations 6 --passivity check
```

## `fit-yparam` 产物

| 产物 | 生成条件 | 用途 |
| --- | --- | --- |
| `*.y.sp` | 默认 | Common-ground Norton/MNA Y-domain SPICE 子电路。 |
| `*.y.json` | 默认 | 机器可读报告，含 Y RMS、Z-log RMS、条件数与 sampled PR 检查。 |
| `*.y.html` | 默认 | 人工阅读报告。 |
| `*.y.log` | 默认 | 运行开始即创建，逐阶段、逐矢量拟合迭代追加并刷新；失败时保留已有进度和异常。 |
| `*.y-derived.sNp` | 指定 `--derived-s-touchstone` | 由有理 Y 在输入频率点严格换算得到的采样 S 参数。 |
| `*.rfm` | 指定 `--exact-s-rfm` | 经 KYP Y 正实性 enforcement 和精确有理 LFT 生成的 S-RFM。 |
| `*.sNp` | `--exact-s-rfm` 时自动或指定 `--exact-s-touchstone` | 与 exact RFM 对应的 S 参数审计文件。 |
| `*_wrapper.sp` | 指定 `--exact-s-rfm-wrapper` | 引用 exact RFM 的 HSPICE/Sigrity wrapper。 |

未指定 `--output` 时，Y-domain SPICE 默认写为 `<输入名>_fitted.y.sp`，其 JSON、HTML、日志使用同一文件名基底。`fit-yparam` 不会自动替代或覆盖 `fit-sparam` 的 SPICE、RFM 或 Touchstone 输出。

## 如何判读误差

报告中常用的两个量服务于不同目的：

```text
Y RMS = sqrt(mean(abs(Y_fit - Y_ref) ** 2))       # 单位 Siemens
Z-log RMS = sqrt(mean(log10(|Z_fit| / |Z_ref|)^2)) # 单位 decades
```

`--max-y-rms-siemens` 比较的是按端口数归一化的全矩阵 mean Y RMS，即上述逐频率、逐矩阵元素 RMS。`y_rms_siemens` 还保留未按端口数归一化的聚合值。Y RMS 用于确认拟合在导纳域的数值残差；项目的 Y-vs-S 算法选择以完整矩阵 `Z-log RMS` 为准。`Z-log RMS` 更低表示阻抗量级的相对误差更小。报告也会给出 `fitted_y_condition_max`：PDN 的 DC 点可能本身病态，不能仅凭一个绝对条件数数值判定失败，应同时查看输入与拟合条件数的比值及 Z 转换状态。

## 精确 Y-to-S RFM 交付

RFM 是 S 参数格式；不能把 Y 的 poles/residues 直接标为 S-RFM。需要 RFM 时使用以下显式交付路径：

```powershell
python -m agent_spice.cli fit-yparam .\board.s2p `
  --output .\deliverables\board.y.sp `
  --report .\deliverables\board.y.json `
  --no-fit-proportional `
  --exact-s-rfm .\deliverables\board.rfm `
  --exact-s-touchstone .\deliverables\board.s2p `
  --exact-s-rfm-wrapper .\deliverables\board-rfm-wrapper.sp `
  --subckt-name board_y
```

该命令执行：

```text
Y fit -> KYP continuous-frequency Y positive-real enforcement
      -> exact rational S = (I - Z0 Y) (I + Z0 Y)^-1
      -> S-RFM / S Touchstone
```

`--exact-s-rfm` 必须与 `--no-fit-proportional` 一起使用。当前 descriptor/proportional Y-to-S RFM 尚未实现；KYP 状态数超过 `--kyp-max-states`、求解器不能给出证书，或校正量超过 `--kyp-max-relative-correction` 时，命令会失败而不是降级为采样 S refit。

`--passivity check` 只是 sampled positive-real 检查。只有 successful exact-RFM 路径在 JSON 中写入 `passivity.enforcement = "KYP continuous-frequency certificate"` 时，才可称已经取得连续频率 Y PR certificate。

## 针对 HSPICE TRAN 场景的残差细调

`tune-yparam-tran` 是第二阶段工具：它只针对调用者明确给出的 HSPICE 签核网表优化已有 Y-derived S-RFM。它不会从 Touchstone 本身猜测激励、观测节点、时间窗口或 RMS 定义。

调用前需要准备：

1. 原始 Touchstone：用于约束带内静态 S RMS 和最大奇异值。
2. 已有的 Y-derived S-RFM：其中必须已经存在将要细调的实极点。
3. 同时包含原始参考路径和待替换 RFM 路径的 HSPICE 网表。
4. 网表中待替换的 RFM 文件名 token，且它必须恰好出现一次。
5. `.measure tran` 的 RMS 名称；峰值名称可选。

当前 CPM 场景的例子：

```powershell
python -m agent_spice.cli tune-yparam-tran `
  runs/yparam-tran-signoff/vddq_port3_port10.s2p `
  runs/yparam-tran-signoff/ybootstrap_blackbox.rfm `
  runs/yparam-tran-signoff/ybootstrap_blackbox.sp `
  --output-rfm runs/yparam-tran-signoff/ybootstrap_cli_tuned.rfm `
  --report runs/yparam-tran-signoff/ybootstrap_cli_tuned.json `
  --rfm-token ybootstrap_blackbox.rfm `
  --rms-measure yfit_vs_raw_rms `
  --peak-measure yfit_vs_raw_peak `
  --residual-poles 0.0628318530718,0.8115045878714,10.48098478623,135.3671238969,1748.33363523,22580.59720916,291639.6276132,3766670.63349,48648421.94905,628318530.718 `
  --band-boundaries 22580.59720916,3766670.63349 `
  --hspice-bin C:/synopsys/Hspice_T-2022.06-1/WIN64/hspice.exe `
  --license-file 27000@zzm-minicenter `
  --max-evaluations 150
```

候选参数是“残差频带 x S 矩阵响应组”的局部缩放。2-port 时 S12/S21 共用缩放，以保持互易项的相对关系。每个候选先满足：

- 输入 Touchstone 频点上的 S RMS 增长不超过 `--max-static-rms-growth`（默认 `0.003`）；
- 输入频点最大奇异值不超过 `--max-sigma`（默认 `0.999`）；
- HSPICE 成功输出 `--rms-measure`。

随后命令以 RMS 为目标执行 Nelder-Mead 搜索，在 `--work-dir` 保存每个候选的 RFM、网表和 HSPICE 输出，最终把最佳冻结模型复制到 `--output-rfm`，并写入 JSON 搜索报告。该过程是特定激励的优化，不是全场景、独立 held-out 或带外 IFFT 的生产签核。

## 项目级 Y-vs-S Z-log 门禁

算法选择不以单个 CPM transient 结果为准，而以独立频点的完整矩阵 Z-log RMS 为准。运行默认 corpus：

```powershell
python scripts/benchmark_yparam_corpus.py `
  --output runs-yparam-benchmark/corpus-heldout-order20.json
```

默认 corpus 包含：

- `user_input/spara/5power_19port_withcap_122324_202459_11476_DCfitted.s19p`；
- `user_input/spara/5power_30port_wocap_121124_221036_4876_DCfitted.s30p`；
- `runs/hspice-native-fit-comparison/vddq_port3_port10.s2p`。

默认协议为 10 个复极点代表（effective order 20）、6 次迭代、每 5 个频点留出 1 个。每项执行同一 pole budget、初始对数极点和迭代上限的 S/Y 拟合，并要求：

```text
heldout Z-log RMS(Y-fit) < heldout Z-log RMS(S-fit)
```

任一输入出现 Y 转 Z 失败、指标缺失、持平或落后，脚本返回非零。`--allow-nonwinning` 仅用于诊断时保留报告，不应用于算法固定。新增生产 `.sNp` 时，应将其作为位置参数传给 corpus 脚本或纳入默认列表，再重新运行门禁。

单文件诊断可直接使用：

```powershell
python scripts/benchmark_yparam_vs_sfit.py .\new-board.sNp `
  --pairs 10 --iterations 6 --holdout-stride 5 `
  --require-y-win `
  --output .\runs\new-board-y-vs-s.json
```

当前三项 corpus 的可复现结果、数值与边界见 [Y 与 S 拟合的 S19/S30P 基准](yparam-s19-s30-benchmark.md)，Y PR/RFM/TRAN 历史验证见 [Y-parameter fit: held-out、enforcement 与 TRAN 签核报告](yparam-heldout-tran-signoff-report.md)。

## 常见失败

| 现象 | 含义与处理 |
| --- | --- |
| `y_not_positive_real` | sampled PR 检查发现负 Hermitian 特征值；先检查输入、极点预算和拟合稳定性，不能将其标为 Y passive。 |
| `--exact-s-rfm requires --no-fit-proportional` | exact RFM 当前只支持 proper Y；加上 `--no-fit-proportional` 后重新拟合，或只交付 Y-domain SPICE。 |
| KYP 状态数超限或求解失败 | 降低极点数、提高 `--kyp-max-states`（会增加 SDP 成本），或保留 check-only 结果；不要以 sampled S refit 冒充 exact KYP 交付。 |
| `residual pole ... not uniquely present` | `--residual-poles` 必须与输入 RFM 中的稳定实极点精确对应；先检查 RFM 或缩小细调范围。 |
| `--rfm-token` 替换失败 | token 在网表中必须恰好出现一次。用一个仅代表待调 RFM 的相对文件名，避免把它同时写进注释或其他模型。 |
| corpus 返回非零 | 至少一个样本未严格满足 Y 的 held-out Z-log RMS 更低；先查看 corpus JSON 的 `cases[*].gate`，不要固定当前 Y 算法。 |
