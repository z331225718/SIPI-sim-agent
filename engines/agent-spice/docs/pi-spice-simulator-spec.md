# Agent-Spice PI 仿真器项目 Spec v0.1

日期：2026-06-30

## 1. 结论先行

本项目不应以“fork 一个开源 SPICE，然后直接补功能”的方式启动。PI 仿真的关键难点不在基础 Newton/MNA 求解器，而在 SPICE 前面的频域模型净化、S 参数到时域可收敛模型转换、CPM/UPM 激励挂载、以及大规模 PDN 的降阶与调度。

推荐架构是：

1. 以 Python/C++ 中间件作为项目核心资产，负责 Touchstone/CPM/HSPICE 网表处理、模型验证、降阶、仿真编排和结果后处理。
2. 后端采用双求解器适配：
   - `ngspice/libngspice`：默认嵌入式原型和中小规模后端，优势是 BSD 友好许可、共享库 API、回调控制能力强。
   - `Xyce`：大规模 PI/PDN 后端，优势是 MPI/Trilinos/KLU 并行能力和电源网格建模经验；若团队确认 GPL 纯内部使用可接受，应作为高规模生产后端重点验证。
3. S 参数瞬态能力不要依赖求解器原生支持。Ngspice 有 `.sp` 频域 S 参数分析和部分 Touchstone/xfer 能力，Xyce 有 `YLIN` 读取 Touchstone 但当前仅用于 HB；二者都不能直接替代 PI 瞬态需要的多端口 Touchstone 卷积/宏模型流水线。
4. 第一阶段使用 `scikit-rf VectorFitting` 打通 `Touchstone -> 拟合 -> 无源性强制 -> SPICE 子电路 -> ngspice/Xyce TRAN`。大规模端口网络再评估 SROPEE 的 Block SAPOR/MOR，或自研宽松许可 MOR。
5. HSPICE 网表直接仿真是 P0 兼容性需求。团队既有 PI deck 必须能作为输入进入平台，由中间件自动完成语法识别、兼容转换、后端选择、运行和结果回收；不要求用户手工改写历史网表。
6. 递归卷积是二期/三期高性能方向，不作为 MVP。它值得做，但需要深入求解器设备加载和时间步状态管理，不能阻塞第一版可用平台。

一句话决策：**基座选 Xyce + ngspice 双后端，核心自研放在 PI 中间件；MVP 用 ngspice 快速闭环，规模化用 Xyce 验证，S 参数流水线以 scikit-rf 为起点，同时把 HSPICE deck 兼容层作为平台入口的 P0 能力。**

## 2. 两份报告的综合校正

### 2.1 Gemini 报告保留的核心判断

Gemini 对 SI/PI 耦合收敛问题的根因判断是正确且重要的：

- 信号端口常以 40-50 ohm 为参考，PDN 端口实际阻抗可能是 0.1 ohm 或毫欧级。
- 如果所有端口统一用 50 ohm 参考阻抗，PDN 端口的 S 参数幅值会接近 +/-1，导致动态范围极端、矩阵病态、无源性更容易被数值噪声破坏。
- 非无源频域模型进入时域后会表现为能量自发产生、指数振荡、`time step too small` 等收敛失败。
- 因此需要多参考阻抗、DC/低频加权、无源性强制、模型降阶。

Gemini 关于 Xyce 的规模优势也成立：如果 GPL 对内部使用不是限制，Xyce 是大规模 PDN 后端的强候选。

### 2.2 本地报告需要修正的点

本地报告的总体架构判断有价值，但有几处需要校正：

- “ngspice 完全没有 S 参数能力”过度简化。Ngspice 当前手册包含 `.sp` S-parameter simulation，并且新闻记录中也提到 Touchstone 读取能力；但这些能力主要用于频域/RF 分析或有限的 xfer 使用，不等价于大规模多端口 S 参数瞬态卷积器。
- “Xyce 完全没有 Touchstone 读取”也过度简化。Xyce 维护者在 issue 中确认它可以通过 `YLIN` 读取 Touchstone，但只能用于 Harmonic Balance，不能用于 AC 或 transient。PI 瞬态仍需外部等效电路综合。
- `scikit-rf` 确实提供 VectorFitting、passivity test/enforce、SPICE subcircuit export，是 MVP 可直接使用的核心库。
- SROPEE 确实存在，是研究级 S 参数降阶和无源性强化工具，但许可证、成熟度、可维护性需要单独评估。

