use serde_json::{Value, json};
use sipi_agent_com_direct::{
    DEFAULT_ATOL_V1, MISMATCH_EXIT_CODE_V1, compare_result_json_v1, validate_result_json_v1,
};

fn document(metrics: Value) -> Value {
    json!({
        "schema_version": 1,
        "source_revision": "r480",
        "profile": {"source_revision": "r480", "reader_semantics": "standard", "fix_ids": ["fix.a"]},
        "cases": [{"case_index": 0, "metrics": metrics}],
        "provenance": {"platform": "x", "python_version": "x", "stable": "yes"},
        "warnings": [],
        "timings_s": {"pipeline": 0.1}
    })
}

fn bytes(value: &Value) -> Vec<u8> {
    serde_json::to_vec(value).expect("JSON")
}

#[test]
fn fresh_result_shape_matches_at_default_tolerance() {
    let left = document(json!({"COM_dB": 1.2, "ERL": -12.0, "array": [1.0, 2.0]}));
    let mut right = left.clone();
    right["timings_s"] = json!({"pipeline": 1000.0});
    right["provenance"]["platform"] = json!("different");
    right["provenance"]["python_version"] = json!("different");
    let report = compare_result_json_v1(&bytes(&left), &bytes(&right), DEFAULT_ATOL_V1).unwrap();
    assert!(report.matched());
    assert_eq!(report.exit_code(), 0);
}

#[test]
fn complete_mismatch_report_and_exit_three() {
    let left = document(json!({"COM_dB": 1.2, "array": [1.0, 2.0]}));
    let right = document(json!({"COM_dB": 1.3, "array": [1.0, 3.0]}));
    let report = compare_result_json_v1(&bytes(&left), &bytes(&right), 0.0).unwrap();
    assert_eq!(report.exit_code(), MISMATCH_EXIT_CODE_V1);
    assert_eq!(
        report.mismatches(),
        &[
            "$.cases[0].metrics.COM_dB: 1.2 != 1.3",
            "$.cases[0].metrics.array[1]: 2.0 != 3.0"
        ]
    );
}

#[test]
fn validation_is_independent_of_compare_order() {
    let mut value = document(json!({"L": 4, "EW_UI": [0.1, 0.2, 0.3]}));
    validate_result_json_v1(&value).unwrap();
    value["cases"][0]["case_index"] = json!(1);
    assert!(validate_result_json_v1(&value).is_err());
}
