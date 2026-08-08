# Native 生产基线固化与 IdEM s19 调参研究设计

## 1. 背景

完整六文件 benchmark 已确认当前 Native S 参数拟合与无源修正算法具备生产可用性：

- 在 Test13.s60p、Test16.s91p、Test11.s163p、Test3.s166p 上，Native 均达到最终 mean S-RMS 小于等于 `0.001`，并通过无源性验收。
- 大端口文件上的最终精度与峰值内存已经和 IdEM 接近；主要差距集中在最小有效 order 和总搜索时间。
- 对数据质量较差的文件，Native 可以通过增加公共极点 order 继续降低误差，有时比当前 IdEM fixed-order 默认配置更有优势。
- 高 order 会扩大后续状态空间和 SPICE 等效电路，可能显著拖慢 PI transient 仿真，因此“能拟合”不能替代“以较低 order 拟合”。
- s19 文件在公共 order 上限 100 时，Native 最佳 mean S-RMS 约为 `0.001543`，IdEM fixed-order 最佳约为 `0.014961`，两者均未达到 `0.001`。

旧 benchmark 对 Native 和 IdEM 使用了相同的外层 target-driven order search：依次尝试偶数 order，首次通过后回填相邻奇数 order。但是每个 trial 内部都是 fixed-order fitting。IdEM XML 中的 `<order><type>fixed</type>` 使 Adding、Skimming、`postadding`、`enhancePolesPlacement`、stagnation 和 guaranteed accuracy 等内部自适应能力没有被启用。

因此下一阶段包含两个独立目标：

1. 将当前 Native 算法固化为唯一生产 fitting 基线，移除旧 skrf fitting 算法入口，防止误用和行为漂移。
2. 使用 IdEM 官方内部 adaptive order refinement 和高级参数研究 s19，确认 IdEM 是否能在低复杂度下达到 `0.001 + passive`，并从迭代历史中分析其极点发现和阶数控制策略。

## 2. 术语和 order 口径

### 2.1 有效 order

公共极点模型的有效 order 定义为：

```text
effective_order = real_pole_count + 2 * complex_pair_count
```

所有 fixed-order 对比继续使用该定义。

### 2.2 外层 adaptive order search

现有 benchmark 和生产 target-driven fitting 使用外层调度：

1. 尝试 `4, 6, 8, ..., max_order`。
2. 找到第一个同时满足最终 RMS 和无源性的偶数 order。
3. 回填上一个失败偶数与当前通过偶数之间的奇数 order。
4. 选择通过 trial 中 effective order 最小者。

每个 trial 内部仍是 fixed-order fitting。

### 2.3 IdEM 内部 adaptive order refinement

IdEM 的内部自适应过程在一次 fitting 中从 minimum order 开始，通过 Adding 硬增加极点，并通过 Skimming 删除低贡献或疑似拟合噪声的极点。其停止行为受 target accuracy、guaranteed accuracy、stagnation、skimming 和 maximum order 共同控制。

内部 adaptive 结果不能只用“最后一次请求 order”描述，必须同时记录：

- 初始 order、order increment、maximum order。
- `ordersHistory` 中的实际迭代 order。
- 最终每个 split 的 effective order。
- 总极点/状态数量。
- 若使用 splitting，则记录所有 split 的总状态数和最大单 split order。

## 3. 范围

### 3.1 范围内

- 将 Native fitting 固化为 `fit-sparam` 和 Python fitting API 的唯一生产算法。
- 删除 skrf VectorFitting 和 skrf 原版 pole relocation 的可选入口。
- 将当前 Native 依赖的自研 streaming relocation 从 `skrf_streaming.py` 迁移到中性 Native 模块。
- 移除生产 SPICE exporter 选择面：生产路径固定使用 Native writer，不提供 exporter 字段或 CLI flag；外部 IdEM 仅作为 benchmark/research adapter 保留。
- 保留 skrf 作为非 fitting 基础设施和研究功能的可选依赖。
- 给生产基线增加显式版本号、配置快照和回归测试。
- 增加 IdEM adaptive fitting 适配器、可恢复实验 runner 和结果报告。
- 对 s19 先执行 `splitting=none` 的分阶段参数实验。
- 提取 IdEM HDF5 中的 error/order/pole histories，形成可审计的算法观察结论。
- 若公共模型仍失败，再根据互易性判断是否允许 splitting 对照。

### 3.2 范围外