### 2.3 统一判断

开源求解器的“原生 S 参数能力”不应作为选型核心，因为它们都没有满足 PI 瞬态签核要求的完整能力。真正的产品壁垒在以下四层：

1. S 参数前处理：参考阻抗归一化、DC extrapolation、因果性、无源性、端口重排、带宽裁剪。
2. 有理宏模型：Vector Fitting、极点选择、低频加权、passivity enforcement、SPICE 子电路生成。
3. 大规模降阶：Block SAPOR/Krylov/端口分组/子网络切分。
4. HSPICE 兼容层：既有 deck 的语法审计、自动转换、`.alter` 展开、`.measure` 结果归一化、模型库兼容报告。
5. 求解器编排：ngspice/Xyce 后端选择、容差策略、错误恢复、波形后处理、回归基准。

## 3. 候选基座评估

| 候选 | 推荐角色 | 优点 | 硬伤 |
|---|---|---|---|
| ngspice | MVP 与嵌入式后端 | BSD 友好、libngspice API、社区活跃、KLU、XSPICE/B 源/PWL 易用 | 单机/单线程为主，大规模 PDN 性能上限较低；无完整 transient n-port Touchstone 卷积 |
| Xyce | 大规模生产后端 | MPI、Trilinos/KLU、大规模电源网格经验、适合百万级器件/无源网络 | GPLv3；Python/嵌入式 API 不如 libngspice 顺手；YLIN Touchstone 不支持 TRAN |
| Qucs/Qucs-S | 不作为基座 | GUI/教学生态，常可调用 ngspice | 本质不是更强求解器；GPL；不解决 PI 核心问题 |
| Gnucap | 不作为基座 | 插件架构漂亮 | GPL，生态和工业验证弱 |
| SPICE OPUS | 不作为基座 | 优化/脚本能力有特色 | 生态小、许可和工业路径不如 ngspice/Xyce |
| scikit-rf | S 参数中间件依赖 | BSD，Touchstone、VectorFitting、passivity、SPICE export | 不是 SPICE 求解器；大规模 MOR/工业鲁棒性仍要补 |
| SROPEE | MOR 候选/算法参考 | 面向 S 参数降阶、Block SAPOR、passivity-enforced equivalent circuit | 研究项目；许可证和工程成熟度需评估 |

## 4. 产品目标

### 4.1 MVP 目标

构建一个可脚本化的 PI 仿真平台，支持：

- 读取 PCB/package/interposer 的 Touchstone `.sNp` 文件。
- 读取团队既有 HSPICE `.sp/.cir/.inc/.lib` 网表，并在不要求用户手工改写的前提下进入仿真流程。
- 对 S 参数做基础质量检查：端口数、频率单调性、Z0、DC 覆盖、无源性、拟合误差。
- 使用 scikit-rf 生成被动强化的 SPICE 子电路。
- 读取简化 CPM/电流签名，转换为 PWL/B 源。
- 组装 PDN + decap + VRM + CPM + S 参数宏模型网表。
- 调用 ngspice 和 Xyce 后端运行 DC/AC/TRAN。
- 输出 IR drop、PDN impedance、transient droop、端口电流/电压波形和模型质量报告。

### 4.2 非目标

MVP 不做以下事项：

- 不从零实现完整 SPICE 求解器。
- 不在第一版修改 ngspice/Xyce 内核。
- 不承诺 100% 克隆 Synopsys HSPICE 的全部私有语法；MVP 优先覆盖团队 PI deck 中实际出现的语法，并对不支持项给出机器可读诊断。
- 不承诺直接读取任意厂商 CPM 私有格式；先支持团队可控的中间格式。
- 不做 GUI，先做 CLI + Python API。
- 不把递归卷积作为第一版交付。
- 不承诺 Sign-off 等级精度，先以与商业工具对齐的回归基准逐步逼近。

