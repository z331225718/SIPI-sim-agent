# RFM 直接接入 ngspice 使用说明

## 1. 适用范围

`run-rfm` 将 HSPICE/Sigrity/Cadence Broadband SPICE `VERSION 200600`、`MATRIX_TYPE S` 的 pole/residue RFM 直接交给 Agent-Spice 的 XSPICE `nport_rfm` device。

- **[实现事实]** 不执行 vector fitting，不使用 `fit-sparam`，也不生成包含大量内部状态节点的普通 `.sp` 有理函数宏模型。
- **[实现事实]** 默认求解器仍是 Windows 离线 ngspice；Xyce/XDM 不是安装或执行前提。
- **[实验验证]** 随包 `rfm.cm` 已在官方 Windows ngspice-46 上完成加载、DC、AC 和 TRAN 验证。
- **[实现事实]** 当前支持动态 N-port、每端口单端信号加一个公共参考 pin；差分/任意多参考映射尚未开放为稳定接口。

`.rfm` 不是 ngspice 原生可读取格式。实际读取它的是随 Agent-Spice 发布的 XSPICE code model。

## 2. RFM 格式与复极点约定

HSPICE `VERSION 200600` 的最小 S 矩阵 RFM 由四个全局头和每个矩阵元素的系数块组成：

```text
VERSION 200600
NPORT 1
MATRIX_TYPE S
Z0 50
BEGIN 1 1
CONST 0.1
C 0
DELAY 0
BEGIN_REAL 1
2.0e9 5.0e8
BEGIN_COMPLEX 1
3.0e9 -4.0e9 2.0e8 3.0e8
END
```

`BEGIN row column` 使用从 1 开始的矩阵下标，表示从 `port[column]` 到 `port[row]` 的响应。`C` 和 `DELAY` 为零时可以省略；Agent-Spice 导出时显式写零，读取第三方文件时两种形式都接受。当前实现拒绝非零 `C`、非零 `DELAY` 和非 S 矩阵，避免静默改变模型。

最容易写错的是 `BEGIN_COMPLEX`。一行四个数 `a b cr ci` 不是直接写系统极点，而是：

```text
omega_c = a + j*b
A_c     = cr + j*ci
term(s) = A_c/(s + omega_c) + conj(A_c)/(s + conj(omega_c))
system pole p = -omega_c
```

因此 Native 模型若保存正虚部代表 `p=sigma+j*beta` 及其 residue `R`，正确输出是 `-sigma -beta Re(R) Im(R)`；不能把 `R` 再共轭。RFM 可以选择共轭对中的任一成员，所以第二列正负都合法，但 residue 必须与所选成员配对。Python importer 和 XSPICE device 都会将两种方向规范化到正虚部系统极点。

这是 HSPICE S-element 的格式语义，不是 Agent-Spice 自定义约定。修复前由本项目生成的旧 RFM 可能被内部旧 parser “错误抵消”而通过回读测试，但在 HSPICE 中得到错误响应；这些文件必须用当前版本从原拟合结果重新导出，不能只改文件扩展名或 wrapper。