- 不彻底移除项目的 skrf 依赖。
- 不重写 Touchstone 2.0、modal-Z、独立 metrics 等成熟基础功能。
- 不因本次清理改变当前 Native 数值算法、passivity 参数或 benchmark 口径。
- 不把 splitting 模型的单 split order 与公共极点 order 直接比较。
- 不在没有实测证据时宣称已经反推出 IdEM 私有实现。
- 不在本阶段直接优化 Native 的低 order 极点发现；本阶段先固化基线并获取 IdEM adaptive 证据。

## 4. 总体架构

本工作拆分为两个边界清晰的工作流。

### 4.1 工作流 A：Native 生产基线固化

生产 fitting 代码只保留一条数值路径：

```text
Touchstone
  -> lightweight S/RI loader（主路径）
  -> NativeVectorFitting
  -> Native streaming/reciprocal pole relocation
  -> Native residue solve
  -> Hamiltonian passivity check/enforcement
  -> Native SPICE writer
  -> full-grid report
```

skrf 仍可由 io fallback、metrics、modal 和研究工具按需延迟加载，但不会参与默认 Native fitting 进程。导入测试必须继续证明 Native fitting 不加载 `skrf` 或 `skrf.vectorFitting`。

### 4.2 工作流 B：IdEM s19 参数研究

实验代码与生产 Native fitting 分离：

```text
s19 input + input SHA
  -> experiment contract/options fingerprint
  -> IdEM adaptive fitting
  -> inspect .mod.h5 histories/poles/order
  -> pre-accuracy gate
  -> IdEM passivity enforcement
  -> final accuracy + authoritative check-only
  -> Touchstone MA export
  -> independent full-grid RMS/SVD audit
  -> trial.json + comparison report
```

每个 trial 使用独立目录并原子写入阶段记录。相同输入、IdEM 身份、实验合同和参数指纹可恢复；任何一项变化均重新运行。

## 5. Native 生产基线设计

### 5.1 唯一 fitting backend

- 删除 `vector_fit_backend` 的公开 CLI 选项。
- 删除 `SParamFitConfig` 对 `skrf` backend 的支持。
- `_create_vector_fitting()` 始终创建 `NativeVectorFitting`。
- 删除 `_LazyVectorFitting` 和对 `skrf.vectorFitting.VectorFitting` 的生产引用。
- 旧配置显式传入 `vector_fit_backend="skrf"` 时不再静默回退；CLI 应报告该选项已移除，Python API 应通过构造参数错误暴露不兼容。

### 5.2 relocation 固化

当前生产基线保留按端口规模选择 relocation 实现的行为：

- 小于 30 端口：streaming relocation。
- 大于等于 30 端口：streaming reciprocal relocation。

该选择改为内部策略，不再暴露 `--relocation-backend`。

`skrf_streaming.py` 中被 Native 使用的实现迁移到 Native 命名模块，例如 `pole_relocation.py`。只保留当前基线需要的 streaming 与 reciprocal 路径；删除仅用于 monkey-patch skrf VectorFitting 的上下文管理器和 skrf reference backend。

### 5.3 exporter 命名

- 生产 API/CLI 不提供 exporter 选择，固定调用 `NativeVectorFitting.write_spice_subcircuit_s()`。
- 删除原 `skrf`/`native`/`idem` exporter 配置字段和 CLI flag。
- 外部 IdEM adapter 仅保留给 benchmark 和算法研究，不进入生产运行时路径。

### 5.4 基线版本

增加显式基线标识，例如：

```text
native_baseline_version = native-idem-fast-v1
```

该标识进入：

- JSON/HTML fit report。
- target trial fingerprint。
- full-corpus benchmark fingerprint。
- README 的生产算法说明。

版本只在数值行为或默认配置发生有意变化时更新。

### 5.5 兼容与清理

- 保留 skrf 包依赖，不从项目依赖表删除。
- 保留 `io.py` 的 Touchstone fallback、`metrics.py`、`modal.py` 和 IdEM 研究函数中的按需 skrf 使用。
- 删除或改写只验证 skrf fitting backend、skrf relocation monkey patch 的测试。
- 保留“Native 主路径不导入 skrf”的测试，并增加默认配置快照测试。
- 用户当前未提交的 pole-discovery 和 passivity probe 文件不属于本次清理范围。

## 6. IdEM adaptive fitting 适配器

### 6.1 命令和 XML 职责

IdEM 官方文档将 `bandwidth` 和 `order` 标记为 XML reserved parameters。adaptive trial 使用命令行控制：

```text
idemmp_fitting.exe
  -its <input>
  -o <model.mod.h5>
  -tol 0.001
  -orderMin <minimum>
  -orderStep <increment>
  -orderMax <maximum>
  -bandwidth <fmax>
  -DC 1
  -nThreads 8
  -xml <advanced-options.xml>
```

advanced XML 不写 fixed `<order>`，只负责：