## 5. 总体架构

```text
Input layer
  HSPICE deck, Touchstone 1.0/2.0, SPICE netlist, CPM/current signature, VRM/decap library
        |
        v
PI middleware
  hspice.compat         HSPICE deck 审计、转换、.alter 展开、.measure 归一化
  sparam.io              Touchstone 读取、端口元数据、Z0 处理
  sparam.conditioning    renormalize、DC extrapolate、passivity/causality checks
  sparam.fitting         VectorFitting、auto_fit、passivity_enforce
  sparam.mor             SROPEE 评估或自研 MOR
  cpm.io                 CPM/UPM/CSV/PWL 解析
  deck.builder           生成 ngspice/Xyce 兼容网表
  backend.adapter        后端抽象、运行、错误分类、结果读取
  report                 模型质量、误差、波形、性能报告
        |
        v
Solver backends
  ngspice/libngspice     原型、中小规模、嵌入式回调
  Xyce                   大规模、MPI、批处理/服务器模式
        |
        v
Post-processing
  IR drop, impedance, droop, SSN, port current, pass/fail metrics
```

## 6. 模块 Spec

### 6.1 `sparam.io`

职责：

- 读取 Touchstone `.sNp`。
- 识别 Touchstone 1.0/2.0。
- 保留每端口参考阻抗、端口名称、单位、格式、频率范围。
- 支持端口映射文件，将 EM 提取端口映射到 `signal/power/ground/bump/vrm/decap` 等语义角色。

验收：

- 能读取 2/4/16/64 端口样例。
- 能识别每端口 Z0；Touchstone 2.0 的 `[Reference]` 信息不可丢失。
- 对缺 DC 点、频率不单调、端口数不匹配给出明确错误。

### 6.2 `sparam.conditioning`

职责：

- 端口重排和端口分组。
- 按端口类型做参考阻抗归一化：signal 默认 50 ohm，power/ground 可配置为 0.1/0.01 ohm。
- S/Y/Z 参数转换，用于 PDN 低阻抗场景的数值稳定性比较。
- DC extrapolation 和高频尾部处理。
- passivity、reciprocity、causality 质量检查。

验收：

- 输出模型质量 JSON：`max_singular_value`、passivity violation 频段、低频误差、拟合频段覆盖。
- 对 PDN 端口 50 ohm 参考导致的病态情况给出自动告警。
- 所有处理步骤可复现，参数写入 manifest。

### 6.3 `sparam.fitting`

职责：

- 使用 scikit-rf `VectorFitting` 进行有理拟合。
- 默认优先尝试 `auto_fit()`，复杂场景允许手动极点数配置。
- 执行 `passivity_enforce()`。
- 导出 SPICE 子电路。
- 生成拟合对比图和误差报告。

验收：

- 对 2-port 和 16-port 样例：加权 RMS 误差小于目标阈值，低频/DC 误差单独报告。
- passivity enforcement 后最大奇异值 <= 1 + epsilon，epsilon 默认 1e-6，可配置。
- 生成的子电路可被 ngspice 和 Xyce 至少一个后端成功运行 TRAN。

### 6.4 `sparam.mor`

职责：

- 第一阶段：封装 SROPEE 作为实验后端，收集端口数、阶数、运行时间、拟合误差。
- 第二阶段：若许可证或可维护性不满足要求，自研 MOR，算法候选包括 Block SAPOR/Krylov 子空间/端口分组。
- 输出降阶前后模型阶数、节点数、受控源数量、拟合误差变化。

验收：

- 对 32/64/128 端口样例，降阶后网表节点数或受控源数下降至少 3x。
- 关键频段阻抗和 transient droop 误差在可配置阈值内。
- 失败时自动回退到非降阶模型或分块模型。

### 6.5 `cpm.io`

职责：

