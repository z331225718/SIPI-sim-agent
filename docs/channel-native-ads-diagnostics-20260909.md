# SIPI 原生 Channel / ADS 数值诊断

2026-09-09。候选端为本仓库实际 `sipi.exe`，进程内使用既有 `sipi-pybert-direct`。
TX Linear Fit 不参与此次通道求解。本文不是 B0-B7 全链路、完整 PyBERT parity 或发布验收。

## 可复核证据

- [报告与全部曲线](../results/channel-native-ads-physical-20260909/report.html)
- [冻结 plan](../results/channel-native-ads-physical-20260909/plan.json)
- [完整结果](../results/channel-native-ads-physical-20260909/result.json)
- [dataset 重读及逐点复核](../results/channel-native-ads-physical-20260909/verification.json)
- [桌面/移动端视觉检查](../results/channel-native-ads-physical-20260909/visual/visual-verification.json)

结果目录是本机开发证据，不自动纳入源码提交或发布包；缺少本机结果时可按
[工作流文档](channel-native-workflow.md#本仓库-ads-对照入口)重新生成。

绑定的 Windows release candidate SHA-256：
`f278cba8460fa851c100337990f7fdfed376a83f7f0069810293f316478826d8`。
完整脚本、plan、ADS simulator/Python 和各次输入/产物身份在目录内保存。
7 cases x 2 runs，28,672 个时域配对点、7,182 个频率配对点，原始 ADS Transient
合计 653,006 点。原始 dataset 通过 Keysight SDK 重新读取，与导出 NPZ 全量一致；
CSV 原值、全部 96 个 gate 和两次运行重复性均经复核。**数值总结果仍为 failed。**

## 参考合同

每例为 NRZ 显式冻结码型，关闭 TX/RX 均衡、噪声和抖动，用于定位 line stage。
参考不是 candidate kernel 驱动的 ADS 行为源：理想线用 ADS TLIND；有损线由已声明的
材料参数产生 R/L/G/C 表，再由 ADS W_Element 求解分布网络。没有导入 SIPI 响应作为模型。
裸线长 5 cm，源/负载阻抗与电容均显式给定。物理负载电压相对于半开路发射电压比较，
ADS AC 开路源固定为 2 V，Transient 开路源固定为 2 倍 SIPI TX；不是结果拟合的增益。

SIPI 的 t=0 对应 ADS 预先声明的四 UI 发射时钟原点，本次为 125 ps。
ADS 从零源、零 DC 平衡开始，在该时钟原点前 dt/8 内线性爬升到首个码元，之后每个码元
边界同样用 dt/8 边沿。零源前导用于建立正确的历史状态，不丢弃任何 SIPI 启动样点。
原始 ADS 时间轴全部保留；以 `ADS time = declared origin + SIPI time` 取已有时间键，
无插值、输出拟合时移、暖机点剔除或幅度优化。14 次运行的时间键误差均为 0。

门限在 fresh 求解前冻结：电压 `2e-8 V + 1e-7 * abs(reference)`；复数传递函数
`1e-9 + 1e-8 * abs(reference)`。统计使用全网格，没有为了通过而增加门限。
CSV 中复数误差逐点使用 scalar abs；gate 使用 NumPy vector abs，两种运算分别精确复核，
不以舍入容差掩盖导出差异。

## 结果

下表为第一次运行，第二次全部原始数组与之相同。频域为复数绝对误差，不仅比较幅度。

| 案例 | TD 最大误差 (V) | kernel DTFT 最大误差 | terminated 最大误差 |
| --- | ---: | ---: | ---: |
| matched-native-grid | 4.7250e-8 | 5.0298e-7 | 无该 telemetry |
| matched-legacy-grid | 1.06505 | 2.00227 | 5.0298e-7 |
| mismatched-legacy-grid | 1.56939 | 2.94478 | 1.0668e-6 |
| source-cap | 1.38324 | 1.43322 | 1.32437 |
| load-cap | 1.00003 | 1.91086 | 0.396596 |
| both-cap | 0.665259 | 1.25034 | 1.95768 |
| lossy-metallic | 1.04897 | 1.85725 | 1.17433 |

`matched-native-grid` 的 1024 个时域点全部通过。其余六例的时域全点 gate 均不通过。
所有案例的 source-delivery gate 均通过，发射码型在配对时间键上完全一致。

## 已定位与待定位

1. **显式码型 CLI 缺陷已修复。** `PatternV1` 序列化字段为 `bit_count`，但 SIPI strict
   preflight 曾只允许 `bitCount`，导致合法显式码型无法从 CLI 进入。修复
   `runner.rs::strict_pattern` 的白名单；新增真实 `sipi` 子进程回归，拒绝错误 camelCase
   拼法和双别名。未改 copied `input.rs` 或任一数值算法。
2. **legacy kernel 不能解释为绝对传播时间。** 5 cm、2e8 m/s 理想线的 native-grid kernel
   峰在第 128 点，即 250 ps；相同线的 legacy-grid kernel 峰在第 11 点，即 21.484375 ps。
   legacy terminated 非 DC 响应与 ADS 的最大误差仅 2.001e-9，但实际 kernel 的 DTFT
   误差达到 2.00227。源码路径是 cubic resample 后 `trim_legacy_impulse`，丢弃裁切原点，
   下游从零卷积。这解释了为何只对频域原始 S21 或手动平移波形会掩盖问题。
3. **复数端接的参考定义需要分开。** 当前 PB-02 metallic workflow 使用 power-wave
   S 参数 renormalize，再乘 `sqrt(Zload/Zsource)`。这不是本 bench 的实际负载电压合同。
   单独启用源/负载电容即可使 terminated 与 ADS 在非 DC 频点明显分离；不应靠改一个
   全局幅度常数通过。需要显式的物理 voltage-transfer 工作流，同时保留旧兼容行为。
4. **ADS 本身不是无误差真值。** 额外用材料表的两端口 ABCD 方程自检 ADS AC。
   六个理想线案例仅 DC 自检不通过，误差约 5.05e-7 到 1.16e-6；有损 W-element 的
   513 个频点自检均失败，最大 0.0163996。单独 AC 的 fresh probe 得到相同差异，
   因此“由 AC/Transient 同跑触发”这个假设已排除，根因仍待定位。
   有损 Transient 日志还记录了 ADS 的高频扩展与卷积建模，不能默认等价于原生的
   64 GHz 截止、raised-cosine 和裁切策略。这部分不得一概记成 SIPI 数值错误。

## 本轮验证

- 默认根 CLI 49 tests 通过；三个 direct integration feature 同开 69 tests 通过。
- 其中原生 channel 8 tests，含显式码型和复制 exe 到 checkout 外、移除构建工具 PATH 的实跑。
- owning direct artifact suite 16 tests 通过；bench 5 项参数/材料/门限/JSON 测试通过。
- Windows `build_windows.ps1 -Channel` release 构建和数值 smoke 通过。
- Clippy、Rust 2024 rustfmt、git diff whitespace 检查通过。
- Playwright 在 1440x1000、390x844 检查 14 张实际数值图、141 个本地链接、96 个 gate 行，
  图片非空、页面无横向溢出、展开与导航可用。移动端图表保留横向滚动，不压缩数值到不可读。

早期 probe 目录保留了字段检查失败、ADS sweep/library 语法失败、初值预充电差异和
UseInitCond 跳过 t=0 的证据；没有覆盖旧结果或将这些失败改写为通过。

## 下一步

先排查有损 W-element 与材料合同的差异，并为物理 voltage-transfer、绝对时延及
频域窗口建立明确入口，再接入现有网络级联/Touchstone 和 EQ/CDR 分层 bench。
PB-02 兼容模式不能静默改变；不得将本轮理想线通过冒称为 B0-B7 全链路通过。
既有冻结 PLAN、来源哈希、许可隔离和发布门保持原状，没有重写为绿色。

## 参考模型 v2 续进

本节补充后续实跑，不覆盖上文 v1 失败证据。所有工具修改仍在 SIPI 仓库内，
本轮没有修改 Rust Channel 数值行为或重新构建 `sipi.exe`。

### 频域参考校准

对 8 份冻结材料请求拆分验证：无损线、DC 电阻、趋肤损耗、介质损耗及端接电容组合。
W_Element 即使在无损情况下也出现随频率线性增长的相位差；AC-only 排除了与 Transient
同跑的影响。该现象尚不能证明 ADS 内部具体实现有误，也没有据此拟合线长或速度。

改用 Keysight [Netlist Translator 文档](https://edadownload.software.keysight.com/eedl/ads/2009u1/pdf/netlist.pdf)
第 114/127 页所列原生 TL 映射：`Z=sqrt(L/C)`、`V=1/(c0*sqrt(L*C))`、显式 R/G/物理线长。
`c0` 使用 ADS 自身常量；本机 2026 Update1 会忽略旧文档的 `F=0`，故不传该参数。
无损线仍用 TLIND。另按已安装的 `ccsim/Options.html` 开启 `ForceS_Params=yes`，
避免无损谐振点的部分数值误差；该选项不能解决线模型 DC 异常。

v2 明确分开两项求解：非零频点来自 ADS 分布线；恰好 0 Hz 来自独立 ADS 稳态电阻电路，
其源电阻为 `Rs + Rdc_per_m * length`、负载为 Rl，所有电容在 DC 开路。
这是声明电路的精确 DC 极限，不是插值、外推、增益拟合或删除零频点。
原线模型全部输出保持不变，DC 异常继续保存在 dataset、CSV、JSON 和报告表格中。

[AC 参考资格检查](../results/channel-native-ads-material-investigation-20260909/reference-v2-controls/result.json)
中，8 份请求各运行两次、每次完整 513 频点，共 8,208 点全部通过原频域门限，
每个原始数组精确重复；[SDK 重导出与逐点复核](../results/channel-native-ads-material-investigation-20260909/reference-v2-controls/verification.json)通过。
最差控制为纯趋肤损耗，最大复数差 `4.980057e-9`；有损加双电容的最大差为 `5.938980e-15`。
这仅验证 AC 参考合同，不证明 SIPI parity 或 ADS Transient 精度。

### SIPI 实跑与未完成项

[v2 全矩阵尝试](../results/channel-native-ads-reference-v2-20260909/report.html)没有缩减原 7 例计划。
前 6 例各跑两次，12 份 dataset、12,288 个时域配对点和 6,156 个频域配对点完成复核。
这些案例的 AC 参考自检均通过；`matched-native-grid` 的全部 gate 通过，另 5 例仍失败。
它们的主要差异仍是 legacy impulse 原点和复数端接电压定义，不靠参考端改动消除。

第 7 例 `lossy-metallic` 的 TL Transient 在 300 秒进程上限内未完成，工作进程及其
ADS 子进程已终止。日志显示自适应卷积表征到 4.096 THz、初始频率间隔 1 GHz；
这不等同于 SIPI 的 64 GHz 频带/窗口。该例没有被标为通过，也未把 AC 控制代替其 TD 结果。

默认校验器对该不完整矩阵明确失败且不写成功证明。显式 `--allow-incomplete` 仅重读
已完成的 12 次运行；[局部工件复核](../results/channel-native-ads-reference-v2-20260909/completed-runs-verification-checked.json)
记录 `complete_bench_verified=false` 和缺失案例，不提供完整矩阵或发布验收。
旧 v1 的 14 次完整运行仍能由更新后的校验器重读，原数值失败状态不变。

本轮 bench 回归 7 项在 ADS Python 下通过；无 NumPy 的根 venv 为 2 项通过、5 项明确跳过。
桌面/移动端的 12 张图、121 个链接、82 行 gate 和 1 个不完整案例显示通过 Playwright 检查。
本轮未改 Rust 文件，未重跑 Rust 全套测试；实际 candidate exe 哈希仍与上文 v1 一致。

下一步仍需接入明确的物理电压/绝对时延工作流，并处理有损线 FD-to-TD 频带、启动及
卷积开销，再继续网络/Touchstone、EQ/CDR 和 B6-B7；不能把本次参考校准当作主线完成。

## 显式物理模式 v1

后续已在 SIPI 本仓库接入 `--channel-policy physical-voltage-v1`，独立计算实际负载电压，
保留 impulse 的零时刻原点，再交给既有原生链路。PB-02 数值源码和默认行为未改。
完整定义和调用方式见[工作流](channel-native-workflow.md#显式物理电压模式)。

最初一次尝试暴露显式频率键的舍入问题：把输入 125 MHz 经 `1/(N*dt)` 重新计算，
会差一个浮点表示单位，不能通过 exact-key 检查。新增回归先复现失败，再改为保留
请求 df 原值；没有放宽键匹配或电压门限。该尝试在用户要求暂停核对仓库时中止，
[原始目录](../results/channel-native-physical-policy-20260909/README-interrupted.md)保留，未伪造完成结果。

### 完整实跑

- [物理模式报告](../results/channel-native-physical-grid-fixed-20260909/report.html)
- [冻结 plan](../results/channel-native-physical-grid-fixed-20260909/plan.json)
- [全部结果](../results/channel-native-physical-grid-fixed-20260909/result.json)
- [独立复核](../results/channel-native-physical-grid-fixed-20260909/verification.json)
- [桌面/移动端检查](../results/channel-native-physical-grid-fixed-20260909/visual/visual-verification.json)

candidate exe SHA-256 为
`021880c643d6a2930f4dffd95adc8419e4c5d845b936b66e137c93fb35b1ff19`，副本保存在结果目录。
沿用原 7 例、相同码型、电路、时间键和门限，每例两次。此次每进程上限为 900 秒，
有损 Transient 两次均实际完成，没有将 AC 控制冒充 TD；全部子进程已退出。

14 次运行共 28,672 个时域配对点、7,182 个频率配对点、652,572 个原始 ADS Transient
点。candidate 和 ADS 全部原始数组均精确重复。SDK 重导出、CSV 原值、98 个原 gate
及工件哈希复核通过，无缺失案例。`complete_bench_verified=true` 仅说明完整证据核验，
**数值总状态仍为 failed，acceptance=false。**

下表为 repeat-1；repeat-2 原值相同。所有负载电压频域 gate 和 AC 材料自检均通过。

| 案例 | TD 最大误差 (V) | 实际 kernel DTFT 最大差 | 负载电压复数最大差 |
| --- | ---: | ---: | ---: |
| matched-native-grid | 4.70002e-8 | 5.01303e-11 | 5.01303e-11 |
| matched-legacy-grid | 0.390115 | 0.471151 | 5.00142e-11 |
| mismatched-legacy-grid | 0.568767 | 0.680740 | 2.93808e-11 |
| source-cap | 0.109722 | 0.112684 | 5.76796e-11 |
| load-cap | 0.109722 | 0.112684 | 5.76805e-11 |
| both-cap | 0.0818070 | 0.704788 | 5.00043e-11 |
| lossy-metallic | 0.0588640 | 0.122399 | 7.20567e-15 |

只有 native-grid 理想匹配线整例通过。其余 6 例的全部 TD 样点未达到门限，实际
kernel 对未加窗物理传递函数的 gate 也失败；不删除启动点、不平移或缩放来获得通过。

### 剩余差异

物理模式无损线峰值保留在 250 ps，不再是旧 legacy 的 21.484375 ps。
复数端接的负载电压定义也已在此次完整频域网格上验证。剩余问题不能继续归咎于这两项。

独立校验从 ADS AC 的原始解，按显式窗口、补零、IFFT、尾部截取和零历史 sample-hold
重建 kernel 与波形。14 次运行的这 42 个附加诊断全部通过：kernel 最大差
`5.077236e-12`，sample-hold 波形最大差 `4.120232e-11 V`。这证明当前离散合同的实现
与重建一致，**不是连续时间 ADS Transient 通过**，不改变原 98 个 gate 或总状态。

材料上限 64 GHz 与 256 GHz Nyquist 之间的补零、窗口以及 1 ns 截尾仍改变实际响应。
例如 `both-cap` 的 1 ns 截尾丢弃约 10.5% 的全周期 kernel 能量；只修复原点并不能保留
完整反射尾部。ADS 有损 Transient 则记录了至 4.096 THz 的自适应卷积表征。
这些证据要求下一轮明确共同的发射边沿/带宽、验证 kernel 时长收敛和因果启动；
不能把 ADS 的时域合同默认为当前有限带宽 sample-hold 合同。

之后仍需接入网络/Touchstone、端口/参考面与 EQ/CDR 分层对比，再推进 B6-B7。
未将此物理模式标成完整 PyBERT、全链路 ADS 或正式发布验收。

### 回归与部署边界

本次根 CLI 默认 49 项、三个 integration feature 同开 72 项通过，其中 Channel 11 项；
涵盖频率键逐位回归、250 ps 延迟、NRZ/duobinary/PAM4 原生网格样点数、均衡保留与失败边界。
owning crate 的 62 项库测试、16 项 artifact 测试通过。ADS bench 回归 9 项通过；
无 NumPy 的根 venv 为 3 项通过、6 项明确跳过。Windows 构建脚本 7 项通过。
Clippy、Rust 2024 格式与 whitespace 检查通过。

离线物理/兼容报告均在 1440x1000 与 390x844 检查过实际曲线、链接和展开导航。
bench 的 14 张图、143 个链接和 98 行原 gate 通过相同桌面/移动端检查；图表为真实数据，
无空白图或页面横向溢出，宽图表保留自身滚动。
构建产物仍动态依赖 VCRUNTIME140/UCRT；本机 PATH 隔离实跑不是干净远端 Windows 部署验收，
具体[运行库检查](../results/channel-native-physical-grid-fixed-20260909/candidate-runtime.md)已保存。
本轮改动尚未提交/推送，未改来源许可和正式发布门。

## 参考模型 v3：网格之外与精确时域控制

后续调查发现，v2 材料表的 513 个节点通过，不足以证明 Transient 使用的整个材料响应正确。
新增本仓库 `tools/qualify_channel_ads_reference.py`，用相同输入和原比较门限分别 fresh 运行
v2/v3 参考，不启动 SIPI，不把研究 Python 算法当作产品候选。

- [v2 全部控制](../results/channel-ads-reference-qualified-v2-20260909/result.json)与
  [SDK/逐点复核](../results/channel-ads-reference-qualified-v2-20260909/verification.json)
- [v3 全部控制](../results/channel-ads-reference-qualified-v3-20260909/result.json)与
  [SDK/逐点复核](../results/channel-ads-reference-qualified-v3-20260909/verification.json)

每个版本均有 11 组 AC 控制、5 组精确 TD 控制，各重复两次，完整完成 32 次 ADS 运行。
每个版本独立复核 27,938 个 AC 点和 10,240 个原始 TD 配对点，所有原始数组精确重复；
执行网表、dataset、SDK 重导出、CSV 原值及全部 gates 均已核验。
AC 控制包含原七例，以及 DC 电阻、纯趋肤、纯介质和有损无电容四个材料隔离案例。
频率保留原全部节点及全部中点，另检查低频和至 4.096 THz 的带外探针。

| 控制，repeat-1 | v2 最大差 | v3 最大差 | 原门限结果 v2 / v3 |
| --- | ---: | ---: | --- |
| 有损双电容 AC，V/V | 0.0725003 | 1.48680e-12 | failed / passed |
| 纯趋肤 AC，V/V | 1.33983 | 9.77790e-11 | failed / passed |
| 纯介质 AC，V/V | 0.414072 | 3.01432e-9 | failed / passed |
| 有损无电容 AC，V/V | 0.384584 | 1.67357e-12 | failed / passed |
| 源端单电容 TD，V | 8.33134e-7 | 4.70000e-8 | failed / passed |
| 负载单电容 TD，V | 8.33134e-7 | 4.70000e-8 | failed / passed |

有损双电容的 v2 AC 为 523/1037 点超差；最大差位于 62.5 MHz，即原表第一个区间的中点。
两个 v2 单电容 TD 控制均为 384/1024 点超差，不能全部归咎于 SIPI。
v3 的 16 组控制全部通过，但这不是有损线或双电容线完整 TD 的精确解认证。
原比较门限仍为电压 `2e-8 + 1e-7*abs(reference)`、传递函数 `1e-9 + 1e-8*abs(reference)`。

v3 改为在 ADS 自身请求的频率处求解析材料表达式，不再把有限 PWL 表作为材料频率定律。
TL 拓扑、线长、速度、电容、源幅度和时间键不改；原独立 DC 控制与 raw line 输出继续保留。
TD 仅收紧参考求解参数：`V_RelTol=I_RelTol=1e-11`、`V_AbsTol=1e-14`、`I_AbsTol=1e-17`、
`TruncTol=0.1`、`ChargeTol=1e-22`、`MaxTimeStep=dt/16`，没有放宽比较门限。
这些实跑证明 v2 表示和参考求解设置需要修正，并不证明 ADS 内部实现存在错误。

首次新增探针时，native 网格中三个已有键与名义探针只差浮点舍入，ADS 合并了它们，
严格数组检查因此拒绝了该次控制；[失败现场](../results/channel-ads-reference-qualification-v3-20260909/result.json)保留。
修复仅避免重复插入与已有键同频的名义探针，全部原始键和中点逐位保留；没有放宽求解输出键校验。
回归先复现失败，再验证无近重复键及原始键完整，最终 fresh 重跑整个控制矩阵。

更新后的共用 SDK 校验器仍能复核旧 v1 和 v2 的各 14 次完整 SIPI 运行，旧数值失败不变：
[v1 复核](../results/channel-native-v1-reverified-sdk-helper-20260909.json)、
[v2 复核](../results/channel-native-v2-reverified-sdk-helper-20260909.json)。

### v3 完整矩阵与卷积响应诊断

[完整七例报告](../results/channel-native-physical-reference-v3-20260909/report.html)和
[原始结果](../results/channel-native-physical-reference-v3-20260909/result.json)已生成。
沿用同一 candidate exe `021880c6...5b1ff19`、全部原七例和双重复，未缩短有损例的 8192 个
原始时间键。14 次全部完成，无异常或缺失案例，candidate 与 ADS 的各个原始数组均精确重复。
[独立复核](../results/channel-native-physical-reference-v3-20260909/verification.json)覆盖
28,672 个时域配对点、7,182 个频域配对点、6,954,946 个 ADS 原始时间点和原 98 项 gates。
各案例 candidate 数组与上一轮 v2 参考时的数组逐位相同；本轮没有修改或重建 Rust candidate。

总结果仍是 **1 例通过、6 例失败，acceptance=false**。所有原负载电压频域和 AC 材料自检通过，
42 个声明 DSP 重建诊断也通过；这些不代替原 TD gate。
`lossy-metallic` 的 TD 最大差却从约 0.058864 V 扩大为 **1.074950948 V**。
该失败完整保留，不把 v3 称为有损 Transient 已校准，也不能把全部差异单独归于 SIPI。

继续导出 ADS 自身的 `ImpSaveSpectrum`，分别读取原频域响应 `LINE_OR`、实际用于卷积的
`LINE_FFT_IMP` 与 impulse。该导出用途由
[Keysight Transient/Convolution 文档](https://edadownload.software.keysight.com/eedl/ads/2011/pdf/cktsimtrans.pdf)
及本机 2026 Update1 的 `Transient_Simulation_Parameters.html` 共同核对。

研究控制只把 StopTime 固定到第一条源边沿之前的 100 ps，以检查元件表征；原电路、源定义、
严格求解参数和解析材料保持不变。它不是原始时间窗口的 TD 验收，不回填 SIPI kernel。
三个控制各重复两次，共 6 份 dataset、300 张表完成 SDK 重导出和全数组重复核对，
16 个元件复数分量共 8,454,144 个同频配对点全部重算。

| ADS 卷积表征 | 原谱与实际谱最大复数差 | 0-64 GHz 最大差 |
| --- | ---: | ---: |
| 自适应，日志为 8 GHz 间隔 | 0.962616 | 0.962616 |
| 显式 125 MHz，4.096 THz 上限 | 0.00247171 | 0.000902645 |
| 同上，`ImpMaxPts=65536` | 0.00247171 | 0.000902645 |

- [自适应/显式间隔原始记录](../results/channel-ads-convolution-probe-20260909/characterization/result.json)与
  [逐点复核](../results/channel-ads-convolution-probe-20260909/characterization/verification-final.json)
- [响应长度上限控制](../results/channel-ads-convolution-probe-20260909/declared-order/result.json)与
  [逐点复核](../results/channel-ads-convolution-probe-20260909/declared-order/verification.json)
- [实际频谱/impulse 图](../results/channel-ads-convolution-probe-20260909/figures/convolution-spectrum.png)与
  [图及跨控制数组核对](../results/channel-ads-convolution-probe-20260909/figures/manifest.json)

例如元件 `(1;3)` 的自适应 impulse 峰值在约 18.425 ps，而显式间隔控制约为 231.556 ps。
自适应频谱在约 2 GHz 处即有约 0.963 的复数差，不能用原 AC 网格通过掩盖。
显式间隔大幅降低误差，但仍未达到原严格门限，不能据此宣布正确。
日志提示 `ImpMaxPts` 上限后另做了足额阶数控制；其全部 111 个导出数组与原显式间隔控制
逐位相同，故增加该上限没有修复剩余误差。没有因该警告继续盲扫或放宽门限。

本轮确认了**参考端导出原谱与卷积核谱的差异**；它本身不足以把实际 TD 误差唯一定位到
频域转卷积构造，离散基函数、时域求值和积分的影响仍需单独检查，也不认定内部算法根因。
下一步先验证该卷积模型对原频域的保持程度及低频/长尾收敛，再做完整有损 TD。
SIPI 的有限带宽/截尾/启动合同问题仍开放；网络/Touchstone、EQ/CDR、B6-B7 也不因本轮诊断被取消。

此次 Python 定向回归为 bench 11 项、参考控制 2 项、时域研究控制 2 项，均在 ADS Python 下通过。
旧 v1/v2 的各 14 次完整结果仍通过新增版本一致性检查，数值失败状态保持：
[v1](../results/channel-native-v1-reverified-reference-version-20260909.json)、
[v2](../results/channel-native-v2-reverified-reference-version-20260909.json)。
完整 v3 报告的 14 张实际图、143 个链接、98 行 gates 在 1440x1000 与 390x844
[通过 Playwright 检查](../results/channel-native-physical-reference-v3-20260909/visual/visual-verification.json)，
截图和卷积诊断图已目检，无空白图或页面横向溢出。后续报告生成器另明确标注 AC 控制不代表
Transient 资格；冻结的本次报告没有覆盖重写。本轮未重跑 Rust 全套测试，未提交或推送。

### 原始频率键与两端口控制

继续只在 SIPI 仓库内推进。新工具
[diagnose_channel_ads_convolution.py](../tools/diagnose_channel_ads_convolution.py)
已将卷积表征、全矩阵诊断、原频率逐点 CSV 和独立复核接入可重复的命令行。
沿用标准 v3 计划中的 `lossy-metallic`，不启动 candidate，不替代全七例 TD 矩阵。

[fresh 实跑结果](../results/channel-ads-convolution-diagnostic-20260909/result.json)包含
三组设置各两次，共六次完整 ADS 运行；
[SDK 独立复核](../results/channel-ads-convolution-diagnostic-20260909/verification.json)
确认所有原始数组精确重复、全部网表和 CSV 可重建，21,037,056 个全频域分量配对点均重算。
**三组数值均失败，acceptance=false。** 原误差门限仍为 `1e-9 + 1e-8*abs(reference)`。

| 原生 TL 设置 | 全 ADS 频率网格最大差 | 原 513 个频率键最大差 | 原网格结果 |
| --- | ---: | ---: | --- |
| 自适应 | 0.962616 | 不计算 | 仅 DC 键精确存在，其余 512 个键缺失 |
| 125 MHz / 4.096 THz | 0.00247171 | 0.000728617 | 每分量 512/513 点超差 |
| 31.25 MHz / 4.096 THz | 0.00247178 | 0.0000293875 | 每分量 512/513 点超差 |

六次运行的原网格要求 49,248 个分量配对点，32,864 个键精确存在，16,384 个缺失；
缺失行全部留在 CSV 中，没有用最近频率、插值或点数缩减得到通过结论。
两组显式间隔在同一原始网格上的全部 8,208 个原谱值逐位相同，故误差降低不是换了输入模型。
但高频段剩余误差基本重合，继续只减小频率间隔不足以证明全带宽收敛。
[共享键复核记录](../results/channel-ads-convolution-probe-20260909/shared-key-audit/result.json)与
[实际误差曲线](../results/channel-ads-convolution-probe-20260909/shared-key-audit/shared-grid-error.png)
同时保留旧四组表征的 SDK 复核、原键全矩阵 CSV 和源码快照；图已目检，无空白或标签重叠。
对数图仅将零误差显示在 `1e-16` 下限，门限计算与 CSV 原值未改。

另做了代数等价的两端口表示控制：从同一声明材料的 ABCD 方程直接给 ADS 原生 `S_Port`，
显式 `Z[1]=Z[2]=100 Ohm`，没有输入 SIPI 传递函数、kernel 或拟合参数。
该控制仍仅表征源边沿前 100 ps，并保留两次独立运行，未替换主 bench 的原生 TL。

- 两端口 raw loaded AC/DC 的 513 个原始点全部通过，最大差 `5.63603e-15`。
- 四个 ADS 原谱分量与独立解析 S2 的全部 131,072 个频率键逐点一致到原门限，两次共 1,048,576 点；最大差 `1.36214e-14`。
- 同一实际卷积频谱仍未合格：全频最大差约 `0.00174599`，原 513 键最大差约 `0.00139796`，每个分量仍为 512 点超差。

这表明两端口表示能通过此次 AC/DC 控制，但没有解决卷积构造误差；不能宣称其 TD 已校准。
原生 TL 的 raw DC 最大偏差约 `9.99905e-7` 也被新工具单独保留，不再与独立 DC 控制混淆。
两端口首轮误用 schematic 名称 `S2P_Eqn` 的网表解析失败保存在
`results/channel-ads-convolution-probe-20260909/two-port-equations/`，没有作为数值结果；
按本机 ADS 输入语法文档改用 `S_Port` 后，在新的 `two-port-native/` 目录重新执行。

定向回归共 21 项通过，包含六个新增测试：全矩阵、末点失败、仅差 1 ULP 的缺失键、
原 DC 偏差、非有限值、旧参考/错误输入、缺失重复，以及网表/CSV 篡改拒绝。
真实六次 ADS 运行与 SDK 重导出独立于这些合成单元测试。没有改动或重建 Rust candidate，
也没有重跑完整有损 TD。下一步区分带宽限制与卷积构造的剩余误差，再恢复完整 TD 对照；
SIPI 的物理启动/带宽合同、Touchstone/级联、EQ/CDR、B6-B7 和可用界面仍全部开放。

### 带宽隔离与精确时域控制

本轮先完成有界带宽控制，再停止继续扫描卷积黑盒参数。新增两组均固定原电路、125 MHz
间隔、源定义、100 ps 表征窗口和原比较门限，仅把表征上限从 4.096 THz 加倍。
执行日志确认实际表征到 8.192 / 16.384 THz，并保留 undersampled 告警。

| 表征上限，间隔均为 125 MHz | 原 513 键最大复数差 | 原键 32-64 GHz 最大差 |
| --- | ---: | ---: |
| 4.096 THz | 7.286166575e-4 | 2.952015321e-5 |
| 8.192 THz | 7.286166580e-4 | 1.487785414e-5 |
| 16.384 THz | 7.286166581e-4 | 7.533195077e-6 |

[四次完整运行](../results/channel-ads-convolution-bandwidth-20260909/result.json)的
[SDK 复核](../results/channel-ads-convolution-bandwidth-20260909/verification.json)
覆盖 25,165,824 个全频谱分量配对点与全部 32,832 个原网格配对点，所有数组精确重复。
与原组相比，16 个分量的全部原始频率键及原谱值逐位相同。
高频残差降低，但低频主误差仍在，完整原门限均失败，`acceptance=false`。
上述子频带只是定位信息，未替代完整 gate，也未把带宽不断增大作为后续验收策略。

重新核对旧台账及
[Keysight 2011 卷积手册第 23-24 页](https://edadownload.software.keysight.com/eedl/ads/2011/pdf/cktsimtrans.pdf)
后，明确纠正此前过强的归因：`OR` 与 `FFT_IMP` 的差异是导出物诊断，不能未经独立时域
检查就当作实际模拟 H 的误差。手册也把 `ImpMaxPts`、旧 PWL Continuous 等列为 obsolete；
冻结配置继续可复核，但不再把这些旧开关当成有效的现代调参路线。

随后新增五个 **ADS-only 已知因果控制**：原生集总 RC、直通、137.5 ps 分数延迟、
20 ps 单极点，以及分数延迟加单极点。后四例通过原生 `S_Port` 声明
`S11=S22=0`、`S12=S21=exp(-s*delay)/(1+s*tau)`，参考阻抗均为 100 Ohm。
原生 RC 使用 100 Ohm 源和负载、0.4 pF 电容，产生相同的 20 ps 加载时间常数。
比较输出传递函数，不声称该集总 RC 与匹配两端口具有相同输入阻抗或完整网络矩阵。

五例均保留同一 64-bit 显式源、原有限边沿和固定四 UI 零前史，分别两次 fresh 执行，
没有通过更改时域观察点、对齐、缩放或回填候选来匹配。
[十次完整记录](../results/channel-ads-primitives-20260909/fixed-frequency-complete/result.json)及
[独立复核](../results/channel-ads-primitives-20260909/native-time-audit/primitive-verification.json)
覆盖 5,130 个 AC 点、10,240 个原观察点。另对全部 **507,110 个 ADS 原生时间点**
直接计算精确有限 ramp 响应，包括原四 UI 前史；
[全原生时点 CSV 与门限](../results/channel-ads-primitives-20260909/native-time-audit/result.json)独立保留。

| 控制，repeat-1 | 原 1024 点最大电压差 | 全 ADS 原生时点最大差 | 原门限 |
| --- | ---: | ---: | --- |
| 原生 RC | 2.21193e-9 V | 2.21228e-9 V | passed |
| 直通 | 0 V | 7.71939e-13 V | passed |
| 分数延迟 | 0 V | 4.06120e-13 V | passed |
| 方程两端口 RC | 2.28331e-6 V | 2.28331e-6 V | failed |
| 方程两端口分数延迟 + RC | 4.30212e-6 V | 1.35649e-4 V | failed |

全部 AC 和源交付检查通过，最大 AC 误差不超过 `3.34222e-16`。
两个方程 RC 案例分别有 427/1024、413/1024 个原观察点超差；全部原生时点又暴露了更大的
边沿附近偏差。所有控制均未导出 `OR/FFT_IMP/IMP` 表，记录为未导出而非频谱通过；
本轮不能据此声称已经复现或解释此前有损线的内部卷积路径。
这组证据直接表明：AC 一致和相同控制器设置不保证两种参考表示的瞬态误差同样小。
它仍不是对 ADS 内部算法的根因结论，也不关闭 SIPI 的 B0/B1 或完整 Channel 任务。

首次控制因错误地要求分数延迟必须导出核谱而中止，保存在
`results/channel-ads-primitives-20260909/fixed-frequency/`；未覆盖或补写为完整。
修正只分离“无导出”和“数值通过”，随后重新完成全部五例双重复。
误差图 [control-errors.png](../results/channel-ads-primitives-20260909/native-time-audit/control-errors.png)
由实际全原生时点与原频率键生成，已目检，无空白或标签重叠。

诊断工具只新增两个显式带宽配置，并将元件谱检查与加载 AC 检查分开复用；
默认三组不变，21 项定向回归通过，旧六次和新四次卷积记录均在该重构后重新复算一致。
本轮没有修改 Rust 数值内核，没有运行原完整有损 TD，也没有把这些参考检查替代产品交付。
下一步以已知解析控制检查时域步长收敛，保持原门限，再回到 SIPI 的共同物理合同和原完整 bench。

### 时间步长收敛记录

上述五个已知因果控制已完成 `dt/16`、`dt/64`、`dt/256`、`dt/1024` 四档双重复研究。
`dt=1.953125 ps`。独立审计重新检查全部 40 份 dataset、SDK 导出、CSV 和实际执行网表，
确认仅 `MaxTimeStep` 不同；电路、码型、有限 ramp、四 UI 前史、AC 网格和门限均保持原值。
每例原始 AC 与原观察键上的源数组跨四档逐位一致，重复运行的全部导出数组精确相同。

[收敛审计](../results/channel-ads-primitives-20260909/integration-convergence/result.json)覆盖
40,960 个原始观察点和 **15,591,006 个全部原生时间点**，各档校验单独保留。
旧 `dt/16` 记录没有被改写：审计另行对其全部原生时点补算相同门限。

| 方程分数延迟 + RC，repeat-1 | 原 1024 点最大差 | 全原生时点最大差 | 全原生点最坏误差/门限 |
| --- | ---: | ---: | ---: |
| dt/16 | 4.30212e-6 V | 1.35649e-4 V | 3374.86 |
| dt/64 | 3.99417e-7 V | 2.00295e-5 V | 499.76 |
| dt/256 | 1.69653e-8 V | 5.36784e-7 V | 13.40 |
| dt/1024 | 1.56055e-9 V | 7.83638e-8 V | 1.96 |

五例在 `dt/256`、`dt/1024` 的原观察键均通过，但分数延迟加 RC 的原生时点仍有超差。
最细档每次运行 1,115,268 个此例原生点中仍有 2,432 个失败，
`finest_controls_passed=false`。不丢弃这些点，不改变 `2e-8 + 1e-7*abs(reference)` 门限。
原生 RC、直通、纯延迟通过全部四档；方程 RC 在后两档通过全部原生时点。
这些结论仅涉及已知解析控制，不能外推为有损线参考已经准确，也不能关闭 SIPI 时域验收。

[收敛图](../results/channel-ads-primitives-20260909/integration-convergence/time-step-convergence.png)
分开展示原始观察键和全部原生时点的最坏误差比，已目检，无空白或标签重叠。
流式 CSV 复核避免将上千万行先复制为 Python 对象列表；四项测试覆盖只改最大步长、
观察键之间漏检、短/多/损坏 CSV，以及明确拒绝 `python -O`。它们是合成测试，不是 fresh ADS。

本阶段到固定四档研究为止，不继续加档扫描，不将参考诊断当作产品交付。已恢复 SIPI
统一入口的离线全时段浏览工作，详见[原生工作流](channel-native-workflow.md#离线报告全时段浏览验证)。
更新后的校验器已复核旧 v3 全七例 14 次运行，原 TD/kernel 失败保持失败；新报告的单例
ADS 双重复 smoke 仅检查工件/入口连接。共同物理启动合同、Touchstone/级联、完整 EQ/CDR
及 B6-B7 均继续开放，整体目标仍未完成。

## 本地 Release `sipi.exe` 候选绑定与实跑复核

2026-09-09。完成多通道串扰、实测 TX 脉冲、接收机均衡网格扫描与 IBIS-AMI 运行时接入后，在 release 模式下重新编译本仓库实际 `sipi.exe`。
运行 `tools/run_channel_native_ads_bench.py` 驱动 Keysight ADS 2026 Update1 求解器（`hpeesofsim.exe`）执行 6 例物理/解析案例（双重复，共 12 次完整 ADS 运行）：
- 结果工件保存在 `results/channel-native-ads-candidate-20260909/`
- 通过 `tools/verify_channel_native_ads_bench.py` 执行 Keysight 原生数据集 SDK 逐点复核，输出 `results/channel-native-ads-candidate-20260909-verification.json`，12 次运行全部完成并通过完整性校验。
- `matched-native-grid` 时域 1024 个配对点全过，最大误差仅 $4.700023 \times 10^{-8}\,\text{V}$，频域负载电压最大误差 $5.013034 \times 10^{-11}\,\text{V/V}$。
- 其余电容与 legacy 网格案例严格记录由于采样裁切和连续时间卷积差异引起的点对点残差，保持 `acceptance: false`，不因部分通过而伪造全线通过。
