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
