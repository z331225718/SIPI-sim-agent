#![forbid(unsafe_code)]
#![recursion_limit = "512"]

//! Lane-local direct ports of Agent-COM's `compare`, `run_com`, and public
//! artifact workflows.
//!
//! The comparator validates and recursively compares semantic result payloads;
//! the run/API leaves execute the portable COM stages and publish bounded
//! artifacts. Workbook-only, MATLAB-only, and unported search branches remain
//! fail-closed. Source provenance and the MIT boundary are recorded in the
//! lane source maps and `NOTICE-AGENT-COM-MIT.md`.

use serde::Serialize;
use serde_json::Value;
use std::collections::BTreeSet;
use std::fmt::{Display, Formatter};
use std::fs;
use std::path::Path;

mod config_preflight_v1;
mod config_validate_v1;
mod run_v1;

pub use config_validate_v1::{
    ARGUMENT_ERROR_EXIT_CODE_V1, CONFIG_VALIDATE_POLICY_V1, CONFIG_VALIDATE_SCHEMA_V1,
    ConfigValidateErrorV1, ConfigValidateReportV1, ConfigValidateRequestV1,
    UNSUPPORTED_SCOPE_EXIT_CODE_V1, ValidatedProfileV1, config_validate_v1,
};
pub use run_v1::{
    COM_02_DIRECT_PORT_SCHEMA_V1, COM_04_DIRECT_PORT_SCHEMA_V1, COM_DIRECT_RESULT_SCHEMA_V1,
    DirectRunErrorV1, DirectRunReportV1, DirectRunRequestV1, MAX_CROSSTALK_CHANNELS_V1,
    MAX_SEARCH_FREQUENCY_POINTS_V1, MAX_SEARCH_TX_FFE_CANDIDATES_V1, RunArtifactSetV1,
    load_config_run_com_write_artifacts_v1, run_com_v1, write_artifacts_v1, write_run_artifacts_v1,
};

pub const DIRECT_PORT_SCHEMA_V1: &str = "sipi.agent-com.direct-compare.v1";
pub const RESULT_SCHEMA_VERSION_V1: u64 = 1;
pub const RESULT_SOURCE_REVISION_V1: &str = "r480";
pub const DEFAULT_ATOL_V1: f64 = 1.0e-12;
pub const MATCH_EXIT_CODE_V1: i32 = 0;
pub const MISMATCH_EXIT_CODE_V1: i32 = 3;
pub const JSON_INPUT_ERROR_EXIT_CODE_V1: i32 = 2;
pub const CONFIG_ERROR_EXIT_CODE_V1: i32 = 3;
pub const IO_ERROR_EXIT_CODE_V1: i32 = 1;

const REQUIRED_RESULT_KEYS: &[&str] = &[
    "schema_version",
    "source_revision",
    "profile",
    "cases",
    "provenance",
    "warnings",
    "timings_s",
];
const OPTIONAL_RESULT_KEYS: &[&str] = &["input_manifest", "report_manifest"];

/// Errors raised by the direct result reader/comparator.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum DirectCompareErrorV1 {
    Json(String),
    Schema(String),
    NegativeTolerance,
    Io { path: String, message: String },
}

impl Display for DirectCompareErrorV1 {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Json(message) => write!(formatter, "invalid result JSON: {message}"),
            Self::Schema(message) => write!(formatter, "{message}"),
            Self::NegativeTolerance => {
                write!(formatter, "comparison tolerance must be non-negative")
            }
            Self::Io { path, message } => write!(formatter, "cannot read {path}: {message}"),
        }
    }
}

impl std::error::Error for DirectCompareErrorV1 {}

/// The exact public JSON result shape emitted by Agent-COM's CLI.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct CompareReportV1 {
    pub matched: bool,
    pub mismatches: Vec<String>,
}

impl CompareReportV1 {
    pub fn matched(&self) -> bool {
        self.matched
    }

    pub fn mismatches(&self) -> &[String] {
        &self.mismatches
    }

    pub fn exit_code(&self) -> i32 {
        if self.matched {
            MATCH_EXIT_CODE_V1
        } else {
            MISMATCH_EXIT_CODE_V1
        }
    }

