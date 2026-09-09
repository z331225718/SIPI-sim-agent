# SIPI 原生 Channel 工作流

2026-09-09。产品代码、入口和示例均位于 SIPI-sim-agent。本轮纠正了此前将新增 channel
CLI/bench 放入外部 PyBERT 仓库、但未连接 SIPI 的交付偏差。

## 入口与代码归属

默认 `sipi channel simulate` 在进程内调用本仓库 `sipi-pybert-direct::run_sim_native_json`，
对应 PB-02 `sim-native` 的现有输入和数值工作流。没有调用 Python、外部 PyBERT checkout、
独立 `sipi-pybert-direct.exe` 或 ADS。ADS 只属于另行运行的对照 bench。

默认兼容模式只增加 CLI 传输、示例和显示/导出；不另写 PRBS、FFT、metallic line、CTLE、FFE 或 DFE/CDR。
`meta.json` 的六键结构和 `arrays.npz` 保留原工作流输出，不注入 SIPI 字段。
兼容 metadata 中保留的 `pybert-python` 等上游标签不代表启动过 Python；
实际执行方及可执行文件 SHA-256 单独记录于 `receipt.json`。
另有显式 `physical-voltage-v1` 模式，增加独立的负载电压和 impulse 时间原点处理；
它不覆盖 PB-02 行为，具体合同见下文。

候选构建：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\build_windows.ps1 -Check -Channel
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\build_windows.ps1 -Channel
$sipi = '.\target\x86_64-pc-windows-msvc\release\sipi.exe'
& $sipi channel init channel-request.json
& $sipi channel simulate channel-request.json --output-dir results/channel-native-run
Start-Process .\results\channel-native-run\report.html
```

直接使用 Cargo 时：`cargo build --locked --release -p sipi-cli --bin sipi --features pybert-direct-integration`。
`channel help`、`commands --json`、`protocols --json` 提供机器可读发现信息。
所有命令使用现有 `sipi.cli.response.v1` 外层 JSON；错误沿用路径无关的结构化诊断。

## 输入与输出

`channel init` 写出嵌入 exe 的 [metallic-line.json](../examples/channel-native/metallic-line.json)，
不是下载外部 fixture。输入采用已有 `pybert.simulation.v1`：

- 示例：32 Gbit/s NRZ、PRBS9 seed 17、512 bit、每 UI 16 点、dt 1.953125 ps。
- 通道：5 cm analytic metallic line，100 ohm 源/负载，显式端接电容；
  125 MHz 步进、64 GHz 最高频率、raised-cosine window、1 ns impulse 请求。
- 所有输入数值均为 SI 单位。频率网格、窗口和 impulse 截取采用现有 PB-02 行为；
  不把 64 GHz 输入带宽冒称为采样网格 256 GHz Nyquist 的实测覆盖。
- 也可使用已有 `impulse_response` 合同；`impulseResponseVoltsPerSecond` 是 V/s，
  core 按 dt 转换为离散卷积系数。不得将已离散化的 V/V kernel 直接填入这个字段。
- TX/RX、噪声和分析配置原样送入现有工作流，不强制关闭用户启用的均衡器。
  不支持的原生分支明确失败，不偷偷切 Python。该入口不额外支持 Touchstone 文件参数，
  也不改变 PB-02 会丢弃 direct-only CTLE impulse 扩展的兼容行为。

| 文件 | 内容 |
| --- | --- |
| `request.json` | 实际读取的原始请求字节 |
| `meta.json` | PB-02 生效输入、metadata、metrics 与 diagnostics |
| `arrays.npz` | 原生输出的完整数组集合 |
| `waveforms.csv` | time_s、TX、post-channel、RX input、RX output，全部原网格样点 |
| `channel-impulse.csv` | 从零开始的离散 kernel 时间轴和 V/V 系数，不再乘 dt |
| `report.html` | 完整波形/impulse 数据、离线曲线、工件链接、生效配置及诊断 |
| `channel-report.js` | 随 exe 内嵌输出的离线浏览控件，不访问网络、不需要 Node |
| `receipt.json` | 成功完成标志；绑定全部上述工件和当前 exe 的长度/哈希 |

CSV 使用可 round-trip 的 f64 十进制，不拟合、不重采样、不调时移、不缩放。
HTML 初始窗口为波形前 32 UI、impulse 前 4096 点，但嵌入的是完整原始波形和 impulse。
可以调整起始样点、窗口点数和游标，跳到最后一个样点；各阶段可分别开关，读数表保留
原始 `time_s` 和 f64 值。每窗最多显示 4096 个连续原始样点，不降采样、插值或峰值对齐。
窗口范围在报告中明示，不能以图片代替全量数值比较。所有原生数组仍在 NPZ 中。
浏览需保持 `channel-report.js` 与 HTML 同目录；禁用脚本时仍有原来的静态首窗和工件链接。
没有本地服务器、远端脚本或浏览器外的运行时依赖；CSP 禁止内联可执行脚本，只允许同源
脚本。实际离线运行不发起网络请求。

请求最多 16 MiB，单份 CSV 和 HTML 各最多 256 MiB；core 仍执行请求中的数值资源限制。
HTML 数值数组按借用切片流式写出，不先复制成一份完整 JSON 对象；超限不生成成功收据。
超限失败，不静默截短数据。`init` 不覆盖请求文件；`simulate` 要求新输出目录，
即使原目录为空也拒绝。失败时保留部分产物作诊断，不生成成功收据。
这不是敌对并发文件写入者的沙箱，也未承诺 OS 级内存硬限制或异步取消。

## 显式物理电压模式

同一个 `-Channel` 构建可以运行：

```powershell
& $sipi channel simulate channel-request.json --output-dir results/channel-physical-run `
  --channel-policy physical-voltage-v1
```