格式依据：[HSPICE Signal Integrity User Guide](https://ece.iisc.ac.in/~dipanjan/E8_262/hspice_si.pdf)、[Cadence PowerSI/Sigrity Broadband SPICE 输出说明](https://www.cadence.com/content/dam/cadence-www/global/en_US/documents/tools/ic-package-design-analysis/sigrity-resources/sigrity-powersi-extraction-best-practices-an.pdf)。

## 3. 电路写法

用户电路只需要实例化 CLI 将要生成的子电路。二端口示例：

```spice
Two-port direct RFM transient
Vsrc src 0 pulse(0 1 0 10p 10p 500p 1n)
Rsrc src in 50
Xchannel in out 0 rfm_direct
Rload out 0 50
.tran 2p 2n 0 2p
.print tran v(src) v(out)
.end
```

`Xchannel` 的节点顺序是 `p1 p2 ... pN ref subckt_name`。上例最后的 `0` 是公共参考，`rfm_direct` 是默认子电路名。四端口写法相应为：

```spice
Xpackage p1 p2 p3 p4 0 rfm_direct
```

不要在用户电路中自行 `.include rfm_direct_wrapper.sp`；CLI 会在运行副本中自动注入，原始输入保持不变。

## 4. 准备与执行

只生成可复现运行目录，不启动 ngspice：

```powershell
python -m agent_spice.cli run-rfm .\channel-tran.sp `
  --rfm .\channel.rfm
```

实际执行：

```powershell
python -m agent_spice.cli run-rfm .\channel-tran.sp `
  --rfm .\channel.rfm `
  --execute
```

指定子电路名、输出目录或 ngspice 路径：

```powershell
python -m agent_spice.cli run-rfm .\channel-tran.sp `
  --rfm .\channel.rfm `
  --subckt-name package_rfm `
  --output-root .\runs-rfm `
  --ngspice C:\Users\me\tools\ngspice-46\Spice64\bin\ngspice_con.exe `
  --execute
```

`--subckt-name` 必须与电路中的 X 实例一致。输出根目录的绝对路径当前不能含空白字符，这是 ngspice `codemodel` 命令在 Windows 上的加载限制。

## 5. Code model 选择

默认使用 Python 包内的 `agent_spice/lib/ngspice/rfm.cm`。临时覆盖：

```powershell
python -m agent_spice.cli run-rfm .\channel-tran.sp `
  --rfm .\channel.rfm `
  --code-model .\build\rfm.cm `
  --execute
```

也可设置环境变量：

```powershell
$env:AGENT_SPICE_RFM_CODE_MODEL = "C:\models\rfm.cm"
```

优先级为 `--code-model`、`AGENT_SPICE_RFM_CODE_MODEL`、随包 DLL。Backend 会把 DLL 暂存到运行目录，为本次运行生成隔离的 `.ngspice-scripts/spinit`，并通过 `SPICE_SCRIPTS` 加载；不会改用户或求解器安装目录。

**[实验验证]** 当前随包 DLL 与 ngspice-46 的 `--with-wingui --enable-xspice --enable-cider` ABI 匹配。其他 ngspice 版本或自行编译的不同配置没有兼容保证，应先做加载和 TRAN smoke test。

## 6. 运行产物

默认目录为 `runs/<deck stem>/rfm_direct/`：

| 文件 | 含义 |
| --- | --- |
| `case.source.sp` | 原始电路，逐字节保留。 |
| `model.input.rfm` | 原始 RFM，逐字节保留。 |
| `model.runtime.rfm` | 共享 pole union 的规范化 RFM；缺失 residue 补零，不重拟合。 |
| `rfm_direct_wrapper.sp` | 一个动态 XSPICE vector device 的连接 wrapper。 |
| `case.cir` | 注入 wrapper 并完成通用 ngspice 转换后的实际网表。 |
| `rfm_run_manifest.json` | 输入/运行 RFM SHA-256、端口数、阶次、频响重构误差和依赖清单。 |
| `stdout.log`、`stderr.log` | ngspice 原始日志。 |
| `run_summary.json` | 返回码、DLL 路径/hash 和 waveform 状态。 |
| `waveform.csv` | 可从 ngspice `.print` 输出解析时生成。 |

相对 `.include`/`.lib` 会递归暂存并转换；逃出电路目录的相对路径会被拒绝。绝对 include 保持原样。

## 7. 数值与步长

**[实现事实]** device 使用 scattering-wave 状态空间和梯形伴随模型，每个 transient step 更新 pole states，并向 ngspice MNA 写入端口电流及完整 N x N Jacobian。状态留在 code model 内部，不成为 MNA 未知量。

建议在 `.tran` 中显式给出 `Tmax`：

```spice
.tran Tstep Tstop 0 Tmax
```

保守起点为 `Tmax <= min(source_rise_time / 10, 0.2 / max(abs(pole)))`，再用步长减半比较关键波形。这个规则是精度建议，不是 parser 强制条件；极小 residue 对应的最快 pole 可结合实际敏感度放宽。强反射或接近 `det(I+S)=0` 的模型可能使端口 Schur 矩阵病态，device 会以 `nport_rfm ERROR:` 报错，CLI 将其视为失败而不是静默继续。

`run-rfm` 不修改输入模型的被动性。生产使用应优先输入已验证稳定且被动的 RFM；项目自身生成 RFM 时，应在 `fit-sparam` 阶段完成相应质量门。

## 8. 已知限制

- 仅支持 `VERSION 200600`、S 矩阵、单一实数正 `Z0`、稳定实极点或复共轭极点代表。
- 当前 wrapper 是 N 个单端端口加一个公共参考 pin；差分和多参考 incidence mapping 尚未实现。
- 单个 device 上限为 256 port；这是内存溢出防护，不代表 256-port 已完成性能签核。
- Windows 随包 DLL 只签核 ngspice-46 ABI；Linux/macOS 需要针对目标 ngspice 自行构建 `.cm`。
- 运行目录路径不能含空白字符。

## 9. 从源码构建 Windows DLL

构建只需要在发布/开发机运行，最终用户不需要 compiler、CMPP 或 Docker：

```powershell
poc\xspice-rfm\build-windows.ps1 `
  -NgspiceArchive "$env:TEMP\ngspice-46-source.tar.gz" `
  -OutputDirectory .\src\agent_spice\lib\ngspice
```

脚本会校验官方 ngspice-46 源码 SHA-256，并固定 XSPICE/CIDER configure flags。构建后必须重新运行聚焦测试和真实 Windows ngspice TRAN；不能仅凭 DLL 成功产出判断 ABI 可用。

技术取舍、官方接口证据、性能数据和 C 路线门槛见 [RFM 接入 ngspice 技术报告](rfm-ngspice-exploration-report.md)。