    /// Serialize with the same lexicographic top-level key order as
    /// `json.dumps(..., sort_keys=True)` in the pinned Python CLI.
    pub fn to_json(&self) -> String {
        let mismatches = format!(
            "[{}]",
            self.mismatches
                .iter()
                .map(|message| serde_json::to_string(message).expect("message is JSON"))
                .collect::<Vec<_>>()
                .join(", "),
        );
        format!(
            "{{\"matched\": {}, \"mismatches\": {mismatches}}}",
            if self.matched { "true" } else { "false" },
        )
    }
}

/// Parse and validate one upstream result artifact.
pub fn read_result_json_v1(bytes: &[u8]) -> Result<Value, DirectCompareErrorV1> {
    let document: Value = serde_json::from_slice(bytes)
        .map_err(|error| DirectCompareErrorV1::Json(error.to_string()))?;
    validate_result_json_v1(&document)?;
    Ok(document)
}

/// Read one upstream result artifact from a path.
pub fn read_result_path_v1(path: &Path) -> Result<Value, DirectCompareErrorV1> {
    let bytes = fs::read(path).map_err(|error| DirectCompareErrorV1::Io {
        path: path.display().to_string(),
        message: error.to_string(),
    })?;
    read_result_json_v1(&bytes)
}

/// Validate the release-critical subset implemented by upstream
/// `_validate_result_contract`.
pub fn validate_result_json_v1(document: &Value) -> Result<(), DirectCompareErrorV1> {
    let object = document.as_object().ok_or_else(|| {
        DirectCompareErrorV1::Schema(
            "result JSON does not satisfy result-v1 required keys".to_owned(),
        )
    })?;
    let required: BTreeSet<&str> = REQUIRED_RESULT_KEYS.iter().copied().collect();
    let optional: BTreeSet<&str> = OPTIONAL_RESULT_KEYS.iter().copied().collect();
    let keys: BTreeSet<&str> = object.keys().map(String::as_str).collect();
    if !required.is_subset(&keys)
        || keys
            .difference(&required)
            .any(|key| !optional.contains(key))
    {
        return Err(DirectCompareErrorV1::Schema(
            "result JSON does not satisfy result-v1 required keys".to_owned(),
        ));
    }
    if object.get("schema_version").and_then(python_number) != Some(RESULT_SCHEMA_VERSION_V1 as f64)
        || object.get("source_revision").and_then(Value::as_str) != Some(RESULT_SOURCE_REVISION_V1)
    {
        return Err(DirectCompareErrorV1::Schema(
            "unsupported result JSON schema version".to_owned(),
        ));
    }

    let profile = object.get("profile").and_then(Value::as_object);
    if profile
        .and_then(|value| value.get("source_revision"))
        .and_then(Value::as_str)
        != Some(RESULT_SOURCE_REVISION_V1)
        || profile
            .and_then(|value| value.get("fix_ids"))
            .and_then(Value::as_array)
            .is_none()
    {
        return Err(DirectCompareErrorV1::Schema(
            "result JSON has an invalid behavior profile".to_owned(),
        ));
    }

    let cases = object
        .get("cases")
        .and_then(Value::as_array)
        .ok_or_else(|| {
            DirectCompareErrorV1::Schema("result JSON must contain at least one case".to_owned())
        })?;
    if cases.is_empty() {
        return Err(DirectCompareErrorV1::Schema(
            "result JSON must contain at least one case".to_owned(),
        ));
    }
    for (expected_index, case) in cases.iter().enumerate() {
        let case_object = case.as_object();
        let case_index = case_object
            .and_then(|value| value.get("case_index"))
            .and_then(Value::as_i64);
        if case_index != Some(expected_index as i64)
            || case_object
                .and_then(|value| value.get("metrics"))
                .and_then(Value::as_object)
                .is_none()
        {
            return Err(DirectCompareErrorV1::Schema(
                "result JSON cases must have contiguous indices and metrics".to_owned(),
            ));
        }
        let metrics = case_object
            .and_then(|value| value.get("metrics"))
            .and_then(Value::as_object)
            .expect("metrics checked above");
        let signal = metrics
            .get("A_s")
            .or_else(|| metrics.get("available_signal_v"));
        if let Some(value) = signal {
            let numeric = python_number(value);
            if numeric.is_none() || numeric.is_some_and(|number| number < 0.0) {
                return Err(DirectCompareErrorV1::Schema(
                    "result JSON requires nonnegative A_s/available_signal_v".to_owned(),
                ));
            }
        }
        if let Some(cursor) = metrics.get("optimization_cursor")
            && (cursor.as_i64().is_none() && cursor.as_u64().is_none())
        {
            return Err(DirectCompareErrorV1::Schema(
                "result JSON optimization_cursor must be a signed integer".to_owned(),
            ));
        }
        let eye_width = metrics.get("EW_UI");
        let levels = metrics.get("levels").or_else(|| metrics.get("L"));
        if let (Some(eye_width), Some(levels)) = (eye_width, levels)
            && let Some(levels) = python_integer(levels)
            && levels >= 2
        {
            let shape = eye_width
                .as_object()
                .and_then(|value| value.get("shape"))
                .cloned()
                .or_else(|| {
                    eye_width
                        .as_array()
                        .map(|value| Value::Array(vec![Value::from(value.len() as u64)]))
                });
            let expected_shape = Value::Array(vec![Value::from((levels - 1) as u64)]);
            if shape.as_ref() != Some(&expected_shape) {
                return Err(DirectCompareErrorV1::Schema(
                    "result JSON EW_UI shape must equal L-1".to_owned(),
                ));
            }
        }
    }

    Ok(())
}