- MVP 支持内部中间格式：JSON/CSV/PWL。
- 表达芯片 bump/region 的坐标、供电域、电流波形、时间单位、电压域、PVT 标签。
- 转换为 SPICE PWL 电流源或 B 源。
- 后续再接入 IEEE 2416 UPM/厂商 CPM 样本。

建议中间格式：

```json
{
  "model": "demo_chip",
  "time_unit": "s",
  "current_unit": "A",
  "domains": [{"name": "VDD", "nominal_v": 0.8}],
  "bumps": [
    {
      "name": "VDD_A1",
      "domain": "VDD",
      "node": "pkg_vdd_a1",
      "return_node": "vss",
      "xy_um": [120.0, 80.0],
      "waveform": [[0.0, 0.01], [1e-9, 0.05]]
    }
  ]
}
```

验收：

- 能生成 ngspice/Xyce 均可接受的 PWL 电流源。
- 能对波形做去毛刺/限斜率/采样压缩，避免不必要的瞬态刚性。
- 能输出总电流、每域电流、峰值 di/dt 报告。

### 6.6 `deck.builder`

职责：

- 生成后端兼容的 SPICE deck。
- 管理子电路命名空间，避免 CPM/S 参数/PDN 网表命名冲突。
- 支持 VRM、decap、probe、仿真命令模板。
- 支持同一设计输出 ngspice 和 Xyce 两套 deck。

验收：

- 同一 project manifest 可一键生成 `ngspice.cir` 和 `xyce.cir`。
- 所有生成文件携带 provenance：输入 hash、拟合参数、求解器版本、生成时间。
- 后端差异被封装在模板层，业务模块不直接拼接后端特定语法。

### 6.7 `backend.adapter`

职责：

- `NgspiceBackend`：优先使用 `libngspice`，其次 CLI fallback。
- `XyceBackend`：第一阶段使用外部进程和文件接口；后续评估更紧的 C++/服务接口。
- 标准化运行结果：波形、日志、返回码、错误分类、性能统计。
- 对常见失败给出自动建议：非无源、PWL 过陡、容差过紧、初始条件不合理、网表语法不兼容。

验收：

- 能运行 DC/AC/TRAN。
- 能捕获 `time step too small`、singular matrix、no convergence 等错误并分类。
- 运行结果转为统一的 parquet/npz/csv。

### 6.8 `hspice.compat`

职责：

- 接受团队既有 HSPICE deck：`.sp/.cir/.inc/.lib`。
- 做静态语法审计，识别指令、模型、库、参数表达式、层级节点名、单位后缀和输出请求。
- 生成兼容性 manifest：可原样运行、自动转换后运行、需人工处理、暂不支持。
- 对 Xyce 路径优先使用 XDM translator，并在运行时使用 HSPICE 兼容选项。
- 对 ngspice 路径实现平台自有转换子集，覆盖 PI deck 常见语法。
- 将 `.alter` 展开为多个 run case，避免把 corner/sweep 逻辑埋在单个后端 deck 中。
- 将 `.measure/.probe/.print` 归一化为平台统一 probe 和 metric 定义。

MVP 必须覆盖的语法子集：

- 文件与库：`.include`、`.inc`、`.lib`、`.endl`。
- 参数与全局：`.param`、`.global`、`.option`、`.temp`。
- 分析命令：`.op`、`.dc`、`.ac`、`.tran`。
- 输出命令：`.print`、`.probe`、`.measure`。
- 层级结构：`.subckt`、`.ends`、实例化 `X...`。
- 激励：`PULSE`、`PWL`、`SIN`、`EXP`、独立 V/I 源。
- 基础无源与常见 PI 模型：R/L/C/K、受控源、简单二极管和 MOS model passthrough。
- HSPICE 数值习惯：单位后缀、续行、注释、参数表达式、层级节点分隔符。

验收：

- 至少 10 个团队既有 HSPICE PI deck 无需人工改写即可进入平台运行。
- 每个 deck 生成 `compat_report.json`，列出转换项、保留项、忽略项和阻断项。
- `.alter` deck 被展开为多个独立 case，case 名称稳定可复现。
- `.measure` 结果被转为统一 metrics 文件，并可与原 HSPICE 参考结果比对。
- 对不支持语法给出明确位置、原文、原因和建议处理方式。