- iterations。
- weighting。
- errorControl。
- splitting 和 response selection。
- outOfBand behavior。

fixed-order adapter 保持现状，用于基准对照；adaptive adapter 使用独立 dataclass 和 renderer，避免两个模式互相覆盖。

### 6.2 adaptive trial 输出

每个 trial 至少保存：

- 完整命令和 advanced XML。
- IdEM stdout/stderr、return code、wall time、peak RSS。
- fitting model 和 passive model。
- `inspect_idem_model()` 完整摘要。
- `errorHistory`、`ordersHistory`、最终 pole blocks。
- pre/final IdEM accuracy report。
- passivity enforcement/check report。
- exported Touchstone 和 independent audit。
- 统一 trial summary 和 fingerprint。

IdEM 返回码 1 继续使用 artifact-based 成功判定，不将返回码本身解释为失败。

## 7. s19 实验协议

### 7.1 固定合同

- 输入：`5power_19port_withcap_122324_202459_11476_DCfitted.s19p`。
- 输入 SHA-256：`87fccc96196d8c149d1b3ba985701dd56a78f5d9904984f55f8161c39cdd7c7e`。
- 原始频点：826，全频训练和全频验收。
- 参数表示：S。
- RMS：所有频点、所有端口对的 mean S-RMS。
- 目标：最终 mean S-RMS `<= 0.001`。
- 无源目标：IdEM authoritative check-only 为 passive，且原始网格 sampled max sigma `<= 1 + 1e-6`。
- 线程：8。
- 公共模型 maximum order：100。
- 主实验 splitting：none。
- 单个 fitting/passivity 阶段 timeout：7200 秒。

### 7.2 对照组

保留两个明确对照：

1. 旧 fixed-order order 100：用于确认旧 benchmark 结果可复现。
2. IdEM adaptive 默认高级路径：`orderMin=4, orderStep=2, orderMax=100, tol=0.001`，advanced options 使用官方默认值，splitting none。

### 7.3 第一阶段：单变量筛选

单变量 trial 均以 adaptive 默认高级路径为基准，每次只改变一组具有同一算法含义的参数。

#### 极点 Adding

- `enhancePolesPlacement`: false / true。
- `postadding`: 1 / 2 / 3。
- `initial`: 3 / 5。
- `final`: 1 / 3。

#### 停滞与噪声底

- stagnation alpha：`0.05 / 0.01 / 0.001`。
- back steps：`3 / 5`。

较小 alpha 的假设是避免 s19 被过早判定为已到噪声底。

#### Adding/Skimming 转换

- guaranteed accuracy：`0.1 / 0.01 / 0.001`。
- skimming relative tolerance：`1e-3 / 1e-4 / 1e-5`。
- final skimming tolerance：`1e-3 / 1e-4 / 1e-5`。

该组用于判断是否存在有效极点被过早删除，或 Adding 过早转入 Adding+Skimming。

#### 带外极点

- reject poles：disabled。
- enabled，max relative frequency：`1.0 / 1.2 / 2.0`。

官方文档指出带外极点可能导致过拟合和数值恶化。该组需要同时比较最终 RMS、极点频率和 order history。

#### 渐近无源约束

- asymptotic passivity enabled，margin 使用当前基准值，relocate poles false / true。
- 仅在 fit 精度接近目标但最终 passivity/RMS 退化时，再尝试更小和更大的 margin；不在第一批盲扫大量 margin。

#### pole relocation 响应选择

- `p4poles=all`。
- `p4poles=eye`。
- dominant largest responses：选择少量候选数量，但 residues 继续覆盖 all responses。

该组验证“少数高能响应决定公共极点”是否适用于 s19。

### 7.4 第二阶段：有效参数组合

单变量的“有效”定义为满足至少一项且不造成明显反向退化：

- pre-enforcement RMS 相对基准降低至少 20%。
- 在相同或更低 final order 下达到更低 RMS。
- 从不达标变为达到 `0.001`。
- 使最终 passivity 可修正，同时 final RMS 仍不超过 `0.001`。

只组合有明确证据的参数。组合按两两开始，最多加入三个不同机制的参数，避免形成不可解释的大型网格。

### 7.5 第三阶段：frequency weighting

仅当最佳 trial 的 residual 显示误差集中于稳定频带时启用 frequency weighting：

- 先生成按频率聚合的 RMS/max-error 曲线。
- 权重锚点由 residual band 自动生成并写入报告。
- 权重范围限制在 `[1e-3, 1]`，避免极小权重掩盖全局误差。
- 最终验收仍使用无权 mean S-RMS，不能用加权训练指标代替。

