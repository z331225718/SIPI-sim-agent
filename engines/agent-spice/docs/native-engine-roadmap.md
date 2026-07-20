# Agent-Spice 自主仿真内核路线

## 目标

Agent-Spice 最终拥有由本项目控制的 SPICE 兼容仿真内核，而不是把 ngspice 作为运行时核心。ngspice 保留为差分回归 oracle 和迁移期后端，不作为新内核的实现来源或隐藏依赖。

## 2026-07-16 路线修正

- 主实现语言从 C# NativeAOT 改为 Rust；新内核位于 `native/agent-spice-sim`。C# 引擎不删除，作为已经跑通的算法参考和迁移期差分 oracle。
- 产品目标收缩为 PI/SI 必需的 `OP/DC/AC/TRAN`、线性 RLC/独立源/受控源、层级网表和 RFM N-port。二极管、BJT、MOS 等器件模型停止扩面，待 PI/SI 主路径完成后再评估。
- Rust 垂直切片已覆盖 R/C/L/V/I、E/F/G/H、嵌套参数化 `.subckt`、`.global`、递归 include、外部 `.lib` section、表达式参数、PULSE/PWL、实数/复数稀疏 LU，以及 OP/DC/AC/TRAN。
- TRAN 已完成 BE 启动/断点重启、Trap、变步长 Gear2，以及基于电容电荷、电感磁链和 RFM 动态输出的 LTE 接受/拒绝控制。拒步只提交候选状态，RLC 历史与 RFM 有理状态可完整回滚；严格 `reltol=1e-5 trtol=1` 门禁会真实拒步 8 次，输出网格不漂移，回滚后相对默认门禁最大波形变化约 `1.18 uV`。
- Rust 已原生解析 `VERSION 200600` RFM，完成 S-to-Y OP/DC/AC、稀疏 Trap/Gear2 状态空间 TRAN 和直接 JSON/CSV 输出。RFM 伴随逆矩阵按非零行压缩，步长核通过共享不可变对象复用。
- Python `run-rfm` 与 `run-hspice` 现在都以 Rust native 为默认路径；`run-hspice --backend native` 直接审计并执行 HSPICE case，不再经过 `.inc/.probe/.option post` 方言转换。ngspice/HSPICE 仅在显式选择时作为 oracle，不做静默回退。Windows 平台 wheel 已在无运行时依赖的干净 venv 中实跑包内 Rust 可执行文件。
- Rust 已原生执行 HSPICE `.measure` 的 `FIND ... AT/WHEN`、独立 `WHEN`、`TRIG/TARG`、`TRIG AT`、`MIN/MAX/AVG/RMS` 和 `FROM/TO` 窗口，事件选择覆盖 `TD`、编号 `RISE/FALL/CROSS` 与 `LAST`。结果进入 `native_result.json` 和 `run_summary.json`；PI 与事件签核脚本直接比较 Rust/HSPICE 各自执行同一组 `.measure` 的结果，不再由 Python 从 Rust 波形重算。
- `.measure PARAM` 已按 HSPICE 顺序依赖语义进入 Rust：可引用先前测量、普通 `.param`、SI 后缀和现有数学函数，支持紧凑及带空格等号写法；前向引用、未知名称和大小写无关的重复测量名会显式报错。
- `.measure DERIV ... AT/WHEN` 与 `INTEG ... FROM/TO` 已复用原生测量采样、事件定位和窗口边界插值；线性斜坡与三角波门禁相对 HSPICE 的导数误差约 `2.4e-7`（相对 `2.4e-16`），积分误差低于 `1e-24`。
- 本机 PrimeSim HSPICE `T-2022.06-1` 已通过许可证实跑。`rust_linear_pi.sp` 的 Rust/HSPICE 差分中，DC 电压绝对误差约 `1.1e-16 V`，1 MHz AC 幅值/相位误差约 `3.2e-8/4.2e-5 deg`，5 ns TRAN 最低电压误差约 `0.064 uV`。
- E/F/G/H 已通过 HSPICE 的 DC/AC/TRAN 共 12 项差分，全部数值一致。RFM 展开状态网络的 HSPICE 门禁也已通过：DC/AC 幅相误差分别约 `1.9e-8 V`、`3.5e-8 V`、`1.6e-6 deg`，五个 TRAN 采样点最大误差约 `0.61 mV`。报告位于 `artifacts/rust-hspice-controlled-final/report.json` 与 `artifacts/rust-hspice-rfm-final/report.json`。
- 5 轮进程级 RFM 门禁中，2/8/16-port Trap 为 ngspice 的 `0.52x/0.51x/0.38x`，Gear2 为 `0.56x/0.56x/0.42x`；波形 RMS 差约 `0.039/0.045 mV`。81/289/1089 阶 RLC PDN TRAN 为 `0.69x/0.76x/0.56x`。AC 频点按最多四个工作线程分块并各自复用符号分解后，同一网格为 `0.69x/0.80x/0.68x`，2050 阶梯形网络约 `1.00x`；当前 PI/SI 四类分析已全部进入同等效率区间。
- Windows/Linux/macOS 的 Rust wheel 构建矩阵已替换旧 C# NativeAOT 主路径；Windows x64 本机已签核，其他平台仍以 CI 首次实跑为发布条件。签名、SBOM、哈希清单和 HSPICE `.measure` 的信号对信号事件比较、优化限定符等高阶语义仍待收口。