## 7. 关键技术策略

### 7.1 S 参数策略

默认流程：

```text
Touchstone
  -> metadata/port map
  -> reference impedance normalization
  -> DC/high-frequency conditioning
  -> passivity/causality quality check
  -> VectorFitting/auto_fit
  -> passivity_enforce
  -> optional MOR
  -> SPICE subcircuit
  -> ngspice/Xyce TRAN
```

设计原则：

- PDN 优先从 Y/Z 参数角度检查低频行为，不只看 S 参数。
- 拟合误差必须按 PI 频段加权：DC 到目标阻抗带宽的误差权重高于超高频尾部。
- passivity enforcement 不能把 DC/低频阻抗改坏；需要单独检查 `Z(0)` 和目标频段阻抗。
- 对 SI/PI 混合网络，强制要求端口角色标注，否则拒绝自动归一化。

### 7.2 求解器策略

ngspice：

- 用作 MVP、回归基线、嵌入式交互后端。
- 适合中小规模 PDN、子问题验证、模型质量快速迭代。
- 借助 libngspice 回调实现实时日志、数据读取和错误捕获。

Xyce：

- 用作大规模 batch/MPI 后端。
- 适合大节点数 RLC 网络、多个电源域、长瞬态仿真。
- 第一阶段保持进程隔离，降低 GPL/工程耦合风险；内部使用明确后再考虑更深集成。

后端选择规则：

| 场景 | 默认后端 |
|---|---|
| 单元测试/小型电路 | ngspice |
| S 参数拟合结果 smoke test | ngspice |
| 大规模 RLC PDN | Xyce |
| 多核服务器/集群 | Xyce MPI |
| 需要嵌入式逐步回调 | ngspice |
| 许可证必须宽松、未来可能外发 | ngspice |

### 7.3 CPM 策略

MVP 先支持可控中间格式，不直接押注厂商 CPM 私有格式。

输入路径：

1. `CSV/PWL`：最小可用，适合验证。
2. `JSON CPM-lite`：内部标准格式，保留坐标/域/波形/探针。
3. `SPICE subckt CPM`：作为黑盒导入，但要做命名空间隔离和语法兼容清洗。
4. `IEEE 2416/厂商 CPM`：拿到真实样本后再开发解析器。

波形处理：

- PWL 点数压缩：Douglas-Peucker 或误差约束分段。
- di/dt 限制和边沿平滑：避免不物理阶跃导致瞬态刚性。
- 多 bump 同步激励可分组，支持最坏工况相位偏移扫描。

### 7.4 递归卷积策略

递归卷积不进入 MVP，但需要在架构中预留：

- `sparam.fitting` 输出极点/留数，不只输出 SPICE 子电路。
- manifest 保存有理模型参数，为后续原生 n-port device 使用。
- 后续可实现 `NPortConvolutionDevice`：
  - 初期作为 ngspice XSPICE code model 或外部 co-sim device。
  - 成熟后再考虑深入求解器内核。

进入递归卷积开发的触发条件：

- 64/128 端口以上 S 参数宏模型导致 SPICE 子电路节点/受控源爆炸。
- Xyce MPI + MOR 仍不能满足目标运行时间。
- 团队已有稳定的 passivity/causality/极点质量保障。

### 7.5 HSPICE 兼容策略

“直接仿真”的产品定义：

- 用户可以把既有 HSPICE deck 交给平台，不手工编辑原文件。
- 平台可以选择原样传递、自动转换、拆分为多个 case，或阻断并给出诊断。
- 直接仿真不等于 100% HSPICE 私有语法克隆；兼容范围由内部回归库驱动，以 PI 相关 deck 为优先级最高。

推荐路径：

