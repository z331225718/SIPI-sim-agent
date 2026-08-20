# Audit：P4B-02b193 parameter-list-prevalence-map

## 切片语义
- **值级切片**：`parameter_list_prevalence_map_v1` 返回 `BTreeMap<String, f64>`，
  仅含**mode 子集**（出现次数 == 最大计数的 item），值为共享比例 `max_count / total`。
- **伴侣关系**：02b180 prevalence-ratio（单值 f64）的 map 形态——比例 + 达到它的 mode items；
  键集 == 02b165 mode-item 集；与 02b192 relative-frequency-map（覆盖全部 distinct item）区分。
- **f64 位精确**：crosscheck 以 12 位小数字符串逐位比较（产品 `format!("{x:.12}")` vs Python `f"{x:.12f}"`）。
- **规则绑定**：02b1 列表规则（`(item, item, ...)`，项 trim 非空）；02b0 原始字节相等。
- **fail-closed**：非 List 值 → `NotAList`；token 不匹配 List 形态 → `MalformedList`（防御性，不可达）。

## 工件清单
- 实现：`crates/sipi-ami-text/src/parameter_list_prevalence_map_v1.rs`（6 Rust 单测，含并列 mode 用例）
- runner：`tests/p4b_02b193_parameter_list_prevalence_map_runner.rs`（harness=false，单值 JSON 输入，12 位小数字符串输出）
- crosscheck：`tools/run_p4b_02b193_parameter_list_prevalence_map_crosscheck.py`（4/4 matched_hash_bound，含 tied_mode 用例）
- verifier/unittest：`tools/verify_p4b_02b193_...py` + `test_verify_...py`（6 tests，含篡改拒绝）
- charter（based_on=192 条）+ source map（mapping×2）+ evidence（CRLF）

## 门禁结果
- `cargo test -p sipi-ami-text --lib`：1103 + 6 = 1109 全绿
- 单切片 verifier valid + pytest 6/6；coverage gates=363
- session health 6/6：TOTAL=345, VALID_KEY=321, gates=363, links=415, BAD=0

## 登记
- ledger note 追加 prevalence-map (02b193, 4/4 crosscheck) delivered；gate 条目更新
- PLAN.md 叙事插入 02b192 审计链接之后；CRLF 字节级断言通过（二进制读写 + CRLF 感知 line_end）