## 当前判断

- 现有代码主要是 Python 编排层，`NgspiceBackend` 通过外部进程执行网表；仓库没有 ngspice 源码树。
- 直接“翻译整个 ngspice”不是可验收的第一步。正确的路径是先建立独立的电路 IR、求解器契约和小型可运行内核，再按真实 PI/HSPICE 语料扩展兼容面。
- C# 第一阶段已经证明自主 MNA/RFM 路径可行；当前开发机现已安装固定版本 Rust 1.97.0，后续产品化实现转入 Rust，并以 HSPICE 为 PI/SI 首要兼容性 oracle。

## 历史 C# 迁移基线

`native/AgentSpice.Engine` 当前覆盖：

- R、C、L、独立 V/I 源和 E/F/G/H 四类线性受控源；
- 续行、递归 `.include`/`.inc`、带 section 选择的外部 `.lib`、相对路径与依赖循环诊断、`.param` 数值表达式、前向引用/循环检测、`.global`、嵌套 `.subckt`、实例参数覆盖、局部模型隔离及层级节点/器件重命名；
- Level-1 二极管的实例 `AREA/M/TEMP/DTEMP` 与位置式面积、模型 `IS/N/RS/BV/IBV/NBV/TNOM/EG/XTI/AREA/CJO/VJ/M/TT/FC`、面积缩放内部串阻、温度化电流/结电荷、反向击穿、结电压限幅、完整 MNA 残差判据、回溯线搜索、OP/DC warm start、AC 增量导纳和 Trap/Gear2 TRAN；
- NPN/PNP BJT 的实例 `AREA/M/TEMP/DTEMP` 与位置式面积、模型 `IS/BF/BR/NF/NR/VAF/VAR/IKF/IKR/RC/RB/RE/TNOM/EG/XTI/XTB`，以及 `CJE/VJE/MJE/CJC/VJC/MJC/TF/TR/FC` 三端守恒电荷模型；覆盖面积缩放三端内部串阻、温度化电流/电荷、高注入基区电荷、解析电流/电荷 Jacobian、双结电压限制、OP/DC warm start、AC 小信号和 Trap/变步长 Gear2 TRAN；
- 四端 NMOS/PMOS Level-1 Shichman-Hodges 模型，覆盖 `VTO/KP/GAMMA/PHI/LAMBDA/LD/RD/RS/RSH/TOX/UO/TNOM/NSUB/TPG/NSS/IS/JS/PB/CBD/CBS/CJ/MJ/CJSW/MJSW/CGSO/CGDO/CGBO/FC`、实例 `L/W/AD/AS/PD/PS/NRD/NRS/M/TEMP/DTEMP`、全局 `.temp`/`.options temp/tnom`、按 `M` 缩放的漏源内部串联电阻节点、衬底参数推导、正反向沟道、体效应、体二极管、温度缩放、Meyer 本征沟道/重叠/结电荷、解析自动微分 Jacobian、AC 和 Trap/变步长 Gear2 TRAN；
- `.op`、`.dc`、`.ac`、`.tran`；
- MNA 组装、稠密/稀疏 LU 自动选择、稳定性约束下的 Markowitz 稀疏选主元、可复用的行置换/结构性 fill 与压缩数值重分解、失稳主元自动回退、Trap/变步长 Gear2 companion model、PULSE/PWL/SIN/EXP 统一瞬态源、源断点与不连续事件调度、历史解 Newton 预测器，以及基于器件 charge/flux 分差的 LTE 接受/拒绝控制；
- `VERSION 200600` RFM 原生解析、S-to-Y DC/AC stamp，以及在 MNA 外消元的 Trap/变步长 Gear2 N-port 状态空间 TRAN；
- 现有 `X... rfm_direct` 网表绑定和 `agent-spice run-rfm --backend native`；
- framework-dependent runtime 已进入 wheel package-data，并通过干净 venv 安装执行 smoke；
- Windows x64 NativeAOT 可执行文件已进入 `py3-none-win_amd64` 平台 wheel，并在没有可用 `dotnet` 命令的干净 venv 中执行通过；
- `run-rfm` 已默认选择 native 后端；ngspice XSPICE 仅在显式 `--backend ngspice` 时作为 oracle 执行，不做静默回退；
- NativeAOT/wheel 脚本已覆盖 Windows、Linux、macOS 的 x64/ARM64 RID，并加入 Windows x64、Linux x64、macOS x64/ARM64 CI 构建与包内可执行文件 smoke；除 Windows x64 外仍以 CI 首次实跑结果为签核条件；
- RFM TRAN 复用 MNA 分解、按积分系数缓存的 companion kernel 和拓扑索引；状态按实际存在的 `(pole,input)` mode 分配，response-specific 极点不再扩展为 `N x global-pole-set`，历史卷积按密度自适应选择稀疏留数项或小型稠密矩阵乘法；有理状态保留三层接受历史，动态端口响应进入可回滚的 LTE 自适应步长；
- 大型 PWL/PWLFILE 的插值和重复断点调度使用二分定位，瞬态开始前预编译动态源列表；查询成本不再随已越过的 PWL 行数增长；
- 引擎可直接写 `native_result.json` 和 `waveform.csv`，Python 编排层不再反序列化并重写完整波形；
- SI 后缀解析和机器可读 JSON 结果。