1. `hspice.audit` 先扫描 deck，构建 include/lib 依赖图和语法特征表。
2. 如果目标后端是 Xyce，优先尝试 XDM translator，并启用 HSPICE 兼容运行选项。
3. 如果目标后端是 ngspice，使用自研转换器处理常见 HSPICE 语法差异。
4. `.alter` 在中间件层展开为多个 project case，而不是依赖后端语义。
5. `.measure/.probe/.print` 被转换为统一 probe schema，后端输出再回填到统一 metrics。
6. 每次运行都保存原 deck hash、转换后 deck、兼容报告、后端日志和结果比对。

优先兼容的内部 PI deck 类型：

- VRM + decap + PDN RLC 网表。
- CPM/PWL 电流源激励瞬态 deck。
- S 参数宏模型已转成 SPICE subckt 后的系统 deck。
- corner/sweep 主要由 `.alter`、`.lib` section、`.param` 控制的 deck。
- 使用 `.measure` 提取 droop、peak-to-peak noise、settling time、impedance peak 的 deck。

## 8. 里程碑

### M0：两周技术确认

交付：

- 法务结论：GPL 内部使用、动态/进程调用、未来外发边界。
- 安装并跑通 ngspice、Xyce、scikit-rf、SROPEE。
- 收集 3 类真实或半真实样本：
  - 小型 2-port/4-port S 参数。
  - 16/32-port PDN S 参数。
  - CPM-like PWL 电流波形。
  - 至少 10 个团队既有 HSPICE PI deck。

成功标准：

- 明确 Path A：Xyce 可作为内部主后端；或 Path B：仅使用宽松许可栈。
- 有一份 benchmark dataset 清单。
- 有一份 HSPICE 语法覆盖矩阵，标出 MVP 必须支持和暂缓支持的语法。

### M1：四到六周 MVP 闭环

交付：

- CLI：`agent-spice run project.yaml --backend ngspice|xyce`
- CLI：`agent-spice run-hspice legacy.sp --backend ngspice|xyce`
- Touchstone 读取、质量检查、VectorFitting、passivity_enforce、SPICE 子电路导出。
- HSPICE deck 审计、自动转换、`.alter` 展开、`.measure` 归一化。
- CPM-lite JSON -> PWL 电流源。
- 自动生成 deck 并运行 TRAN。
- 输出基础报告：拟合误差、passivity、droop、runtime、memory。

成功标准：

- 2-port/4-port 样例端到端通过。
- 16-port 样例可以运行 TRAN 并给出波形。
- 同一输入可以选择 ngspice 或 Xyce 后端。
- 至少 10 个团队既有 HSPICE PI deck 无需人工修改即可运行；其中至少 5 个与原 HSPICE 参考 `.measure` 结果完成阈值内对齐。

### M2：八到十二周工程化

交付：

- 扩展到 32/64-port。
- 模型质量报告可视化。
- 错误分类和自动建议。
- HSPICE 兼容性报告和语法覆盖 dashboard。
- SROPEE/MOR 评估报告。
- ngspice vs Xyce 性能对比。

成功标准：

- 至少一个真实 PI case 与商业工具/参考结果对齐。
- 对 non-passive、bad DC、wrong Z0 的坏模型能提前拦截。
- 形成后端选择准则。
- 形成内部 HSPICE deck 兼容分级：直接支持、自动转换支持、需人工迁移、暂不支持。

### M3：三到六个月规模化

交付：

- Xyce MPI 后端生产化。
- 自研或可控许可 MOR。
- CPM/UPM 真实样本解析器。
- 大规模回归测试库。
- 初步 decap/VRM 参数扫描。

成功标准：

- 64/128-port S 参数 + CPM 激励可稳定运行。
- 大规模 case 相比 naive 子电路有明确 runtime/memory 改善。
- 有可复现 benchmark dashboard。

### M4：六个月以后高级能力

候选方向：

- 原生递归卷积 n-port device。
- PI/SI 联合仿真工作流。
- decap 优化器。
- 与 EM/PCB 工具的自动端口映射。
- GUI/波形查看器。

## 9. 验收指标

### 9.1 模型质量

- Passivity：最大奇异值 <= 1 + 1e-6，或 violation 被明确报告并阻断。
- 低频精度：`Z(0)` 或最低频点误差单独检查，默认 < 1%。
- 拟合误差：目标频段加权 RMS 默认 < -40 dB 或由 case 配置。
- 稳定性：所有极点实部必须在左半平面。

