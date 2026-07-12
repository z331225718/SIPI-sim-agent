# Native Fit Product Exports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 native 拟合增加 RFM、fitted Touchstone 和中文可视质量报告。

**Architecture:** 新建一个纯导出模块，将 `VectorFitArrays` 在输入频率上评估为
S 参数并生成交付物；`fitting.py` 只负责调用，HTML renderer 接收预先计算的
质量摘要和图像。CLI 只增加显式 opt-in 参数。

**Tech Stack:** Python 3.11、NumPy、scikit-rf、Matplotlib、pytest。

## Global Constraints

- native 默认路径和未指定新参数的既有输出不变。
- RFM 与 Cadence BBS 示例的 `VERSION 200600` S 模型布局兼容。
- fitted Touchstone 必须使用输入的频率和参考阻抗。
- 报告为中文，默认展示 RMS 最大的 6 个元素。

---

### Task 1: Fitted Touchstone and RMS Summary

**Files:** Create `src/agent_spice/sparam/artifacts.py`; create
`tests/test_sparam_artifacts.py`.

- [ ] 写失败测试，要求 `evaluate_fitted_s` 返回 `(frequency,port,port)`、
  `write_fitted_touchstone` 回读值一致、`rank_element_rms` 降序稳定。
- [ ] 运行 `python -m pytest tests/test_sparam_artifacts.py -q`，确认导入失败。
- [ ] 实现评估、RMS 排名和 scikit-rf Touchstone 写入；保留输入 `z0`。
- [ ] 运行测试并提交 `feat(sparam): export fitted touchstone artifacts`。

### Task 2: Cadence RFM and Wrapper

**Files:** Modify `artifacts.py`; modify `tests/test_sparam_artifacts.py`.

- [ ] 写失败测试，要求 RFM header、每个元素块、实/复极点布局及 wrapper
  `rfmfile` 相对引用；比例项和非共轭极点必须拒绝。
- [ ] 运行新测试，确认 RFM API 缺失。
- [ ] 实现 `write_cadence_rfm(model, path, z0)` 与 `write_cadence_rfm_wrapper`。
- [ ] 运行测试并提交 `feat(sparam): add Cadence RFM export`。

### Task 3: Chinese HTML Quality Report

**Files:** Modify `fitting.py`; modify `tests/test_sparam_fitting.py`.

- [ ] 写失败测试，要求 HTML 包含中文质量标题、最差元素表和 base64 PNG 图。
- [ ] 运行测试，确认现有 renderer 不含这些数据。
- [ ] 实现受限 `top_rms` 数据路径、三轨曲线图和中文 HTML section。
- [ ] 运行 focused tests 并提交 `feat(sparam): enrich Chinese fit report`。

### Task 4: CLI Integration and Regression

**Files:** Modify `cli.py`, `fitting.py`; modify `tests/test_cli_fit_sparam.py`.

- [ ] 写失败 CLI 测试，覆盖三个导出参数、默认 wrapper、JSON artifact 路径，
  并断言未指定参数的旧路径不产生新文件。
- [ ] 实现参数解析和 opt-in 调度。
- [ ] 运行 CLI、artifact、fitting suites；提交 `feat(sparam): productize native fit exports`。

### Task 5: Final Review and Smoke

- [ ] 使用小型 fixture 执行真实 CLI，检查 `.sNp`、`.rfm`、wrapper、JSON 和
  中文 HTML。
- [ ] 运行相关完整回归。
- [ ] 独立 branch review，修复 P0/P1 后提交结论。
