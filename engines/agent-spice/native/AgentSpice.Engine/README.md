# Agent-Spice Engine

> 迁移说明（2026-07-16）：本目录中的 C# 引擎已经冻结为算法迁移与器件级差分 oracle。PI/SI 产品主线、默认 CLI、RFM 执行与平台 wheel 均已切换到 `native/agent-spice-sim` 的 Rust 实现；这里不再承接新功能。

这是自主仿真内核的第一条垂直切片，使用 .NET 8/C#，不依赖 ngspice、Python 或第三方 NuGet 包。除基础线性器件外，它可以直接解析项目的 `VERSION 200600` RFM，并以 N-port 状态空间设备执行 DC、AC 和 TRAN。

## 构建

```powershell
dotnet build native/AgentSpice.Engine/AgentSpice.Engine.csproj -c Release
```

## 运行

```powershell
dotnet native/AgentSpice.Engine/bin/Release/net8.0/AgentSpice.Engine.dll `
  native/AgentSpice.Engine/fixtures/divider.cir
```

直接运行 RFM：

```powershell
dotnet native/AgentSpice.Engine/bin/Release/net8.0/AgentSpice.Engine.dll `
  native/AgentSpice.Engine/fixtures/rfm_tran.cir `
  --rfm native/AgentSpice.Engine/fixtures/one_port.rfm
```

生产编排使用直接文件输出，避免调用方重新解析和改写大波形：

```powershell
dotnet native/AgentSpice.Engine/bin/Release/net8.0/AgentSpice.Engine.dll `
  native/AgentSpice.Engine/fixtures/rfm_tran.cir `
  --rfm native/AgentSpice.Engine/fixtures/one_port.rfm `
  --output-json native-result.json `
  --waveform-csv waveform.csv
```

生成可随 wheel 携带的 framework-dependent 运行时：

```powershell
./tools/build-native-engine.ps1
```

生成当前平台的 NativeAOT 引擎和平台 wheel（默认 `win-x64`）：

```powershell
./tools/build-native-engine-aot.ps1
./tools/build-native-wheel.ps1
```

构建脚本接受 `win-x64/win-arm64/linux-x64/linux-arm64/osx-x64/osx-arm64`，NativeAOT 必须在目标操作系统上构建；例如 Linux x64 使用 `-RuntimeIdentifier linux-x64`。CI 对 Windows x64、Linux x64、macOS x64/ARM64 构建并直接执行 wheel 内的引擎。NativeAOT 构建默认仅为本次命令使用 `https://api.nuget.org/v3/index.json`，不会修改用户全局 NuGet 配置。构建脚本会依次查找 `-DotnetPath`、`DOTNET_ROOT`、`~/.dotnet-sdk` 和 `PATH` 中带 SDK 的 `dotnet`。平台 wheel 只携带目标 RID，不依赖 .NET Runtime；未构建 AOT 时，普通 wheel 继续携带 framework-dependent DLL。

未指定输出文件时，标准输出是完整 JSON；指定 `--output-json` 后，标准输出只返回执行摘要。JSON 使用 source-generated metadata，可安全裁剪为 NativeAOT。结果包含节点电压、V/L/E/H 支路电流、AC 复数值，以及瞬态接受/拒绝/断点步数、Newton 迭代、预测器使用、线搜索回退和最大收敛残差。当前实现覆盖线性 R/C/L/V/I/E/F/G/H、PULSE/PWL/SIN/EXP、OP/DC/AC/TRAN、直接 RFM N-port、通用稀疏 LU，以及带动态电荷和 AC 增量导纳的 Level-1 二极管、BJT 与 MOSFET。RFM TRAN 可选 Trap 或变步长 Gear2，内部有理状态与动态端口响应进入同一套 LTE、拒步和回滚协议。

网表前端会在建立 MNA 前自主完成续行、`.param` 数值表达式、前向引用与循环检测、`.global`、嵌套 `.subckt`、实例参数覆盖、局部模型隔离、内部节点和器件层级重命名。表达式支持工程后缀、算术/幂/比较/逻辑/条件运算及常用数学函数。递归实例、未知参数、未知实例覆盖和无效 F/H 控制支路会显式失败，不会静默近似。

