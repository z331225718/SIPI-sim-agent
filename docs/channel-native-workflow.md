# SIPI 原生 Channel 工作流

2026-09-09。产品代码、入口和示例均位于 SIPI-sim-agent。本轮纠正了此前将新增 channel
CLI/bench 放入外部 PyBERT 仓库、但未连接 SIPI 的交付偏差。

## 入口与代码归属

`sipi channel simulate` 在进程内调用本仓库 `sipi-pybert-direct::run_sim_native_json`，
对应 PB-02 `sim-native` 的现有输入和数值工作流。没有调用 Python、外部 PyBERT checkout、
独立 `sipi-pybert-direct.exe` 或 ADS。ADS 只属于另行运行的对照 bench。

只增加 CLI 传输、示例和显示/导出；不另写 PRBS、FFT、metallic line、CTLE、FFE 或 DFE/CDR。
`meta.json` 的六键结构和 `arrays.npz` 保留原工作流输出，不注入 SIPI 字段。
兼容 metadata 中保留的 `pybert-python` 等上游标签不代表启动过 Python；
实际执行方及可执行文件 SHA-256 单独记录于 `receipt.json`。

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
| `report.html` | 离线曲线、工件链接、生效配置及诊断 |
| `receipt.json` | 成功完成标志；绑定全部上述工件和当前 exe 的长度/哈希 |

CSV 使用可 round-trip 的 f64 十进制，不拟合、不重采样、不调时移、不缩放。
HTML 是显示窗口：波形为前 32 UI，最多 4096 点；impulse 为前 4096 点。
窗口大小在报告中明示，不能以图片代替全量数值比较。所有原生数组仍在 NPZ 中。

请求最多 16 MiB，单份 CSV 最多 256 MiB；core 仍执行请求中的数值资源限制。
超限失败，不静默截短数据。`init` 不覆盖请求文件；`simulate` 要求新输出目录，
即使原目录为空也拒绝。失败时保留部分产物作诊断，不生成成功收据。
这不是敌对并发文件写入者的沙箱，也未承诺 OS 级内存硬限制或异步取消。

## 验证与边界

```powershell
cargo test --locked -p sipi-cli
cargo test --locked -p sipi-cli --features pybert-direct-integration
python -B tools/test_build_windows.py
```

集成测试从实际 `sipi` 子进程取得结果，与同一输入直接调用 owning Rust workflow 的
`meta.json`、`arrays.npz` 做逐字节比较，并逐位检查 CSV 中每个 f64 值。
另覆盖真实 metallic line、impulse + TX/RX FFE、输入错误/资源超限/未知字段、
重复 typed 字段、拒绝覆盖、HTML 转义、收据哈希、默认 feature 隔离，以及仅复制 exe、
移出 checkout、从 PATH 去掉 Rust/Python 后的真实仿真。

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
  --output-dir results/channel-ads-new --sipi $sipi --ads-root $ads --timeout 300
& $python -X utf8 -B tools/verify_channel_native_ads_bench.py results/channel-ads-new `
  --output results/channel-ads-new/verification.json
```

需要本机有效 ADS 安装及许可证。工具使用已安装的 ADS Python、Keysight dataset SDK、NumPy
和 Matplotlib；不下载安装依赖，不使用另一个 PyBERT 仓库。Python 仅承载 ADS bench，
不是 `sipi.exe` 的运行依赖。没有 ADS 时仍可使用前述原生仿真入口。

`init` 不覆盖已有 plan，`run` 要求新的输出目录。可重复指定 `--case NAME` 做定位，
但子集不会标成完整 plan。每个案例固定跑两次，逐个原始数组比较重复性。数值不通过或
运行失败都返回非零；以 `result.json` 中的完整 gates 和各 case 的 `error` 区分原因。
校验器只核对已产生的证据，不重新运行仿真；校验通过不等于数值对照通过。

当前校验包含输入/执行文件哈希、原始 ADS dataset 重新导出、完整 CSV 原值、原生数组、
时钟关系、全部 96 个 gate 及重复性。误差图只用于显示，不代替 CSV；所有图显示全部
配对点，频域对数误差图的显示下限不参与判定。

上文“仍需推进”第 1 项的 candidate 连接和逐点导出已经完成；物理参考合同、自检失败和
各层数值差异仍需继续处理，不能将第 1 项整体标为数值验收完成。