二极管 OP/DC 曲线、面积/倍乘、面积缩放 `RS`、全局/模型/实例温度、`BV/IBV/NBV` 反向击穿、含结电容/扩散电容的 AC 小信号、动态钳位和 Trap/Gear2 反向恢复 TRAN 已与真实 ngspice 差分。三种温度来源与模型缺省面积的 OP 电流相对差不超过 `7.4e-6`；导通区串阻 DC 相对差不超过 `6.1e-6`，击穿区 DC 不超过 `1.6e-5`；100°C AC 归一化最大复数差低于 `1.9e-7`，TRAN 输出 RMS/最大差约 `0.28/1.59 mV`。动态钳位预测器把 Newton 总迭代从 `764` 降到 `647`（约 `15%`），最大波形变化仅 `1.72e-11 V`。Trap 反向恢复的 `0.5/0/-0.5 V` 换向时刻与 ngspice 在 `0.25 ns` 内，Gear2 在 `0.30 ns` 内。`PULSE` 的零上升/下降时间已按 ngspice 语义使用 `.tran TSTEP`，对应 RC 波形 RMS 误差约 `0.33 mV`。

`scripts/benchmark_native_diode_engine.py` 固化 13 组 Windows x64 NativeAOT 进程级门禁。31 次中位数中，全部场景为 ngspice 的 `0.923x` 到 `1.108x`，中位比值 `0.993x`；面积串阻 DC 为 `1.108x`，击穿 DC/带串阻击穿 OP 为 `0.923/0.975x`，温度 OP/AC/TRAN 为 `1.048/1.047/1.049x`。完整报告位于 `artifacts/benchmark-native-diode-complete-final-31/report.json`。当前二极管静态、串阻、击穿、温度、频域和动态核心都处于 ngspice 同等效率区间。