Level-1 二极管支持实例 `AREA/M/TEMP/DTEMP` 和位置式面积，模型支持 `IS/N/RS/BV/IBV/NBV/TNOM/EG/XTI/AREA/CJO/VJ/M/TT/FC`。预处理按面积与倍乘缩放电流、电容和串阻，按全局/模型/实例温度缩放饱和电流、结势垒和零偏电容，并预匹配反向击穿拐点；内部阳极节点对公共输出隐藏。OP/DC、AC 增量导纳以及 Trap/Gear2 的结电荷与扩散电荷共用同一温度化核。13 组 31 轮 NativeAOT 进程级门禁为 ngspice 的 `0.923x` 到 `1.108x`，中位比值 `0.993x`。

NPN/PNP BJT 支持实例 `AREA/M/TEMP/DTEMP` 和位置式面积，模型支持 `IS/BF/BR/NF/NR/VAF/VAR/IKF/IKR/RC/RB/RE/TNOM/EG/XTI/XTB` 以及 `CJE/VJE/MJE/CJC/VJC/MJC/TF/TR/FC` 守恒电荷。温度预处理缩放饱和电流、正反向增益、结势垒和零偏电容；高注入基区电荷同时进入静态传输电流、解析 Jacobian 与扩散电荷；三端串阻生成按 `AREA*M` 缩放且对公共输出隐藏的内部节点。14 组 31 轮 NativeAOT 进程级门禁为 ngspice 的 `0.940x` 到 `1.128x`，中位比值 `0.981x`。

四端 NMOS/PMOS MOS1 支持模型参数 `VTO/KP/GAMMA/PHI/LAMBDA/LD/RD/RS/RSH/TOX/UO/TNOM/NSUB/TPG/NSS/IS/JS/PB/CBD/CBS/CJ/MJ/CJSW/MJSW/CGSO/CGDO/CGBO/FC`，以及实例参数 `L/W/AD/AS/PD/PS/NRD/NRS/M/TEMP/DTEMP`；全局支持 `.temp` 与 `.options temp/tnom`。直接或片电阻会生成按 `M` 缩放、对公共输出隐藏的漏源内部节点；`TOX` 建立氧化层电容，在未给 `KP` 时按 `UO` 推导跨导参数，`NSUB/TPG/NSS` 可进一步推导缺省的 `PHI/GAMMA/VTO`，Meyer 半电容及路径积分状态进入 AC、Trap 和 Gear2。温度预处理按 MOS1 公式缩放 `KP/VTO/PHI/IS/JS/PB/CBD/CBS/CJ/CJSW` 并进入结限幅。Shichman-Hodges 正反向沟道、体效应、体二极管和结电荷仍通过四变量自动微分形成精确 Jacobian；噪声参数与更高阶 MOS 模型继续显式阻断。

节点名与同名 V/L 支路在内部状态中隔离。含 C/L、RFM 或动态半导体器件的 TRAN 使用可快照回滚的 Trap 或 `.options method=gear` 变步长 Gear2、源断点调度、历史解预测器与器件 charge/flux/state LTE；`.options nopredictor` 可关闭预测器做差分，`AGENT_SPICE_NATIVE_USE_STEP_DOUBLING_LTE=1` 仅保留旧三求解路径作为回归参考。`PULSE` 的零上升/下降时间按 ngspice 兼容语义使用 `.tran TSTEP`。RFM companion 继续在 MNA 外消元，按积分系数复用 N-port 核；2/8/16-port 的 Trap/Gear2 六组 31 轮 NativeAOT 进程级门禁为 ngspice 的 `0.760x` 到 `0.852x`。二极管 sidewall/高注入/隧穿/噪声与温度系数，BJT 复合泄漏/基极电阻调制/过渡时间偏置/excess phase/衬底结/噪声，MOS 更高阶模型，以及完整 SPICE 收敛策略尚未覆盖。