### 7.6 第四阶段：splitting 对照

仅当 splitting none 的最佳组合仍不能满足合同才进入。

1. 先计算原始数据的互易误差。
2. 若数据被 IdEM 判断为 reciprocal，则遵守官方限制，不尝试 column/row/all。
3. 若允许 splitting，优先 column；all 只作为精度上限对照。
4. splitting 结果记录总状态数、每个 split order、SPICE 文件大小和 transient complexity proxy。
5. splitting 模型不参与公共 order parity，只回答“IdEM 能否以非公共稀疏模型解决 s19”。

## 8. 算法观察与结论边界

每个 adaptive trial 生成以下派生分析：

- error vs iteration/order 曲线。
- 每次 order increment 后的误差改善。
- Skimming 导致的 order 下降和误差变化。
- 最终极点的实部、虚部、频率和带外比例。
- enhanced placement 对新极点频率分布的影响。
- reject poles 对带外 pole 和 conditioning 的影响。
- asymptotic relocation 对 poles/residues/final passivity 的影响。

结论分为三类：

- **实测事实**：来自命令、HDF5、accuracy、passivity 和 independent audit。
- **强推断**：参数变化与历史轨迹之间具有可重复因果关系。
- **假设**：无法从公开输出直接证明的内部实现机制。

报告禁止把假设写成已经反编译或确认的 IdEM 私有算法。

## 9. 失败处理与可恢复性

- 每个阶段完成后原子写 JSON。
- stale model/report/export 在重跑阶段前删除。
- trial fingerprint 包含输入 SHA、IdEM executable identity、实验合同、全部选项和验证代码 identity。
- 非有限指标、点数/端口不匹配、order 解析失败、导出网格不一致均标记 INVALID。
- pre-RMS 高于目标时允许跳过 passivity，但仍保存 fitting histories。
- 某 trial timeout 或失败不终止整个参数实验。
- 成功和对分析有价值的失败 model 保留；重复、明确劣化的中间二进制在摘要落盘后清理。

## 10. 测试设计

### 10.1 Native 基线测试

- 默认配置只创建 NativeVectorFitting。
- CLI 不再暴露 skrf/vector backend 和 relocation backend。
- API 不接受已删除 backend 字段。
- 小/大端口内部 relocation 策略与当前生产版本一致。
- Native fitting 进程不导入 skrf。
- Native writer 可生成有效 SPICE，生产路径不依赖 IdEM。
- baseline version 出现在报告和 fingerprint。
- 现有 target order、passivity、resume 和 full-corpus tests 全部通过。

### 10.2 IdEM adaptive adapter 测试

- adaptive 命令精确包含 orderMin/orderStep/orderMax/tol。
- advanced XML 不写 reserved fixed order。
- 所有新增参数正确序列化。
- fixed 和 adaptive 模式不能混用。
- HDF5 order/error histories 可解析。
- return-code-1 仍按 artifact 判断。
- resume 只复用完全相同的指纹。
- final acceptance 使用 post-enforcement accuracy 和独立 audit。

### 10.3 真实 smoke

- 先用 2-port fixture 跑 adaptive IdEM smoke。
- 再用 s19 跑一个低 maximum order 的 bounded smoke，验证 histories、阶段记录和 cleanup。
- smoke 有效后才开始完整 s19 参数实验。

## 11. 交付物

- 固化后的 Native fitting 代码和精简 CLI。
- Native baseline version 和 README。
- IdEM adaptive fitting options/runner/tests。
- s19 参数实验 manifest、trial records、summary JSON/CSV。
- `docs/sparam-idem-s19-tuning.md`，由 summary 自动生成。
- 一份明确区分事实、推断和假设的 IdEM adaptive algorithm analysis。

大型 runs 目录不提交 Git；提交可复现命令、输入 SHA、canonical Markdown 和必要的小型摘要。

## 12. 完成标准

本工作完成需同时满足：

1. `fit-sparam` 和 Python fitting API 不再存在 skrf fitting/relocation 算法选择。
2. 当前 Native 生产路径的数值默认和完整测试保持稳定。
3. Native 主路径继续不加载 skrf。
4. IdEM adaptive order refinement 可通过命令和 XML 自动运行、恢复和审计。
5. s19 的 splitting-none 参数阶段全部完成或形成明确 bounded failure。
6. 若找到成功配置，最终模型满足 mean S-RMS `<= 0.001`、authoritative passive 和原始 826 点独立审计。
7. 若未找到成功配置，报告给出最佳 RMS/order、停止原因、pole/order histories 和后续 splitting 决策。
8. 所有仓库测试通过，用户现有未提交研究改动保持不变。