### 9.2 仿真正确性

- DC IR drop：与参考工具误差 < 3% 或 < 5 mV，二者取更宽松者，具体按项目校准。
- AC impedance：目标频段内峰值频率偏差 < 5%，峰值幅值误差 < 10%。
- TRAN droop：关键 probe 峰值跌落误差 < 5% 或 < 10 mV。
- 守恒检查：端口注入电流与网络消耗/储能变化应在容差内闭合。

### 9.3 性能

初始目标，需要用真实 case 校准：

- 16-port S 参数 + 简单 CPM：单机 5 分钟内完成。
- 64-port S 参数 + 中型 PDN：Xyce 后端 30 分钟内完成。
- MOR 后网表节点/受控源数量降低至少 3x。
- 失败 case 在进入长时间求解前给出可解释诊断。

## 10. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| GPL 边界不清 | 架构返工或未来商业化受阻 | M0 法务确认；Xyce 先保持进程级后端；核心中间件不依赖 GPL API |
| S 参数非无源/非因果 | TRAN 发散 | 前置质量门禁；passivity_enforce；坏模型拒绝进入求解 |
| 低阻 PDN 用 50 ohm 参考导致病态 | 拟合差、收敛差 | Touchstone 2.0 多参考阻抗；端口角色映射；Y/Z 域检查 |
| Vector Fitting 阶数爆炸 | 网表巨大、求解慢 | auto_fit、极点预算、MOR、端口分组、分块 |
| CPM PWL 边沿过陡 | time step too small | 波形压缩、边沿平滑、容差策略、初始条件 |
| HSPICE 私有语法长尾 | 既有 deck 迁移成本高 | 建内部 deck 回归库；优先覆盖真实 PI 语法；不支持项机器可读诊断 |
| `.alter`/corner 语义不一致 | sweep 结果错误 | 中间件展开为独立 case；保留原参数和 case manifest |
| `.measure` 方言差异 | 结果无法比对 | 转换为统一 metrics schema；保留原语句和等价表达式 |
| ngspice 性能不足 | 中大型 case 跑不动 | Xyce MPI 后端；ngspice 保持原型/回归角色 |
| SROPEE 工程成熟度不足 | MOR 依赖不稳 | 先实验封装；保留自研 MOR 路线；不要让 MVP 依赖它 |
| 厂商 CPM 格式拿不到 | 解析器误设计 | 先定义 CPM-lite；拿真实样本后适配 |

## 11. 项目目录建议

```text
agent-spice/
  docs/
    pi-spice-simulator-spec.md
    benchmark-plan.md
  src/
    agent_spice/
      sparam/
        io.py
        conditioning.py
        fitting.py
        mor.py
      cpm/
        io.py
        waveform.py
      hspice/
        audit.py
        converter.py
        alter.py
        measure.py
        manifest.py
      deck/
        builder.py
        templates/
      backend/
        base.py
        ngspice.py
        xyce.py
      report/
        metrics.py
        plots.py
  examples/
    simple_2port/
    pdn_16port/
    cpm_lite/
  tests/
    fixtures/
    test_sparam_quality.py
    test_hspice_compat.py
    test_deck_generation.py
    test_backend_smoke.py
```

## 12. 第一批任务拆解

1. 写 `project.yaml` schema：输入文件、端口映射、后端、仿真命令、验收阈值。
2. 写 `hspice.audit`：扫描 HSPICE deck，输出 include/lib 依赖图和语法覆盖报告。
3. 写 `hspice.converter`：实现 MVP 语法子集转换，Xyce 路径集成 XDM，ngspice 路径走自研转换。
4. 写 `hspice.alter`：把 `.alter` 展开成多个独立 case。
5. 写 `hspice.measure`：把 `.measure/.probe/.print` 转成统一 metrics schema。
6. 写 `sparam.io`：基于 scikit-rf 读取 Touchstone，输出 metadata。
7. 写 `sparam.quality`：passivity、Z0、DC、频率范围报告。
8. 写 `sparam.fitting`：调用 VectorFitting/auto_fit/passivity_enforce/export。
9. 写 `cpm-lite` parser：JSON/CSV -> PWL source。
10. 写 deck builder：最小 VRM + PDN macro + current sources + probes。
11. 写 ngspice CLI backend。
12. 写 Xyce CLI backend。
13. 建 HSPICE legacy deck、S 参数、CPM 三类 examples 和 smoke tests。
14. 建 benchmark report：runtime、memory、fit error、passivity、droop、HSPICE compat coverage。

