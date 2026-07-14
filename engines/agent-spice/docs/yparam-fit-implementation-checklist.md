# Y 参数拟合实施清单

## 完成范围

- [x] 创建功能分支 `codex/fit-yparam`，未合并 `main`。
- [x] 在 [Y 参数拟合设计](yparam-fit-design.md) 固定 MVP 边界：Y 域服务 Z 需求，
  直接交付 `I=Y(s)V`，不直接拟合 Z。
- [x] 咨询只读 advisor，确认 Y 正实性、比例项和 S/RFM 隔离策略；实现后再次完成
  独立审查并修复其 P1/P2 发现。
- [x] 扩展 `NativeVectorFitting` 的响应矩阵选择，使其明确支持 `s` 和 `y`，保持 S
  为默认值。
- [x] 新增 `fit-yparam`：从标准 `.sNp` 读取 `network.y`，shared-pole 拟合且强制
  比例项，以支持电容导纳。
- [x] 对 S-to-Y 变换执行 fail-fast 病态检查。MVP 明确限制为共享正实 `z0` 与
  `power`/`traveling` wave；在该范围内检查 `cond(I+S)`。
- [x] 实现 Y 正实性 check-only：采样 `lambda_min((Y+Y^H)/2)`，并报告 D/E 的
  Hermitian 最小特征值。`check` 发现违规时 CLI 失败；`off` 可用于诊断导出。
- [x] 实现共同地 Norton/MNA SPICE 导出。端口电流方向为流入子电路；D 用 VCCS，
  `sE` 用隔离 VCVS、电容、0 V 测量源和 CCCS，极点项用状态电容网络。
- [x] 保持 `fit-sparam`、RFM、RFM wrapper 及自动 TRAN 编译路径不变。

## CLI 和产物

```powershell
python -m agent_spice.cli fit-yparam .\input.sNp `
  --output .\input_fitted.y.sp `
  --max-y-rms-siemens 0.001 `
  --passivity check
```

默认写入 `.y.sp`、`.y.json`、`.y.html` 和 `.y.log`。JSON 记录 Y 单位、RMS、
`z0`、`s_def`、频带、转换条件数、比例/DC 策略、极点、有限频带正实性采样及
检查结果。MVP 不生成 fitted Touchstone、RFM 或 Z 参数。

## 验证记录

- `python -m pytest -q tests/test_yparam.py`：`11 passed`。
  覆盖 RC、纯比例项、负电导、病态 S-to-Y、CLI、real/complex poles、二端口交叉
  导纳符号及 ngspice AC 比较。
- `python -m pytest -q tests/test_yparam.py tests/test_sparam_artifacts.py tests/test_cli_fit_sparam.py`：
  `54 passed`。
- `python -m agent_spice.cli fit-yparam runs-y-smoke/rc.s1p --output runs-y-smoke/cli-rc.y.sp
  --n-poles-real 1 --n-poles-cmplx 1 --fit-iterations 8 --max-y-rms-siemens 1e-5`：通过，
  RMS 为 `2.83510112813e-16 S`。
- 全量 `python -m pytest -q`：`863 passed, 5 skipped, 4 xfailed, 3 failed`。三个失败
  均来自开始本功能前已存在的 CLI/脏工作区不一致：缺
  `load_s19_tuning_report_summary`、缺 `run-stall-diagnostic` 子命令、以及
  `sparam.io` 顶层导入 scikit-rf 与 import-laziness 测试预期冲突；本功能未修改
  这些接口或 `sparam.io`。

## 后续不在本次范围

- Y 正实性 enforcement；
- 复数或逐端口 `z0`、pseudo waves 的准确病态性检查；
- Z 导出、Y-RFM、fitted Touchstone 和自动 TRAN 接入；
- 更密集的全频/渐近正实性证明。