BJT 的 NPN/PNP 工作点、Early 效应、面积/倍乘、`RC/RB/RE`、`IKF/IKR` 高注入、全局/模型/实例温度、`1 kHz` 到 `1 GHz` 动态 AC，以及 Trap/Gear2 NPN 与 Trap PNP 开关 TRAN 已与真实 ngspice 差分。温度 OP 八路源电流相对差不超过 `8.9e-6`，高注入 DC 导通区相对差不超过约 `1.5e-5`，100°C AC 归一化最大复数差约 `1.1e-5`，100°C TRAN 输出 RMS/最大差约 `28.0/57.4 mV`。三端电荷及其完整非互易 Jacobian 保持电荷守恒，瞬态历史支持快照、拒绝和回滚；理想源支路电流不再误入 LTE 状态集合，Trap NPN 从 `1091` 个接受步降至 `222` 个，ngspice 对应输出 `236` 个自适应点。开关波形的集电极电压 RMS 差异为 Trap NPN `11.4 mV`、Gear2 NPN `15.6 mV`、Trap PNP `11.8 mV`。

`scripts/benchmark_native_bjt_engine.py` 固化 14 组 Windows x64 NativeAOT 进程级门禁。31 次中位数中，全部场景为 ngspice 的 `0.940x` 到 `1.128x`，中位比值 `0.981x`；三端串阻 DC 为 `1.054x`，高注入 DC 为 `0.981x`，温度 OP/AC/TRAN 为 `0.970/0.940/1.033x`。完整报告位于 `artifacts/benchmark-native-bjt-complete-final-31/report.json`。当前 BJT 静态、串阻、高注入、温度、频域和动态核心都处于 ngspice 同等效率区间。

MOS1 门禁覆盖带体效应的 NMOS OP、NMOS/PMOS DC、互补 CMOS 反相器 DC、直接/片电阻 DC、重叠/结电容 AC、NMOS/PMOS/反向区 Meyer AC、全局/模型/实例温度、衬底参数推导、NMOS Trap/Gear2 开关、Meyer TRAN 和互补 CMOS TRAN。串联电阻两组漏源电流相对 ngspice 最大差约 `2.4e-5`；三组 Meyer AC 归一化最大复数差不超过 `2.0e-6`。三种温度来源的 OP 电流相对差约 `0.7e-6` 到 `1.6e-6`，衬底推导 NMOS/PMOS 四路电流相对差约 `0.14e-6` 到 `1.42e-6`，125°C AC 归一化最大复数差低于 `3.5e-7`，100°C TRAN 输出 RMS/最大差约 `9.1/54.8 mV`。常温 Meyer TRAN 输出 RMS/最大差约 `9.0/63.7 mV`，栅极电流 RMS/最大差约 `0.134/1.66 mA`。原有 CMOS DC 输出最大差约 `0.5 uV`；NMOS Trap/Gear2 输出 RMS 差约 `12.8/7.0 mV`，最大差约 `47.2/23.5 mV`；CMOS TRAN 输出 RMS/最大差约 `1.8/14.5 mV`。动态四端电荷参与同一套快照、拒绝、回滚和器件 LTE，不把栅极理想源电流误当作状态。

`scripts/benchmark_native_mos1_engine.py` 固化 18 组 Windows x64 NativeAOT 进程级门禁。31 次中位数中，全部场景为 ngspice 的 `0.921x` 到 `1.320x`，中位比值 `1.034x`；衬底推导 OP 为 `0.951x`，温度 OP/AC/TRAN 为 `0.956/1.076/1.267x`，常温 Meyer TRAN 为 `1.159x`。完整报告位于 `artifacts/benchmark-native-mos1-complete-final-31/report.json`。当前 MOS1 静态、串联电阻、衬底推导、温度、频域和动态核心都处于 ngspice 同等效率区间。