此模式在本仓库 `sipi-pybert-direct/src/physical_channel.rs` 内实现，只接受
`metallic_line`，沿用同一输入 schema。未传选项仍是 PB-02，未知 policy 明确失败。
没有启动外部 Python、PyBERT 或 ADS，也没有另写发射码型、FFT 或接收链路。

- 电压定义为 `Vload / Vhalf_open`，开路源电压为 native TX 的两倍；源电容位于 Rs
  之后，源/负载电容均按差分等效电路值使用，不隐式除以二。
- 使用既有材料传播常数和特征阻抗计算负载电压。DC 单独使用精确稳态电阻极限
  `2*Rl/(Rs + Rdc_per_m*length + Rl)`，不把复数参考阻抗的 power-wave S21 当作负载电压。
- 显式 `frequencyStepHz` 原值保留，所有导出频率键均为 `i * frequencyStepHz`；
  FFT 长度须满足 `N = 1/(df*dt)` 的整数网格校验。未给 df 时使用原生波形样点数。
  `frequencyMaxHz/df`、`impulseLength/dt` 也须为整数；只容纳浮点表示误差，不重采样。
- 最高材料频点不得高于 Nyquist。启用窗口时使用 `0.5*(1+cos(pi*f/fmax))`，末点
  精确为零；高于材料带宽到 Nyquist 的区间补零，不代表测量覆盖或高频外推。
  未加窗口的复数 Nyquist 端点会失败，不静默丢弃其有效虚部。
- kernel 始终从 t=0 保留，不裁切前缀、不按峰值对齐。只有显式 `impulseLength`
  截去尾部，且不得超过 FFT 周期。诊断记录保留长度、尾部能量比例、末四分之一能量、
  标称线时延和 kernel 峰值时刻。
- kernel 仍送入既有零历史、sample-hold 原生链路；用户启用的 TX/RX 处理不会被关闭。
  **有限频带的周期 IFFT 不等于连续时间因果求解**。特别是带宽补零、窗口和截尾，
  都可能使 ADS 的有限边沿物理 Transient 与当前波形不同，不能据原点保留宣称 TD parity。
- 除原有链路资源预算外，本阶段保守预留 `256*N` 字节；这不是操作系统内存硬限制。

