# P5-05a Workbook Importer Xlsx Stage — Audit

- slice: **P5-05a**（workbook importer xlsx reader + lookup）
- date: 2026-08-16
- schema: `sipi.p5-05a.workbook-importer-stage.v1`

## 范围

从 MIT agent-com 源 `src/agent_com/config/excel.py` 移植 COM_Settings xlsx
读取与 r4.80 keyword lookup 语义：

| Python | Rust |
| --- | --- |
| `_validate_xlsx_container` | `validate_xlsx_container_v1` |
| `_is_strict_ooxml` | `is_strict_ooxml_v1` |
| `ComSettings.from_xlsx` / `_strict_xlsx_cells` | `read_com_settings_xlsx_v1` + `parse_sheet_cells` |
| `_strict_shared_strings` | `read_shared_strings` |
| `_strict_cell_value` / openpyxl 值绑定 | `classify_cell_value` + `flush_cell` |
| `ComSettings.lookup_optional` / `lookup` | `ComSettingsV1::lookup_optional_v1` / `lookup_v1` |
| `RawCell` | `RawCellV1` |

逐函数映射记录于 `docs/baselines/p5-05a-mit-source-map.v1.yaml`（7 项）。

## 语义要点（与源逐点对照）

- 容器校验：仅 .xlsx；zip 必须可解；`xl/vbaproject.bin`（宏）与
  `xl/externallinks/*`（外部链接）拒绝
- Strict/Transitional 双路径：workbook.xml 根命名空间或
  `conformance="strict"` 判定；COM_Settings 工作表经 workbook rels
  定位（posixpath 归一化）；`calcPr calcMode=manual` 或
  `fullCalcOnLoad=1` → 拒绝（要求重算）
- 公式缓存：有公式无缓存值 → 拒绝；Transitional 下 t=d 缓存类型
  不支持 → 拒绝；公式文本保留（`=` 前缀）
- 值分类：s→shared string（索引越界拒绝）；b→bool；str/e→字符串；
  inlineStr→Transitional 取 `<is>` 文本 / Strict 取 v 文本；无 t→
  f64（整数→Integer，超出 i64 范围拒绝；非数值→字符串，与源一致）
- 空白语义：字符串值与 shared strings 的 rich-text 拼接**保留首尾
  空白**（修复了 trim_text 导致的丢失）
- lookup：casefold 语义按 ASCII lowercase 面实现（charter 记录）；
  0 匹配→None；>1→Duplicate；右侧缺失或值为空→Missing

## 非声明

- `ComSettings.from_csv` / `_csv_value` 未移植（P5-05b）
- `ComSettings.from_mat` / `_matlab_cell_value` 未移植（P5-05b）
- 参数 DTO 消费 / 未使用字段报告未移植
- 非 profile acceptance、非 release evidence

## 验证

- sipi-com 累计 **45 测试绿**（本 stage 4 项：列号转换往返、坐标解析、
  值分类含字符串回退与共享串索引拒绝、policy；全量含此前 04a-04g）
- crosscheck：`tools/run_p5_05a_workbook_crosscheck.py`，授权 config
  xlsx（hash f2c4c92f…，hash 校验通过）：
  - oracle 外部 custody `ComSettings.from_xlsx`（openpyxl 3.1.5 /
    numpy 2.4.6）vs 产品 runner：**2048 cells 逐 cell 匹配**（坐标、
    类型化值、公式，含 `=26.5625*2`/53.125、` [TX RX]` 空白保留、
    logical 尾随空格）；5 个 lookups（f_b/A_ft/Port Order/COM_Settings/FOM）
    全部一致
  - 负面 fixture：注入 vbaProject.bin / externallinks 条目 → oracle 与
    产品**双方一致拒绝**
- 依赖：新增 zip 2.4.2 / quick-xml 0.37（MIT 通用库，clean-room
  允许；sipi-ibis 的 sha2 先例）
- 证据：`docs/baselines/p5-05a-workbook-crosscheck-evidence.v1.yaml`

## 门禁绑定

- `tools/verify_p5_05a_workbook_importer.py`（charter/source-map/evidence/
  tokens/PLAN 行绑定）+ 6 项 verifier 测试
- ledger `P5-05` gate 列表 += verify_p5_05a；`total_open` 保持 31
- open-item gate coverage 97 → **98**

## 结论

P5-05a 语义达成：产品 xlsx importer 与 MIT 源 oracle 在授权 workbook 上
2048 cells 全匹配，负面面双方一致拒绝。剩余 P5-05 范围：CSV/MAT reader
（from_csv/from_mat）、参数 DTO 消费与未使用字段报告。
