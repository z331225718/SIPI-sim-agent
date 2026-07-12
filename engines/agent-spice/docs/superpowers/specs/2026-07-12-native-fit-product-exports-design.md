# Native Fit Product Exports Design

## Goal

把现有 native S 参数拟合变成可交付、可核验的工程产物：Cadence
Broadband SPICE 兼容 RFM、拟合后的 Touchstone，以及中文 HTML 报告和最差
RMS 曲线图。

## Scope

- `fit-sparam` 保持 native 默认路径和当前 SPICE 输出完全兼容。
- 额外输出 fitted Touchstone，频率、端口数和参考阻抗与输入一致。
- 输出 Cadence RFM：`VERSION 200600`、`NPORT`、`MATRIX_TYPE S`、`Z0`，每个
  S 矩阵元素使用常数、实极点和共轭复极点块；同时生成加载该文件的
  HSPICE/Sigrity wrapper `.txt`。
- HTML 报告使用中文，包含输入/模型/质量门、全矩阵 RMS、最差元素排名、
  导出物链接，以及前 N 个最差元素的原始/拟合/绝对误差图。

## Data Flow

native `VectorFitArrays` 是导出的唯一模型来源。导出模块先在输入原始频点
计算 fitted S，既写入 Touchstone，也计算每个 `Sij` 的 RMS。RFM writer 把
同一极点集合写入每个元素的 residue block；若极点不是实数或相邻共轭对，
明确失败，不生成不完整文件。HTML renderer 接收已计算的排序和 PNG data URI，
不重新拟合或重新计算模型。

## RFM Compatibility

以 `BBSResult...rfm` 为样本：实块每行写 `pole residue`；复块每行写
`sigma omega residue_real residue_imag`。常数项为 `Const`。wrapper 生成
`.subckt` 和 `.model ... S n=<ports>`，通过相对文件名引用 RFM。仅支持 S
模型、常数项、实极点、完整共轭对；比例项或非共轭极点必须给出明确错误。

## CLI and Artifacts

`fit-sparam` 新增可选参数：

- `--fitted-touchstone PATH`
- `--rfm PATH`
- `--rfm-wrapper PATH`（默认按 RFM 路径推导）
- `--report-top-rms N`（默认 `6`）

未指定导出参数时保持当前行为。若指定 HTML 报告，图表内嵌；若指定 fitted
Touchstone 或 RFM，JSON 报告列出真实路径和校验结果。

## Quality and Tests

- fitted Touchstone 回读后必须与模型计算值逐元素一致。
- RFM fixture 校验 header、块计数、实/复系数和 wrapper 引用。
- 报告测试验证中文标题、最差 RMS 排名、图像嵌入和导出路径。
- CLI 测试保证未指定新参数时 native 输出不变。

## Non-goals

- 不接入 MFT-NNLS，也不修改 native 拟合数学。
- 不实现 Cadence 的比例项/频率项 RFM 扩展。
- 不把 BBS 的 78 阶模型作为质量达标基线；它仅提供 RFM 格式参考。