`receipt.json` 的 `channel_policy` 明示所选模式。物理模式 `meta.json` 的 schema 为
`sipi.channel.physical-result.v1`，不是默认 PB-02 六键 metadata；其中
`diagnostics.physical_channel` 声明上述数值合同，`acceptance` 保持 false。
新增 `frequency-response.csv` 导出完整原频率网格上的未加窗负载电压传递函数与加窗响应
的实部/虚部；对应完整数组也写入 NPZ。该 CSV 同样绑定到收据哈希。

两种模式均已通过本机“仅复制生成的 `sipi.exe`、移出 checkout、从 PATH 去掉构建工具和
Python”的真实运行测试；程序不调用这些工具或另一个源码仓库。源码构建仍需要前述
构建工具。尚未在另一台干净 Windows 机器上验证系统运行时依赖，也未发布安装包；
本机测试不是跨机器部署、来源/许可审查或发布验收通过的声明。

对本轮 exe 执行 `dumpbin /DEPENDENTS` 还确认了 `VCRUNTIME140.dll` 和 UCRT 动态依赖。
目标机若报这些运行库缺失，需要与 x64 目标匹配的 Microsoft Visual C++ v14
Redistributable，版本不低于构建工具所需版本；这不是要求使用者安装 Rust 或完整 C++
Build Tools。使用[微软官方运行库说明与下载](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist?view=msvc-170)，
不要从第三方 DLL 下载站复制单个文件。本轮没有修改系统或自动安装运行库。

## 显式 Touchstone 与网络级联模式

同一个 `-Channel` 构建支持完整的 Touchstone S 参数网络工作流与多级级联：

```powershell
& $sipi channel init channel-touchstone.json --template touchstone-network
& $sipi channel simulate channel-touchstone.json --output-dir results/channel-touchstone-run `
  --channel-policy touchstone-network-v1