/// Compare two validated result artifacts using upstream's absolute-only
/// tolerance and comparable-metadata projection.
pub fn compare_result_json_v1(
    golden: &[u8],
    result: &[u8],
    atol: f64,
) -> Result<CompareReportV1, DirectCompareErrorV1> {
    if atol < 0.0 {
        return Err(DirectCompareErrorV1::NegativeTolerance);
    }
    let golden = comparable(read_result_json_v1(golden)?)?;
    let result = comparable(read_result_json_v1(result)?)?;
    let mut mismatches = Vec::new();
    compare_values(&golden, &result, atol, "$", &mut mismatches);
    Ok(CompareReportV1 {
        matched: mismatches.is_empty(),
        mismatches,
    })
}

/// Compare two result artifacts by path.
pub fn compare_result_paths_v1(
    golden: &Path,
    result: &Path,
    atol: f64,
) -> Result<CompareReportV1, DirectCompareErrorV1> {
    let golden_bytes = fs::read(golden).map_err(|error| DirectCompareErrorV1::Io {
        path: golden.display().to_string(),
        message: error.to_string(),
    })?;
    let result_bytes = fs::read(result).map_err(|error| DirectCompareErrorV1::Io {
        path: result.display().to_string(),
        message: error.to_string(),
    })?;
    compare_result_json_v1(&golden_bytes, &result_bytes, atol)
}

fn comparable(mut document: Value) -> Result<Value, DirectCompareErrorV1> {
    if let Some(object) = document.as_object_mut() {
        object.remove("timings_s");
        let mut provenance = python_string_key_dict(
            object
                .get("provenance")
                .expect("required provenance checked by validator"),
        )?;
        provenance.remove("platform");
        provenance.remove("python_version");
        object.insert("provenance".to_owned(), Value::Object(provenance));
    }
    Ok(document)
}

fn python_string_key_dict(
    value: &Value,
) -> Result<serde_json::Map<String, Value>, DirectCompareErrorV1> {
    if let Some(object) = value.as_object() {
        return Ok(object.clone());
    }
    let Some(items) = value.as_array() else {
        return Err(DirectCompareErrorV1::Schema(
            "result JSON provenance cannot be converted to a mapping".to_owned(),
        ));
    };
    let mut result = serde_json::Map::new();
    for item in items {
        let Some(pair) = item.as_array().filter(|pair| pair.len() == 2) else {
            return Err(DirectCompareErrorV1::Schema(
                "result JSON provenance cannot be converted to a mapping".to_owned(),
            ));
        };
        let Some(key) = pair[0].as_str() else {
            return Err(DirectCompareErrorV1::Schema(
                "result JSON provenance contains a non-string mapping key".to_owned(),
            ));
        };
        result.insert(key.to_owned(), pair[1].clone());
    }
    Ok(result)
}

