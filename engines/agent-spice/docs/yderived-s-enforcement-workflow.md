# Y-derived S enforcement 工作流

Y 参数拟合用于识别，最终交付为 S-domain RFM。不要把 Y 的 poles/residues 直接写成 S RFM：
`S=(I-z0Y)(I+z0Y)^-1` 是动态矩阵分式变换，会改变分母与极点。

## 命令

先从 Y 有理模型导出严格转换的采样 S：

```powershell
python -m agent_spice.cli fit-yparam <input.sNp> `
  --output yfit.sp --report yfit.json `
  --derived-s-touchstone y-derived.sNp `
  --n-poles-real 0 --n-poles-cmplx 30 --fit-iterations 20 --passivity check
```

再把该采样 S 作为新的 S-domain 拟合输入，执行现有 S passivity enforcement 并导出 RFM：

```powershell
python -m agent_spice.cli fit-sparam y-derived.sNp `
  --output yderived-sfit.sp --fitted-touchstone yderived-sfit.sNp `
  --rfm yderived-sfit.rfm --report yderived-sfit.json `
  --rms-target <conversion_budget> --passivity enforce --max-order <order>
```

`fit-yparam` 对每个点以严格线性求解实现转换，并检查 `cond(I+z0Y)`；它不使用伪逆。`yfit.json` 的 `y_derived_s` 记录转换后的 S 相对原始 S 的误差及条件数。`fit-sparam` 的 `comparison_mean_rms_error` 则是最终 S-RFM 相对 `y-derived.sNp` 的误差，也就是转换后 S 到最终交付 S 的总扰动。

## 门槛

在同一冻结评估频点上，同时检查：

| 指标 | 含义 |
| --- | --- |
| `A = RMS(S_raw, S_Y)` | Y fit 经 LFT 后的原始 S 保真度 |
| `D = RMS(S_raw, S_post)` | 最终 enforced S 的原始 S 保真度 |
| `E = RMS(S_Y, S_post)` | Y-derived S 到最终 enforced S 的扰动 |

用户所说的“转换后与 enforcement 后差不多”应至少满足 `D-A <= max(absolute_budget, relative_budget*A)`，同时限制 `E`。建议起始门为 `absolute_budget=1e-4`、`relative_budget=0.05`，但必须再配合独立的 `A` 与 `D` 原始 S 质量门；仅比较前后接近，可能同时保留一个很差的模型。

这条路径的无源性结论只能称为 **S-domain enforcement**，不能称为 Y enforcement。Y Norton/MNA 宏的 TRAN 问题也没有被该路径修复；这条路径交付的是新的 Y-derived S-RFM。