```

此模式由 `crates/sipi-channel/src/network_cascade_v1.rs` 与 `crates/sipi-pybert-direct/src/touchstone_channel.rs` 驱动，支持单文件（.s2p / .s4p）、内联 S 参数文本或解析网络级联：

- **Typed 端口映射**：支持 4 端口标准 Touchstone（1=TX+, 2=RX+, 3=TX-, 4=RX-）、相邻差分对（1=TX+, 2=TX-, 3=RX+, 4=RX-）及自定义映射；完整保留 2x2 差分 S 矩阵（$S_{dd11}, S_{dd12}, S_{dd21}, S_{dd22}$），不只取 S21。
- **频域网络级联**：支持 $N \ge 1$ 级网络在频域直接级联（基于精确无求逆的 Redheffer 矩阵星积），不将每段独立转为时域 impulse 拼接，也不使用有理拟合。
- **完整频网与覆盖诊断**：严检频率严格单调递增性，报告 DC（$f=0$）覆盖状态、网格均匀性与对仿真 Nyquist（$f_{Nyquist} = 1/(2\Delta t)$）的覆盖比例，不隐式插值/缩放。
- **无损与有界诊断**：使用数值稳定的二次型特征值分解评估离散采样最大奇异值（$\sigma_{max} \le 1$）与互易性差异（$|S_{12} - S_{21}|$），明确区分诊断与验收门。
- **负载传递函数与一次最终 FD-to-TD**：计入源/负载复阻抗端接（含 $R_S, C_S, R_L, C_L$ 寄生）与多重反射，计算全网格 $H(f) = V_{load}/V_{half\_open}$，仅在最终执行一次两边对称实 IFFT，严格保留 $t=0$ 原点，不裁切前缀或峰值对齐。
- **产物与收据**：收据声明 `channel_policy = "touchstone-network-v1"`，`meta.json` 采用 `sipi.channel.touchstone-result.v1` schema，`acceptance` 保持 false；全量导出 `frequency-response.csv`（全部 4 个 S 参数与加载/加窗 $H(f)$）、多级级联节点 `cascade-nodes.csv`、`waveforms.csv`、`channel-impulse.csv`、`report.html` 与 `channel-report.js`。
- **B6 噪声/抖动与眼图统计闭环**：当请求启用 `analysis` 统计选项时，自动输出 `eye-metrics.csv`（眼高、眼宽、电平及 ISI/DCD/PJ/RJ/DJ 抖动分解）、`bathtub.csv`（采样相位维度的 BER 浴盆曲线）与 `eye-contours.csv`（目标 BER 下的 2D 轮廓），并在离线 HTML 报告与 `channel-report.js` 中新增 BER Bathtub 曲线互动浏览视图。

## 验证与边界

```powershell
cargo test --locked -p sipi-cli
cargo test --locked -p sipi-cli --features pybert-direct-integration
python -B tools/test_build_windows.py
```

集成测试从实际 `sipi` 子进程取得结果，与同一输入直接调用 owning Rust workflow 的
`meta.json`、`arrays.npz` 做逐字节比较，并逐位检查 CSV 中每个 f64 值。
另覆盖真实 metallic line、impulse + TX/RX FFE、输入错误/资源超限/未知字段、
重复 typed 字段、拒绝覆盖、HTML 转义与写入预算、收据哈希、默认 feature 隔离，以及仅复制 exe、
移出 checkout、从 PATH 去掉 Rust/Python 后的真实仿真。
物理模式另检验 5 cm 无损匹配线的 250 ps 原点延迟、全波形逐点值、频率键逐位一致、
独立 ABCD/零长度 RC 方程、强衰减有限值及错误频率/时间网格的拒绝。

这些测试证明连接和导出没有改写数值，**不证明 ADS parity 或上游全工作流 parity**。
`sipi-pybert-direct` 保留独立 workspace 和既有 NOTICE；根 workspace 的 `exclude` 只是
允许显式可选依赖连接，不是许可决定或 release promotion。默认能力认证、冻结账本和
历史 source/hash 门不被更新为通过。发布前仍需独立审核候选构建的依赖和来源边界。

## 仍需推进

1. 将分层 ADS bench 的 candidate 改为本仓库实际 `sipi` 输出，绑定请求、exe 和原始 ADS dataset，
   保留全量点对点误差，不把此前外部 PyBERT 结果当成 SIPI 的通过证据。
2. 将通道输入质量、S 参数加载/参考面等工作流接入统一入口，不用 matched-S21 小切片替代完整 channel。
3. 继续处理已记录的 B2/B3 因果启动、B4 Transient 差异、B5 训练/CDR 和后续眼图/噪声覆盖。

TX Linear Fit 保持辅助工具；原 PyBERT 仓库的新增功能和研究图表不再作为另一套产品入口交付。

### 离线报告全时段浏览验证

本轮输出位于 `results/channel-native-browser-20260909/{compat,physical}/`。
两种模式分别用修改前冻结的 exe 与新 exe fresh 运行相同请求；`request.json`、`meta.json`、
`arrays.npz`、全部数值 CSV 逐字节一致。只改变显示、报告数据及其收据，不改变仿真内核。
`cargo test --locked -p sipi-cli` 为 49 项通过，启用 `pybert-direct-integration` 后为 60 项通过。
两模式各在 1440x1000、390x844 检查完整嵌入数据与 CSV 的 f64 精确一致性、最后样点、
单点窗口、边界/空输入、阶段开关、指针游标、绘图投影、禁用 JS 的静态显示及非空像素。

ADS 校验器同时严格识别旧静态报告和新报告的工件集合，不接受缺失脚本、额外工件或未知
显示策略。新 exe 的 `matched-native-grid` 双重复 ADS smoke 已完整复核，但只是单例连接
检查，`complete_bench_verified=false`；旧 v3 全七例的 14 次运行也已用新校验器复核，原有
`numerical_status=failed` 保持不变。本轮没有用报告升级替代 B0-B7 的剩余数值工作。

## 本仓库 ADS 对照入口

2026-09-09 已将独立物理通道 bench 接到实际 `sipi.exe channel simulate`，不再用外部
PyBERT 的输出充当 SIPI candidate。它属于开发诊断，不是 PB-02 compatibility 验收或发布门。
本次 fresh 对照的 7 个案例均未全部通过，详见
[数值诊断记录](channel-native-ads-diagnostics-20260909.md)。

特别注意：当前 PB-02 legacy 频率网格分支会裁切 impulse 并重置其原点；其波形时间轴
不能直接当作物理传播时延。复数 RC 参考阻抗下的 power-wave 归一化也不应直接等同于
实际负载电压。这些现有数值行为在本轮保持不变，没有为了通过 ADS 而平移或缩放结果。

```powershell
$ads = 'C:\Program Files\Keysight\ADS2026_Update1'
$python = Join-Path $ads 'tools\python\python.exe'
$sipi = '.\target\x86_64-pc-windows-msvc\release\sipi.exe'
& $python -X utf8 tools/run_channel_native_ads_bench.py init channel-bench.json
& $python -X utf8 tools/run_channel_native_ads_bench.py run channel-bench.json `
  --output-dir results/channel-ads-new --sipi $sipi --ads-root $ads --timeout 1800
& $python -X utf8 -B tools/verify_channel_native_ads_bench.py results/channel-ads-new `
  --output results/channel-ads-new/verification.json