fn compare_values(left: &Value, right: &Value, atol: f64, path: &str, messages: &mut Vec<String>) {
    match (left, right) {
        (Value::Object(left), Value::Object(right)) => {
            let left_keys: BTreeSet<&String> = left.keys().collect();
            let right_keys: BTreeSet<&String> = right.keys().collect();
            if left_keys != right_keys {
                messages.push(format!("{path}: keys differ"));
            }
            for key in left_keys.intersection(&right_keys) {
                compare_values(
                    left.get(*key).expect("key from left set"),
                    right.get(*key).expect("key from right set"),
                    atol,
                    &format!("{path}.{key}"),
                    messages,
                );
            }
        }
        (Value::Array(left), Value::Array(right)) => {
            if left.len() != right.len() {
                messages.push(format!("{path}: list lengths differ"));
            } else {
                for (index, (left, right)) in left.iter().zip(right.iter()).enumerate() {
                    compare_values(left, right, atol, &format!("{path}[{index}]"), messages);
                }
            }
        }
        _ if python_numbers_equal(left, right, atol) => {}
        _ if left == right => {}
        _ => messages.push(format!(
            "{path}: {} != {}",
            python_repr(left),
            python_repr(right)
        )),
    }
}

fn python_numbers_equal(left: &Value, right: &Value, atol: f64) -> bool {
    let (Some(left), Some(right)) = (python_number(left), python_number(right)) else {
        return false;
    };
    if left.is_nan() || right.is_nan() {
        return left.is_nan() && right.is_nan();
    }
    (left - right).abs() <= atol
}

fn python_number(value: &Value) -> Option<f64> {
    match value {
        Value::Bool(value) => Some(if *value { 1.0 } else { 0.0 }),
        Value::Number(number) => number.as_f64(),
        _ => None,
    }
}

fn python_integer(value: &Value) -> Option<i128> {
    match value {
        Value::Number(number) if number.is_i64() => number.as_i64().map(i128::from),
        Value::Number(number) if number.is_u64() => number.as_u64().map(i128::from),
        _ => None,
    }
}

fn python_repr(value: &Value) -> String {
    match value {
        Value::Null => "None".to_owned(),
        Value::Bool(value) => if *value { "True" } else { "False" }.to_owned(),
        Value::String(value) => format!("'{value}'"),
        Value::Number(number) => number.to_string(),
        Value::Array(_) | Value::Object(_) => value.to_string(),
    }
}