BJT 的 `ISE/ISC/NE/NC` 复合泄漏、`RBM/IRB` 基极电阻调制、基集电容外部分配、过渡时间偏置、高频 excess phase、衬底结和噪声参数仍待实现；二极管 sidewall/高注入/隧穿/噪声与温度系数、MOS1 噪声参数与更高阶模型尚未实现，这些参数会显式报错。当前仍不宣称已经达到 ngspice 的完整器件、成熟稀疏重排序和全部收敛控制能力。

层级网表和受控源已用真实 ngspice 覆盖 OP/DC/AC/TRAN。门禁同时包含全局/局部参数、数学表达式、两层 X 实例、实例覆盖、`.global` 节点、每实例局部二极管模型及 E/F/G/H 支路。31 次 NativeAOT 进程级中位数中，受控源 OP/DC/AC/TRAN 为 `19.647/19.491/18.653/19.198 ms`，ngspice 为 `20.363/20.316/19.733/20.384 ms`；参数化嵌套子电路为 `19.088/19.842/19.368/19.980 ms`，ngspice 为 `20.063/20.107/20.780/20.646 ms`。八组门禁均未牺牲端到端效率，AOT 内部解析加仿真约 `0.8 ms`。

递归 include/lib 门禁覆盖“顶层 -> 参数 include -> 子电路相对 include”以及外部库 section 选择，并对缺文件、缺 section、依赖循环和依赖文件中的 `.end` 给出显式诊断。PWL 覆盖线性插值和重复时间点的右连续跳变，SIN/EXP 覆盖延迟、阻尼与双时间常数；每个事件都会钳住步长并正确重启 Trap/Gear 历史。与 ngspice 的输出波形差分中，PWL、SIN、EXP 的 RMS 分别约为 `0.334/1.433/1.018 mV`，最大差分别约为 `1.257/2.867/4.073 mV`。31 次 NativeAOT 进程级中位数中，include/lib、PWL Trap、PWL Gear2、SIN、EXP 分别为 `22.110/21.710/23.010/21.870/21.930 ms`，ngspice 为 `24.090/23.210/23.390/23.140/22.210 ms`，五组端到端门禁均未牺牲效率。

## RFM 性能基线

基准命令由 `scripts/benchmark_native_rfm_engine.py` 固化，使用同一份 6 阶 RFM、同一网表和真实 ngspice XSPICE code model。Trap/Gear2 都启用 RFM 状态 LTE；每个进程包含解析、仿真、结果落盘和波形 CSV 生成，报告排除预热轮次。

| 场景 | native 中位数 | ngspice 中位数 | native/ngspice |
|---|---:|---:|---:|
| 2 port, Trap, 2k 点 | 0.035 s | 0.044 s | 0.79 |
| 8 port, Trap, 2k 点 | 0.046 s | 0.054 s | 0.84 |
| 16 port, Trap, 2k 点 | 0.070 s | 0.092 s | 0.76 |
| 2 port, Gear2, 2k 点 | 0.036 s | 0.045 s | 0.80 |
| 8 port, Gear2, 2k 点 | 0.047 s | 0.056 s | 0.85 |
| 16 port, Gear2, 2k 点 | 0.075 s | 0.092 s | 0.82 |

严格 `reltol=1e-5/trtol=1` 的 Gear2 动态源门禁会真实触发拒步与状态回滚；相对 ngspice 展开状态宏模型，2 ns 输出波形 RMS/最大差约 `5.73/14.66 uV`。31 轮性能完整报告位于 `artifacts/benchmark-native-rfm-gear2-lte-final-31/report.json`，六组进程级中位比值为 `0.760x` 到 `0.852x`。表中 native 使用 Windows x64 NativeAOT 平台 wheel；framework-dependent DLL 保留为跨平台回退。

## 通用稀疏 MNA 基线

`scripts/benchmark_native_linear_engine.py` 生成 256/1024/4096 段电阻梯形并对照 ngspice。4098 阶矩阵只有 12291 个非零元，native 会进入稀疏 LU；解析解测试同时核对末端电压为 `1/(sections+1)`。