```

对照物理模式时，改用新 plan 和新输出目录，不能复用默认模式的结果身份：

```powershell
& $python -X utf8 tools/run_channel_native_ads_bench.py init channel-physical-bench.json `
  --channel-policy physical-voltage-v1
& $python -X utf8 tools/run_channel_native_ads_bench.py run channel-physical-bench.json `
  --output-dir results/channel-physical-ads-new --sipi $sipi --ads-root $ads --timeout 1800
```

两种 candidate 使用相同的 7 例、ADS 参考、完整采样键和原门限。物理模式额外报告
`physical_vs_voltage_transfer`，将未加窗的真实负载电压传递函数与 ADS AC 比较；
`physical_vs_kernel_dtft` 仍检查实际截尾/加窗 kernel，TD gate 仍比较全部原始启动样点。
不以原始传递函数通过替代 kernel 或 TD 的失败。

校验器对物理模式另列 `declared_transform_diagnostic`：从重新读取的 ADS AC 参考出发，
按请求的窗口、补零、IFFT、截尾和零历史 sample-hold 重建 kernel 与波形，逐点定位
数值实现和带宽/启动合同的差异。该诊断不改变原 bench gate，也不是 ADS Transient 求解结果；
即使它全部通过，原 TD 失败仍保持失败。

需要本机有效 ADS 安装及许可证。工具使用已安装的 ADS Python、Keysight dataset SDK、NumPy
和 Matplotlib；不下载安装依赖，不使用另一个 PyBERT 仓库。Python 仅承载 ADS bench，
不是 `sipi.exe` 的运行依赖。没有 ADS 时仍可使用前述原生仿真入口。

`init` 不覆盖已有 plan，`run` 要求新的输出目录。可重复指定 `--case NAME` 做定位，
但子集不会标成完整 plan。每个案例固定跑两次，逐个原始数组比较重复性。数值不通过或
运行失败都返回非零；以 `result.json` 中的完整 gates 和各 case 的 `error` 区分原因。
校验器只核对已产生的证据，不重新运行仿真；校验通过不等于数值对照通过。

此前 v1 对照的校验包含输入/执行文件哈希、原始 ADS dataset 重新导出、完整 CSV 原值、原生数组、
时钟关系、全部 96 个 gate 及重复性。误差图只用于显示，不代替 CSV；所有图显示全部
配对点，频域对数误差图的显示下限不参与判定。

上文“仍需推进”第 1 项的 candidate 连接和逐点导出已经完成；物理参考合同、自检失败和
各层数值差异仍需继续处理，不能将第 1 项整体标为数值验收完成。

### ADS 参考 v2

此前 `init` 生成 `sipi.channel.ads-physical-bench.v2`，当前默认已升级为下述 v3；
原 v1/v2 plan 仍可执行和复核，不会被隐式迁移。v2 用 ADS 原生 TL 的 RLGC 映射替换有损 W_Element；仅零频点使用
独立稳态电阻电路，原线模型 DC 输出另列为诊断。全量 CSV 的 `reference_solver`
逐点说明参考来源，`ads_raw_line_h_re/im` 保留原线输出。门限、码型和时间键规则不变。

本机 v2 的 8 个材料 AC 控制已通过完整网格自检，但完整 7 例 SIPI/ADS 矩阵仍未通过：
此前 PB-02 candidate 为 1 例通过、5 例数值失败、有损 Transient 1 例在 300 秒上限超时。
这些不是发布验收，详见 [v2 诊断](channel-native-ads-diagnostics-20260909.md#参考模型-v2-续进)。
后续物理模式的完整 14 次运行已完成：7 例原始负载电压频域全部通过，但整例仍是
1 例通过、6 例 TD/kernel 数值失败，见[物理模式诊断](channel-native-ads-diagnostics-20260909.md#显式物理模式-v1)。

校验不完整运行时，默认仍失败。仅检查已经完成的工件可显式使用：

```powershell
& $python -X utf8 -B tools/verify_channel_native_ads_bench.py results/channel-ads-new `
  --output results/channel-ads-new/completed-runs-verification.json --allow-incomplete
```