/// Classify an error according to the pinned CLI's observable exit semantics.
pub fn error_exit_code_v1(error: &DirectCompareErrorV1) -> i32 {
    match error {
        DirectCompareErrorV1::Json(_) => JSON_INPUT_ERROR_EXIT_CODE_V1,
        DirectCompareErrorV1::Schema(_) | DirectCompareErrorV1::NegativeTolerance => {
            CONFIG_ERROR_EXIT_CODE_V1
        }
        DirectCompareErrorV1::Io { .. } => IO_ERROR_EXIT_CODE_V1,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn result(metrics: Value) -> Value {
        serde_json::json!({
            "schema_version": 1,
            "source_revision": "r480",
            "profile": {"source_revision": "r480", "reader_semantics": "r480", "fix_ids": []},
            "cases": [{"case_index": 0, "metrics": metrics}],
            "provenance": {"platform": "one", "python_version": "one", "stable": "same"},
            "warnings": [],
            "timings_s": {"pipeline": 1.0}
        })
    }

    fn bytes(value: &Value) -> Vec<u8> {
        serde_json::to_vec(value).expect("json")
    }

    #[test]
    fn ignores_upstream_non_comparable_metadata() {
        let left = result(serde_json::json!({"COM_dB": 1.2}));
        let mut right = left.clone();
        right["timings_s"] = serde_json::json!({"pipeline": 999.0});
        right["provenance"]["platform"] = serde_json::json!("other");
        right["provenance"]["python_version"] = serde_json::json!("other");
        let report =
            compare_result_json_v1(&bytes(&left), &bytes(&right), DEFAULT_ATOL_V1).unwrap();
        assert!(report.matched);
        assert_eq!(report.to_json(), r#"{"matched": true, "mismatches": []}"#);
    }

    #[test]
    fn preserves_python_schema_version_equality_and_provenance_dict_conversion() {
        for version in [serde_json::json!(true), serde_json::json!(1.0)] {
            let mut value = result(serde_json::json!({"COM_dB": 1.2}));
            value["schema_version"] = version;
            assert!(validate_result_json_v1(&value).is_ok());
        }

        let mut left = result(serde_json::json!({"COM_dB": 1.2}));
        let mut right = left.clone();
        left["provenance"] = serde_json::json!([]);
        right["provenance"] = serde_json::json!([["platform", "ignored"], ["stable", "same"]]);
        let report = compare_result_json_v1(&bytes(&left), &bytes(&right), DEFAULT_ATOL_V1)
            .expect("JSON sequences accepted by Python dict() remain comparable");
        assert!(!report.matched);
        assert_eq!(report.mismatches, vec!["$.provenance: keys differ"]);
    }

    #[test]
    fn uses_absolute_tolerance_and_reports_nested_path() {
        let left = result(serde_json::json!({"COM_dB": 1.2, "nested": [1, 2]}));
        let right = result(serde_json::json!({"COM_dB": 1.2005, "nested": [1, 3]}));
        let report = compare_result_json_v1(&bytes(&left), &bytes(&right), 0.001).unwrap();
        assert!(!report.matched);
        assert_eq!(
            report.mismatches,
            vec!["$.cases[0].metrics.nested[1]: 2 != 3"]
        );
        assert_eq!(report.exit_code(), MISMATCH_EXIT_CODE_V1);
    }

    #[test]
    fn validates_each_upstream_error_branch() {
        let base = result(serde_json::json!({"COM_dB": 1.2}));
        let mut wrong_version = base.clone();
        wrong_version["schema_version"] = serde_json::json!(2);
        assert!(matches!(
            validate_result_json_v1(&wrong_version),
            Err(DirectCompareErrorV1::Schema(message)) if message.contains("unsupported")
        ));
        let mut empty_cases = base.clone();
        empty_cases["cases"] = serde_json::json!([]);
        assert!(matches!(
            validate_result_json_v1(&empty_cases),
            Err(DirectCompareErrorV1::Schema(message)) if message.contains("at least one")
        ));
        let mut negative_signal = base.clone();
        negative_signal["cases"][0]["metrics"] = serde_json::json!({"A_s": -1.0});
        assert!(matches!(
            validate_result_json_v1(&negative_signal),
            Err(DirectCompareErrorV1::Schema(message)) if message.contains("nonnegative")
        ));
        let mut bad_cursor = base.clone();
        bad_cursor["cases"][0]["metrics"] = serde_json::json!({"optimization_cursor": 1.5});
        assert!(matches!(
            validate_result_json_v1(&bad_cursor),
            Err(DirectCompareErrorV1::Schema(message)) if message.contains("optimization_cursor")
        ));
        let mut bad_eye = base;
        bad_eye["cases"][0]["metrics"] = serde_json::json!({"L": 4, "EW_UI": [0.1, 0.2]});
        assert!(matches!(
            validate_result_json_v1(&bad_eye),
            Err(DirectCompareErrorV1::Schema(message)) if message.contains("EW_UI")
        ));
    }

    #[test]
    fn preserves_python_bool_numeric_compare_rule() {
        let left = result(serde_json::json!({"value": true}));
        let right = result(serde_json::json!({"value": 1}));
        let report = compare_result_json_v1(&bytes(&left), &bytes(&right), 0.0).unwrap();
        assert!(report.matched);
    }

    #[test]
    fn rejects_negative_tolerance_before_reading_inputs() {
        let error = compare_result_json_v1(b"not json", b"not json", -1.0).unwrap_err();
        assert_eq!(error, DirectCompareErrorV1::NegativeTolerance);
        assert_eq!(error_exit_code_v1(&error), CONFIG_ERROR_EXIT_CODE_V1);
    }

    #[test]
    fn schema_rejects_unknown_top_level_keys() {
        let mut value = result(serde_json::json!({"COM_dB": 1.2}));
        value["unknown"] = serde_json::json!(true);
        assert!(matches!(
            validate_result_json_v1(&value),
            Err(DirectCompareErrorV1::Schema(message)) if message.contains("required keys")
        ));
    }
}
