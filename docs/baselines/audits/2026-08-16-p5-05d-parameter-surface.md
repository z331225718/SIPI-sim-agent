# P5-05d Parameter Surface Report Stage — Audit

- slice: **P5-05d**（parameter surface extraction + consumption classification）
- date: 2026-08-16
- schema: `sipi.p5-05d.parameter-surface-stage.v1`

## 范围

从任一 workbook surface（xlsx/csv/mat 统一面）提取全部 (key, value) 对并按
canonical 消费 key 集合分类：

| 面 | Rust |
| --- | --- |
| lookup 扫描语义（excel.py lookup_optional 面） | `extract_parameter_pairs_v1` |
| 网格 surface + canonical 分类 | `classify_parameter_surface_v1` |
| RawCell 坐标/值面 | `ParameterPairV1` |

逐函数映射 + observation 引用记录于 `docs/baselines/p5-05d-mit-source-map.v1.yaml`
（3 项 mapping；canonical 集合引用 `p5-r480-canonical-parameter-reference.v1.yaml`
，214 keys / 229 xls_parameter 调用）。

## 语义要点

- 提取：非空字符串 cell（trim 后）且右侧 cell 存在且值非空 → 一个 pair
  （key 保留原始字符串；坐标与 typed 值类型保留）
- 分类：key ∈ canonical 集合 → consumed；否则 → unconsumed（表头/单位噪声
  如实落入 unconsumed——**未使用字段全部保留在报告中，不丢弃**）
- xlsx 授权 config：137 pairs → **82 consumed / 41 unconsumed**，与 P5-06c
  的 82 消费 key 观察吻合（跨证据一致性）

## 非声明

- 值消费 / 默认解析（P5-02 consumption 面）
- behavior profile、workbook 写回
- 非 profile acceptance、非 release evidence

## 验证

- sipi-com 累计 **54 测试绿**（本 stage 3 项：提取保留全部字段、分类拆分、
  policy；含 empty-right 不丢面）
- crosscheck：`tools/run_p5_05d_surface_crosscheck.py`，oracle 外部 custody
  `ComSettings.from_xlsx/csv/mat` + Python 独立提取：
  - xlsx 授权 config（hash f2c4c92f…）：**137 pairs 逐项匹配**（key/坐标/
    值类型），consumed 82 / unconsumed 41 集合一致
  - CSV / MAT fixture：提取与分类双方一致
- 证据：`docs/baselines/p5-05d-surface-crosscheck-evidence.v1.yaml`

## 门禁绑定

- `tools/verify_p5_05d_parameter_surface.py`（charter/source-map/evidence/
  tokens/PLAN 行绑定）+ 6 项 verifier 测试
- ledger `P5-05` gate 列表 += verify_p5_05d；`total_open` 保持 31
- open-item gate coverage 100 → **101**

## 结论

P5-05d 语义达成：参数表面报告（含未使用字段）与 oracle 在三种 surface 上
全一致，且与 P5-06c 的 82 消费 key 观察交叉吻合。P5-05 主项剩余：值消费/
默认解析（依赖 P5-02 consumption 面契约）。