此时必须同时读取 `verification_scope`、`incomplete_cases`、`all_plan_cases_selected`
和 `complete_bench_verified`，不能把进程退出 0 或完成子集的校验当作全矩阵验收。

### ADS 参考 v3 与独立控制

当前 `init` 生成 `sipi.channel.ads-physical-bench.v3`。v2 在材料表节点的 AC 自检通过，
但节点之间和带外的表格近似并不等于原解析材料定律，不能据此认定其 Transient 参考充分准确。
v3 在 ADS 请求的频率上直接计算解析 R/L/G/C，保留同一 TL 映射、独立 DC 电路和原始线输出。
仅参考求解精度改为更严格的电压/电流容差、`TruncTol=0.1`、`ChargeTol=1e-22`、
`MaxTimeStep=dt/16`；双方码型、电路、时间键和比较门限不变。

独立检查参考，不启动 SIPI candidate：

```powershell
& $python -X utf8 tools/qualify_channel_ads_reference.py run channel-physical-bench.json `
  --output-dir results/channel-reference-new --ads-root $ads
& $python -X utf8 tools/qualify_channel_ads_reference.py verify results/channel-reference-new `
  --output results/channel-reference-new/verification.json
```

标准七例计划扩展为 11 组 AC 控制与 5 组可用精确解的 TD 控制，每组重复两次。
AC 保留全部原始频率键，增加全部相邻中点、低频及至 4.096 THz 的带外抽查。
名义探针与既有键仅相差几个浮点单位时不重复插入，原始键不改，求解输出仍逐位核对。
TD 对照原零历史、原有限边沿的纯延迟/反射或单 RC 精确解，覆盖完整原始采样网格，
不做插值、对齐、缩放或启动点丢弃。双电容/有损线没有被冒充为已有精确 TD 控制。

`verify` 重新读取 ADS dataset，逐项核对执行网表、全部导出数组、完整 CSV、门限及双重复。
该控制工具要求完整七例计划，不接受案例子集冒充标准资格检查。
失败或不完整的控制不会升级为通过，输出始终 `acceptance=false`。
这些是参考模型的限定资格检查，不替代真正 SIPI/ADS 七例矩阵，也不证明全部带宽、
所有电路或完整链路已经通过。严格有损 Transient 可能耗时较长，前述完整七例矩阵命令
显式给出每进程 1800 秒上限；独立参考控制的单次进程上限为 180 秒。
超时仍保留失败，不能用 AC 控制补齐缺失 TD。

