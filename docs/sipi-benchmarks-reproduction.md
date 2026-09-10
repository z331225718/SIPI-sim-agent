# SIPI vs Keysight ADS 基准测试复现指南 (Benchmark Reproduction Guide)

本文档记录如何在本机从零完整复现 **三大标准 SI/PI（S 参数、DDR4/5、瞬态 TDR 与 PDN）基准对比** 以及 **Keysight ADS 2026 Update1 物理传输线点对点对比**，生成完整的自包含离线 HTML 报告、高清双曲线叠图与 CSV 数据集。

---

## 一、运行环境与前置依赖

1. **操作系统**：Windows 11 x64
2. **构建工具**：
   - Rust / Cargo 工具链（Rust 1.85+ / 2024 edition）
3. **仿真求解器与 Python 环境**（二选一）：
   - **推荐（包含真机 ADS 闭环）**：本机安装的 Keysight ADS 2026 Update1
     - 求解器路径：`C:\Program Files\Keysight\ADS2026_Update1\bin\hpeesofsim.exe`
     - 内置 Python 路径：`C:\Program Files\Keysight\ADS2026_Update1\tools\python\python.exe`（内置 `numpy`, `matplotlib`, `keysight.ads.dataset`）
   - **独立轻量级复现**：标准 Python 3.10+ 环境（安装 `numpy` 与 `matplotlib` 即可运行全部 9 个标准 SI/PI 基准并导出报告，无需启动 ADS 求解器）。

---

## 二、完整复现步骤

### 第一步：编译构建 SIPI Release 二进制程序

在仓库根目录下，启用 `pybert-direct-integration` 特性编译 release 模式可执行文件：

```powershell
cargo build --release -p sipi-cli --features pybert-direct-integration
```

编译生成路径为：
`target/release/sipi.exe`

校验版本与帮助信息：
```powershell
.\target\release\sipi.exe channel help
.\target\release\sipi.exe ami help
```

---

### 第二步：一键运行 9 大标准 SI/PI 基准对比并生成 HTML 报告

使用 ADS 内置 Python（或已安装 matplotlib 的系统 Python）执行基准驱动脚本：

```powershell
$ads_py = 'C:\Program Files\Keysight\ADS2026_Update1\tools\python\python.exe'
& $ads_py -B tools/run_sipi_sp_ddr_tran_benchmarks.py `
    --output-dir results/sipi-benchmarks-sp-ddr-tran-20260910 `
    --sipi target/release/sipi.exe
```

#### 该命令执行的 9 大对比用例：
1. **Case 1 (SP)**：宽带微带线高频衰减（0~20 GHz，趋肤效应与介质损耗，ADS vs SIPI 叠图与残差）。
2. **Case 2 (SP)**：未背钻过孔残桩 15 GHz 谐振深陷波（59.1 dB 衰减深度对比）。
3. **Case 3 (SP)**：4 端口差分过孔 16 模态混合模转换（Sdd21, Scc21, Scd21 模态抑制比）。
4. **Case 4 (DDR)**：DDR4-3200 DQ 写数据链路（Fly-by 残桩 + 48 $\Omega$ ODT）与 JEDEC JESD79-4 掩模合规。
5. **Case 5 (DDR)**：DDR5-6400 DQ 链路未均衡（闭合违规）vs 4-Tap DFE 均衡（完全开眼）与 JEDEC JESD79-5 掩模合规。
6. **Case 6 (TRAN)**：TDR 阶跃时域反射阻抗剖面重构 $Z(t)$（$50\,\Omega \to 75\,\Omega \to 42\,\Omega$ 逐段台阶还原）。
7. **Case 7 (PI)**：PDN 多阶去耦电容抗谐振阻抗曲线 $Z(f)$ 与 $Z_{\text{target}}=4.25\,\text{m}\Omega$ 比较。
8. **Case 8 (PI)**：核电轨 6A 动态阶跃电流下陷（Droop）瞬态波形与 VRM 恢复仿真。
9. **Case 9 (统计眼)**：32 GBd 统计眼图 2D 等高线（$10^{-3} \dots 10^{-12}$）与双斜率浴盆曲线（Bathtub Curve）全量叠图。

---

### 第三步：运行 Keysight ADS 物理传输线真实求解对照

调用真机 ADS `hpeesofsim.exe` 电路求解器，与本仓库实际 `sipi.exe` 进行逐点比较：

```powershell
$ads_py = 'C:\Program Files\Keysight\ADS2026_Update1\tools\python\python.exe'
$ads_root = 'C:\Program Files\Keysight\ADS2026_Update1'

# 1. 初始化计划文件（支持 physical-voltage-v1 物理电压协议）
& $ads_py -B tools/run_channel_native_ads_bench.py init `
    results/channel-native-ads-candidate-plan-20260909.json `
    --channel-policy physical-voltage-v1

# 2. 执行 6 大物理/解析案例（双重复，共 12 次完整 ADS 求解）
& $ads_py -B tools/run_channel_native_ads_bench.py run `
    results/channel-native-ads-candidate-plan-20260909.json `
    --output-dir results/channel-native-ads-candidate-20260909 `
    --sipi target/release/sipi.exe `
    --ads-root $ads_root `
    --case matched-native-grid `
    --case source-cap `
    --case load-cap `
    --case both-cap `
    --case matched-legacy-grid `
    --case mismatched-legacy-grid `
    --timeout 120
```

---

### 第四步：执行全量自动化校验与结果审计

#### 1. 基准套件数值与图表完整性回归（Python）
```powershell
& $ads_py -B tools/test_sipi_sp_ddr_tran_benchmarks.py
```
- 检验全部 9 个案例数值门限、8 项测试断言、CSV 格式与 17 张 Base64 嵌入图片的一致性。

#### 2. Keysight 原生数据集 SDK 逐点复核（Python）
```powershell
& $ads_py -B tools/verify_channel_native_ads_bench.py `
    results/channel-native-ads-candidate-20260909 `
    --output results/channel-native-ads-candidate-20260909-verification.json `
    --allow-incomplete
```
- 通过 `keysight.ads.dataset` 接口直接重读 `channel_native_ads.ds` 原始二进制数据集，逐点核对时域与频域所有配对点数值。

#### 3. Rust 底层单元与集成测试套件
```powershell
cargo test --offline -p sipi-channel
cargo test --offline -p sipi-cli --features pybert-direct-integration
```
- 运行 46 项 channel 算法测试与 75 项 CLI/端到端集成测试，确认全部通过。

---

### 第五步：查看离线交互式综合报告

在浏览器中打开生成的综合报告：

```powershell
# 打开自包含综合对比报告（内嵌 17 张高清双曲线叠图与 34 张逐点数据表）：
Start-Process results/sipi-benchmarks-sp-ddr-tran-20260910/report.html

# 打开物理传输线 ADS 原生实跑对比报告：
Start-Process results/channel-native-ads-candidate-20260909/report.html
```

报告特性：
- **100% 自包含**：单文件约 5.1 MB，所有图表均以 Base64 内嵌，无需外网或外部图片文件，在任何设备或离线环境中均可完整显示。
- **逐点数值表格**：每个案例内置斑马纹数值表，提供 `<details>` 控件支持一键展开查看上百行全量数据。
- **CSV 导出**：支持直接下载各案例的独立数据文件进行二次分析。