## 13. 推荐技术栈

- Python：中间件、数据处理、CLI。
- NumPy/SciPy/scikit-rf：S 参数与拟合。
- pandas/pyarrow：波形和报告数据。
- matplotlib/plotly：报告图。
- ngspice：MVP/嵌入式后端。
- Xyce：大规模后端。
- XDM：Xyce 路径的 HSPICE/PSpice/Spectre 网表翻译器。
- pytest：回归测试。
- 可选 C++/Rust：后续高性能 MOR/递归卷积内核。

## 14. 决策记录

### DR-001：不从零写 SPICE 求解器

原因：成熟 SPICE 的收敛控制、器件模型、稀疏求解和积分算法需要多年积累。项目差异化在 PI 模型处理，不在基础求解器。

### DR-002：采用双后端，而不是单押 ngspice 或 Xyce

原因：ngspice 适合嵌入和快速原型，Xyce 适合规模。PI 平台需要二者能力，后端抽象成本低于未来迁移成本。

### DR-003：S 参数中间件是核心资产

原因：开源求解器没有满足 PI 瞬态要求的完整原生 S 参数卷积能力。模型净化、拟合、passivity、MOR 是产品成败关键。

### DR-004：MVP 不做递归卷积

原因：递归卷积性能潜力高，但内核侵入大。先用等效子电路法建立正确性基线，再决定是否进入内核开发。

### DR-005：HSPICE deck 兼容作为 P0 平台入口

原因：团队内部已有大量 HSPICE PI 网表。若不能直接进入新平台，迁移成本会压过求解器和 S 参数能力带来的收益。兼容层必须独立于具体后端，先做审计、转换、case 展开和结果归一化，再交给 ngspice/Xyce。

## 15. 参考来源

- Ngspice 官网与新闻：<https://ngspice.sourceforge.io/>、<https://ngspice.sourceforge.io/news.html>
- Ngspice 46 手册：<https://ngspice.sourceforge.io/docs/ngspice-46-manual.pdf>
- Xyce About：<https://xyce.sandia.gov/about-xyce/>
- Xyce 文档与教程：<https://xyce.sandia.gov/documentation-tutorials/>
- Xyce issue #116：<https://github.com/Xyce/Xyce/issues/116>
- Xyce issue #154：<https://github.com/Xyce/Xyce/issues/154>
- scikit-rf VectorFitting：<https://scikit-rf.readthedocs.io/en/latest/api/vectorFitting.html>
- scikit-rf `passivity_enforce`：<https://scikit-rf.readthedocs.io/en/latest/api/generated/skrf.vectorFitting.VectorFitting.passivity_enforce.html>
- scikit-rf `write_spice_subcircuit_s`：<https://scikit-rf.readthedocs.io/en/latest/api/generated/skrf.vectorFitting.VectorFitting.write_spice_subcircuit_s.html>
- scikit-rf license：<https://scikit-rf.readthedocs.io/en/latest/license.html>
- SROPEE GitHub：<https://github.com/RasulChoupanzadeh/SROPEE>
- Touchstone 2.1 specification：<https://ibis.org/touchstone_ver2.1/touchstone_ver2_1.pdf>
- Xyce XDM Netlist Translator User Guide：<https://xyce.sandia.gov/files/xyce/XDM_User_Guide_2.7.pdf>
- Xyce FAQ on compatibility and XDM：<https://xyce.sandia.gov/documentation-tutorials/frequently-asked-questions/>
- Xyce/XDM repository：<https://github.com/Xyce/XDM>