| 场景 | native AOT 中位数 | ngspice 中位数 | native/ngspice |
|---|---:|---:|---:|
| 258 阶单次 OP | 0.020 s | 0.023 s | 0.88 |
| 1026 阶单次 OP | 0.022 s | 0.028 s | 0.80 |
| 4098 阶单次 OP | 0.051 s | 0.055 s | 0.93 |
| 4098 阶、1001 点 DC | 0.213 s | 0.250 s | 0.85 |

通用稀疏 MNA 已通过当前线性 OP/DC 性能门禁，矩阵规模呈近线性增长且不会发生稠密内存爆炸。AC、Newton 和 TRAN 现已使用连续稀疏数值缓冲区、预编译整数 stamp 槽与可原地重填的 LU 因子对象；矩阵组装和数值分解不再为每个频点重建字典或行级小数组。

AC、Newton 和变步长 TRAN 复用首次数值稳定选主元得到的行置换与结构性 fill；后续矩阵在冻结数值槽上重新 stamp，并仅执行数值分解。首次 Markowitz 分解直接捕获实际 factor 行和主元来源来生成平坦计划，不再用 HashSet 重演一次符号消元；新拓扑分析按列邻接表访问候选行，避免逐列扫描全部后续行。求解缓存最多保留 8 个通过数值稳定性检查的计划，以覆盖变步长和非线性过程中出现的多种主元序列。

标准器件 AC 矩阵会从前两个频点编译 `G + fB` 仿射模板，后续频点直接填充连续数值缓冲区；含频率有理函数 RFM 的路径会保守禁用该模板。64 个节点以上的网表默认使用 Reverse Cuthill-McKee 节点排序，器件 stamp 使用排序后的整数索引，电压源和电感支路变量仍保持 MNA 后缀布局。若缓存主元低于当前列最大候选的稳定阈值，求解器会自动回退到完整 Markowitz 分析并加入新计划。开启/关闭复用及节点排序的复数 AC、实数 TRAN 和非线性 Newton 结果已有严格差分回归。

瞬态路径把设备历史状态改为按器件类型编译的连续数组；相同积分方法和量化步长可复用精确数值因子快照，同时共享全局符号计划。电容电荷、电感磁链、二极管电荷和 BJT 三端电荷各保留三层接受历史与变步长间隔，由一至三阶分差估计 Trap/Gear2 局部截断误差。默认路径每个候选步只求解一次，并保留完整的接受、拒绝、状态回滚、源断点和积分重启；`.options trtol`/`chgtol` 已进入解析契约。`AGENT_SPICE_NATIVE_USE_STEP_DOUBLING_LTE=1` 保留旧整步加两个半步算法，仅用于差分回归和性能对照。

候选步长仍向下量化到每倍频程 4 档，以提高数值因子快照命中率。输出采样点截短的小尾步不再缩小下一步建议；当 `.tran TSTEP` 远大于源的显式变化时间时，内部最大步长会按源特征时间收紧，避免输出网格改变物理解。零边沿 PULSE 继续使用 TSTEP 作为有效上升/下降时间，并对该过渡使用更严格的线性存储 LTE 门禁。

`scripts/benchmark_native_sparse_reuse.py` 生成 RC 梯形的 101 点 AC 扫频。下表为 31 次 Windows x64 NativeAOT 进程级中位数；“旧路径”通过 `AGENT_SPICE_NATIVE_DISABLE_SYMBOLIC_REUSE=1` 禁用结构与矩阵工作区复用。

| 场景 | native 复用 | native 旧路径 | ngspice | 复用/旧路径 | native/ngspice |
|---|---:|---:|---:|---:|---:|
| 130 阶、101 点 AC | 0.0210 s | 0.0314 s | 0.0213 s | 0.67 | 0.99 |
| 514 阶、101 点 AC | 0.0271 s | 0.0612 s | 0.0252 s | 0.44 | 1.07 |
| 2050 阶、101 点 AC | 0.0506 s | 0.1927 s | 0.0419 s | 0.26 | 1.21 |

