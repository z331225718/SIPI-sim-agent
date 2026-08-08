# Y 参数拟合设计（MVP）

## 目标

为标准 Touchstone `.sNp` 输入提供一个独立的 `fit-yparam` 工作流。工作流在
Y 域执行有理拟合，并交付直接满足 `I = Y(s)V` 的 SPICE Norton/MNA 宏模型。

这个设计服务于以阻抗观察/供电网络为主的使用场景：Y 域避免在数据处理和拟合
过程中显式构造 `Z = Y^-1`。它**不**承诺对所有频点都能导出 Z；浮地、开路、DC
和谐振点的 Y 可以物理上奇异或病态，不能通过数值正则化悄悄掩盖。

## 范围与非目标

MVP 输入仍是符合 Touchstone 标准的 `.sNp`，以 scikit-rf 读取其频率、`z0`、
`s_def` 和 `network.y`。不引入非标准 `.yNp` 格式。

MVP 新增独立 CLI `agent-spice fit-yparam INPUT`，不会修改 `fit-sparam`、自动
TRAN S 参数编译或 Cadence RFM 的既有合约。这样 S-only 的 RFM、fitted
Touchstone 和 `rfm.cm` 不会被误用于 Y 模型。

首版不包含：

- 直接 Z 参数拟合或从 Y 强制求逆导出 Z；
- Y-RFM、Y Touchstone 或自动接入 HSPICE S 元件转换；
- Y passivity enforcement；
- Native topology sweep（其评分目前按 S 的最大奇异值定义）。

## 数学约定

端口电压和电流均相对于共同参考地，电流正方向定义为流入宏模型：

```text
I(s) = Y(s) V(s)
Y(s) = D + sE + sum_k R_k / (s - p_k)
```

极点必须稳定（`Re(p_k) < 0`）。Y 的单位为 Siemens，因此误差使用绝对 RMS
（S），不能复用 S 参数 `0.001` 的无量纲门槛。报告同时给出：

- `y_rms_siemens`：所有矩阵元素的 RMS 聚合值；
- `y_mean_rms_siemens`：按端口数归一化的值；
- 每个 `Y[i,j]` 的 RMS；
- 拟合频点范围和全量比较频点范围。

比例项 `sE` 在 Y 域是必需的：纯电容的导纳为 `sC`。因此 Y MVP 默认并强制
`fit_proportional=True`；CLI 不提供关闭它的静默路径。

## 输入转换与病态性

`network.y` 是从 Touchstone S 和其原始 `z0`/`s_def` 得到的派生量。读取后必须
检测所有 Y 值是否有限，并记录每个频点 S 到 Y 转换使用的矩阵条件数。条件数超过
配置阈值或转换失败时，默认 fail-fast，报告对应频率和原因。

MVP 仅接受所有端口共享的正实 `z0` 以及 `power`/`traveling` S-wave 定义；在这个
受限合约下 `cond(I+S)` 与实际 S-to-Y 求解的病态性一致。MVP 不对病态频点进行
裁剪、伪逆或正则化。以后若引入复数/逐端口 `z0` 或 pseudo waves，必须按
scikit-rf 实际变换矩阵重新定义条件数检查。

## 无源性语义

Y 模型的正实性检查与 S 模型不同。采样频率上的条件为：

```text
lambda_min((Y(jw) + Y(jw)^H) / 2) >= -epsilon
```

还须分别报告常数项 `Hermitian(D)` 的最小特征值；含比例项时，报告 `E` 的
Hermitian 部分，不能把有限频带采样宣称为全频保证。

MVP 提供 `--passivity {off,check}`，默认 `check`。检查覆盖原始频点、频带加密
点和极点邻域，报告最小特征值、发生频率、违规数、采样覆盖和检查局限。`check`
是 MVP 的质量门：发现违规时 CLI 返回失败；要只导出诊断模型须明确选择 `off`。
不得调用现有 S 专用的
`is_passive`、Hamiltonian、spectral projection 或 `constant_matrix_sigma < 1`
逻辑，也不得把 `enforce` 映射为未验证的 Y 修复。

## CLI 与交付物

初版命令形态：

```powershell
agent-spice fit-yparam .\input.sNp `
  --output .\input.y.sp `
  --report .\input.y.json `
  --passivity check `
  --max-y-rms-siemens 0.001
```

CLI 沿用已有阶数、频率选择和日志选项；`--max-y-rms-siemens` 是明确带单位的
质量门。目标搜索和自动阶数策略在完成 Y 专用质量门后才暴露。

MVP 产物：

- `.y.sp`：Y-domain Norton/MNA 子电路；每个端口电流源实现 `I = Y(s)V`，并写入
  端口电流方向及共同地参考约定；
- `.y.json`：`parameter_type: "y"`、单位、输入的 `z0`/`s_def`、转换条件数、
  RMS 定义、DC/比例项策略、极点稳定性和 Y passivity 检查结果；
- 可选 HTML 报告和日志。

第一版不会输出 fitted `.sNp`、`.rfm` 或 RFM wrapper。将 Y 转回 S 的输出功能须
单独设计，且只在每个频点转换条件满足要求时允许。

## 实现分期

1. 抽出 Native 拟合的响应矩阵选择和 RMS 计算，只接受 `s` 与 `y`，保持现有 S
   默认路径不变；Y 路径禁用 topology sweep 和 S passivity 代码。
2. 实现 `fit-yparam` 与 shared-pole Y fit，先完成 JSON/log 和解析测试。
3. 实现 Y-domain Norton/MNA exporter，并用 AC 与有理模型逐点比较。
4. 加入 Y 正实性 check-only 与 Y 专用质量报告。
5. 在独立设计和验证完成前，不实现 Y enforcement、Z 导出或自动 TRAN 接入。

## 验收测试

- 一端口 RC（包括 DC）和纯电容（验证比例项）；
- 互易二端口的交叉导纳及端口电流符号；
- 已知负电导的非正实模型；
- 浮地/奇异 Y 与 S-to-Y 病态转换的 fail-fast 路径；
- Y RMS、单位、JSON 语义和条件数记录；
- SPICE 宏模型 AC 与数学模型的逐点 `Y[i,j]` 比较；本机存在 ngspice 时运行集成
  测试，否则显式 skip；
- 简单负载 TRAN smoke；
- 完整保护 `fit-sparam`、RFM 和现有生产回归。