**当前 v3 有损 Transient 仍未通过卷积自检。** fresh 七例矩阵虽已完整运行两次，
有损 TD 最大差反而扩大到约 1.075 V。ADS 自身导出的原始频谱与实际卷积频谱亦明显不同，
因此不能把这个数字认定为 SIPI 的独立误差。详情见
[卷积响应诊断](channel-native-ads-diagnostics-20260909.md#v3-完整矩阵与卷积响应诊断)。
`oracle_contract_passed` 是历史保留字段，仅对应 `ads_vs_material_equations` 的 AC 网格检查，
不是整套 Transient 参考资格；新报告明确标为 `ADS AC material control`。

### ADS 卷积频谱诊断

本仓库的 `tools/diagnose_channel_ads_convolution.py` 复用同一 v3 网表生成器、ADS worker
和 SDK 校验器，不依赖外部 PyBERT checkout。它是 ADS bench 的开发工具，不是另一个
Channel 产品入口，也不增加 `sipi.exe` 的运行时依赖。

```powershell
& $python -X utf8 -B tools/diagnose_channel_ads_convolution.py run channel-physical-bench.json `
  --case lossy-metallic --output-dir results/channel-convolution-new --ads-root $ads
& $python -X utf8 -B tools/diagnose_channel_ads_convolution.py verify results/channel-convolution-new `
  --output results/channel-convolution-new/verification.json
```

默认依次执行 `adaptive`、`bounded125mhz`、`bounded31mhz`，每组两次 fresh 运行。
也可重复传入 `--profile` 选择明确的诊断设置；选择范围完整写入 plan，不冒充全矩阵验收。
固定间隔组保留 4.096 THz 上限，分别使用 125 MHz / 31.25 MHz 频率间隔与
65536 / 262144 的 `ImpMaxPts`。原电路、材料、源定义、求解容差及比较门限不改。
仅表征 StopTime 改为第一条源边沿之前的 100 ps，并开启 `ImpSaveSpectrum`。
第一条边沿过早的输入、旧版本参考、无卷积的 lossless TLIND、重复或缺失案例会明确拒绝。

- 全部 16 个元件复数分量分别比较 ADS 原谱与实际卷积频谱，保留全 ADS 网格与原 bench 网格的门限结果。
- `original-frequency-pointwise.csv` 为每个分量保留全部原频率键，记录原值、实际值、误差、门限及通过标记。
- 不存在精确 ADS 频率键时，CSV 保留该行但数据留空，JSON 明示缺失键，原网格 gate 不计算；不插值或对齐。
- 单独核对 raw loaded AC，包括原始 DC 点，不用独立 DC 电路替换掩盖线模型偏差。
- `verify` 重新读取全部 dataset 表与原始数组，重建网表，重算全部门限、CSV 和双重复。

`run` 数值失败或不完整返回非零；`verify` 退出 0 只代表证据完整且复算一致，
必须另读 `numerical_passed`。两者都不启动 SIPI candidate，始终 `acceptance=false`。
本轮实跑的三组均未合格，不能据此启动有损 TD 验收声明。详见
[原始频率键与两端口控制](channel-native-ads-diagnostics-20260909.md#原始频率键与两端口控制)。

另有显式的带宽隔离配置 `bandwidth8192ghz` / `bandwidth16384ghz`，固定 125 MHz
间隔，只把表征上限改为 8.192 / 16.384 THz；它们不会加入默认三组或自动重复扫描。
两组双重复均已实跑、SDK 复核，原网格最大误差没有收敛到原门限。
这些冻结配置中保留的 `ImpMaxPts` 不是经过证明的内存硬上限，也不据此推断现代 ADS
支持该历史参数；官方 2011 手册已将其列入 obsolete 控制。

**导出频谱诊断不能单独证明实际时域传递函数，也不是全部参考资格的充分条件。**
新的直通、分数延迟和单 RC 解析控制已把 AC、原采样键与全部 ADS 原生时点分开检查。
详见[带宽隔离与精确时域控制](channel-native-ads-diagnostics-20260909.md#带宽隔离与精确时域控制)。

已完成这五个控制的四档时间步长研究：`dt/16`、`dt/64`、`dt/256`、`dt/1024`，每例各两次。
原始 1024 个观察键从 `dt/256` 起全部过门限，但分数延迟叠加 RC 的原生时点在 `dt/1024`
仍有超差；原门限、失败和源电路全部保留，不继续加档扫描，不据此认定有损参考或 SIPI
时域验收通过。详细全原生时点结果见下述诊断文档的时间步长收敛记录。