连续矩阵/因子缓冲区、原地数值重分解、整数节点索引、预编译 stamp 槽、直接符号计划和 AC 仿射模板把 2050 阶压力场景较当前完整 Markowitz 路径加速约 `3.8x`。130 阶略快于 ngspice，514 阶差约 `7%`，2050 阶差约 `21%`；与上一轮 2050 阶的 `0.067 s` 相比又缩短约 `25%`。完整 31 次报告位于 `artifacts/benchmark-native-sparse-reuse-final-31/report.json`。

`scripts/benchmark_native_sparse_topologies.py` 进一步生成带每行电感支路、二维不规则电阻网格、分布电容和负载的真实 RLC PDN 拓扑。AC 表为 31 次 Windows x64 NativeAOT 进程级中位数，包含进程启动、网表解析、仿真和 JSON 序列化。

| 场景 | native AOT | ngspice | native/ngspice |
|---|---:|---:|---:|
| 81 阶、101 点 AC | 0.0221 s | 0.0216 s | 1.02 |
| 289 阶、101 点 AC | 0.0360 s | 0.0318 s | 1.13 |
| 1089 阶、101 点 AC | 0.1551 s | 0.1314 s | 1.18 |

真实多支路 AC 在 81 到 1089 阶范围内保持在 ngspice 的 `1.02x` 到 `1.18x`，说明通用线性稀疏核心已经达到同等效率区间。旧 step-doubling TRAN 的差距会随规模扩大；器件 LTE 替换后的同一门禁如下。

| 场景 | 器件 LTE | 旧 step-doubling | ngspice | 新/旧 | native/ngspice |
|---|---:|---:|---:|---:|---:|
| 81 阶、21 点 TRAN | 0.0243 s | 0.0259 s | 0.0212 s | 0.94 | 1.15 |
| 289 阶、21 点 TRAN | 0.0407 s | 0.0541 s | 0.0326 s | 0.75 | 1.25 |
| 1089 阶、21 点 TRAN | 0.1656 s | 0.3279 s | 0.1456 s | 0.50 | 1.14 |

32x32 网格从上一轮 ngspice 的 `2.40x` 降至 `1.14x`，且比同一版本旧 LTE 快约 `49.5%`。默认路径执行 `232` 次单求解 LTE 试步，旧路径执行 `120` 次试步但每次需要三次求解；默认与旧路径输出波形最大差约 `1.7 mV`，两者都通过 ngspice 差分门禁。AC 旧报告位于 `artifacts/benchmark-native-sparse-topologies-final-31/report.json`，新 TRAN 31 次报告位于 `artifacts/benchmark-native-device-lte-topologies-final-31/report.json`。

`scripts/benchmark_native_transient_engine.py` 固化 11 组 RC、PWL/SIN/EXP、动态二极管和 BJT Trap/Gear2 门禁。31 次中位数里，器件 LTE 相对旧路径为 `0.88x` 到 `0.99x`，相对 ngspice 为 `0.87x` 到 `1.07x`；BJT Trap 的 Newton 迭代从 `828` 降到 `396`，Gear2 从 `812` 降到 `390`。完整报告位于 `artifacts/benchmark-native-device-lte-fixtures-final-31/report.json`。

## 迁移门禁

每一层都必须同时通过：

1. 与 ngspice 的数值差分回归：节点电压、支路电流、频率/时间轴和错误分类。
2. 规模基准：运行时间、峰值内存、矩阵填充和可扩展性。
3. 兼容性报告：支持、转换、阻断的语法/器件必须可追溯。
4. 失败时不静默回退到 ngspice；是否使用 oracle 必须在运行 manifest 中显式记录。

## 后续顺序

1. 扩大真实 PI/SI HSPICE 语料，固化 unsupported 诊断与兼容矩阵，不新增器件模型。
2. 把性能门禁扩大到更高阶非规则 PDN、更多 RFM 极点和多实例层级电路，持续跟踪内存峰值与并行收益。
3. 扩展 `.measure` 的信号对信号事件比较、优化限定符与表达式函数，并把 Rust/HSPICE 双跑差分收口为统一命令。
4. 让 Windows/Linux/macOS wheel 矩阵完成首次 CI 签核，再补签名、SBOM 和哈希清单。
5. 保持二极管/BJT/MOS 扩面冻结；只有真实 PI/SI 语料证明必要时才恢复器件级工作。
