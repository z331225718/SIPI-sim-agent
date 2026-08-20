# Audit：P4B-02b188 parameter-list-occurrence-indices-map

## 切片语义
- **值级切片**：`parameter_list_occurrence_indices_map_v1` 返回 `BTreeMap<String, Vec<usize>>`，
  键为每个 distinct trimmed item，值为该项**全部**出现的 0-based 下标（升序）。
- **伴侣关系**：02b186 first-occurrence-map / 02b187 last-occurrence-map 的富化形态——
  逐项 `indices[0]` == 02b186 首现下标、`indices[last]` == 02b187 末次下标、`indices.len()` == 02b121 逐项计数。
- **规则绑定**：02b1 列表规则（`(item, item, ...)`，项 trim 非空）；02b0 原始字节相等。
- **fail-closed**：非 List 值 → `NotAList`；token 不匹配 List 形态 → `MalformedList`（防御性，不可达）。

## 工件清单
- 实现：`crates/sipi-ami-text/src/parameter_list_occurrence_indices_map_v1.rs`（6 Rust 单测）
- runner：`tests/p4b_02b188_parameter_list_occurrence_indices_map_runner.rs`（harness=false，单值 JSON 输入）
- crosscheck：`tools/run_p4b_02b188_parameter_list_occurrence_indices_map_crosscheck.py`（4/4 matched_hash_bound）
- verifier/unittest：`tools/verify_p4b_02b188_...py` + `test_verify_...py`（6 tests，含篡改拒绝）
- charter（based_on=187 条）+ source map（mapping×2）+ evidence（CRLF）

## 门禁结果
- `cargo test -p sipi-ami-text --lib`：1073 + 6 = 1079 全绿
- 单切片 verifier valid + pytest 6/6；coverage gates=358
- session health 6/6：TOTAL=340, VALID_KEY=316, gates=358, links=410, BAD=0

## 登记
- ledger note 追加 occurrence-indices-map (02b188, 4/4 crosscheck) delivered；gate 条目更新
- PLAN.md 叙事插入 02b187 审计链接之后；CRLF 字节级断言通过（二进制读写）
