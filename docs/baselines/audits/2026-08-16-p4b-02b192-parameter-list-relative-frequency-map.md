# Audit：P4B-02b192 parameter-list-relative-frequency-map

## 切片语义
- **值级切片**：`parameter_list_relative_frequency_map_v1` 返回 `BTreeMap<String, f64>`，
  键为每个 distinct trimmed item，值为比例 `count / total`（(0, 1] 内，和为 1.0）。
- **伴侣关系**：02b181 frequency-normalized 的 map 形态伴侣（相同数据，BTreeMap vs 首现序 Vec）；
  逐项比例 == 02b190 frequency-map count / len；最大项 == 02b180 prevalence ratio。
- **f64 位精确**：crosscheck 以 12 位小数字符串逐位比较（产品 `format!("{x:.12}")` vs Python `f"{x:.12f}"`）。
- **规则绑定**：02b1 列表规则（`(item, item, ...)`，项 trim 非空）；02b0 原始字节相等。
- **fail-closed**：非 List 值 → `NotAList`；token 不匹配 List 形态 → `MalformedList`（防御性，不可达）。

## 工件清单
- 实现：`crates/sipi-ami-text/src/parameter_list_relative_frequency_map_v1.rs`（6 Rust 单测）
- runner：`tests/p4b_02b192_parameter_list_relative_frequency_map_runner.rs`（harness=false，单值 JSON 输入，12 位小数字符串输出）
- crosscheck：`tools/run_p4b_02b192_parameter_list_relative_frequency_map_crosscheck.py`（4/4 product_owned_self_crosscheck_unbound）
- verifier/unittest：`tools/verify_p4b_02b192_...py` + `test_verify_...py`（6 tests，含篡改拒绝）
- charter（based_on=191 条）+ source map（mapping×2）+ evidence（CRLF）

## 门禁结果
- `cargo test -p sipi-ami-text --lib`：1097 + 6 = 1103 全绿
- 单切片 verifier valid + pytest 6/6；coverage gates=362
- session health 6/6：TOTAL=344, VALID_KEY=320, gates=362, links=414, BAD=0

## 登记
- ledger note 追加 relative-frequency-map (02b192, 4/4 crosscheck) delivered；gate 条目更新
- PLAN.md 叙事插入 02b191 审计链接之后；CRLF 字节级断言通过（二进制读写 + CRLF 感知 line_end）
