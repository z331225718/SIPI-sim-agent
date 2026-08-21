//! External-custody selected-model consumer runner (P4A-03bk).
//!
//! This target is not a product file route.  An operator supplies both the
//! complete input path and every selected-profile field; no model, selector,
//! corner, PVT, or table family is chosen by the runner.

use std::{collections::BTreeSet, path::PathBuf};

use serde_json::{Value, json};
use sipi_ibis::{
    CornerPvtV1, ParseLimitsV1, SELECTED_MODEL_POLICY_V1, SelectedModelConsumerV1,
    SelectedModelRequestV1, SelectedModelTargetV1, SignalPinRoleV1, TableFamilyV1,
};

fn string_field<'a>(value: &'a Value, name: &str) -> Result<&'a str, String> {
    value
        .get(name)
        .and_then(Value::as_str)
        .ok_or_else(|| format!("missing_or_invalid_{name}"))
}

fn reject_unknown_keys(value: &Value, allowed: &[&str]) -> Result<(), String> {
    let object = value
        .as_object()
        .ok_or_else(|| "selected_profile_must_be_object".to_owned())?;
    if let Some(key) = object.keys().find(|key| !allowed.contains(&key.as_str())) {
        return Err(format!("unknown_selected_profile_field:{key}"));
    }
    Ok(())
}

fn parse_request(value: &Value) -> Result<SelectedModelRequestV1, String> {
    reject_unknown_keys(value, &["role", "target", "corner_pvt", "table_family"])?;
    let role = value.get("role").ok_or_else(|| "missing_role".to_owned())?;
    reject_unknown_keys(role, &["kind", "name"])?;
    let role = match string_field(role, "kind")? {
        "signal" => SignalPinRoleV1::signal(string_field(role, "name")?)
            .map_err(|error| format!("{error:?}"))?,
        "pin" => SignalPinRoleV1::pin(string_field(role, "name")?)
            .map_err(|error| format!("{error:?}"))?,
        other => return Err(format!("unsupported_role_kind:{other}")),
    };

    let target = value
        .get("target")
        .ok_or_else(|| "missing_target".to_owned())?;
    let target = match string_field(target, "kind")? {
        "model" => {
            reject_unknown_keys(target, &["kind", "model"])?;
            SelectedModelTargetV1::model(string_field(target, "model")?)
                .map_err(|error| format!("{error:?}"))?
        }
        "selector_branch" => {
            reject_unknown_keys(target, &["kind", "selector", "branch"])?;
            SelectedModelTargetV1::selector_branch(
                string_field(target, "selector")?,
                string_field(target, "branch")?,
            )
            .map_err(|error| format!("{error:?}"))?
        }
        other => return Err(format!("unsupported_target_kind:{other}")),
    };

    let pvt = value
        .get("corner_pvt")
        .ok_or_else(|| "missing_corner_pvt".to_owned())?;
    reject_unknown_keys(pvt, &["corner", "voltage_v", "temperature_c"])?;
    let corner = string_field(pvt, "corner")?;
    let voltage_v = pvt
        .get("voltage_v")
        .and_then(Value::as_f64)
        .ok_or_else(|| "missing_or_invalid_voltage_v".to_owned())?;
    let temperature_c = pvt
        .get("temperature_c")
        .and_then(Value::as_f64)
        .ok_or_else(|| "missing_or_invalid_temperature_c".to_owned())?;
    let pvt = CornerPvtV1::try_new(corner, voltage_v, temperature_c)
        .map_err(|error| format!("{error:?}"))?;

    let table_family = TableFamilyV1::parse(string_field(value, "table_family")?)
        .map_err(|error| format!("{error:?}"))?;
    SelectedModelRequestV1::try_new(role, target, pvt, table_family)
        .map_err(|error| format!("{error:?}"))
}

fn write_or_print(report: Option<PathBuf>, value: &Value) {
    let encoded = serde_json::to_string_pretty(value).expect("json");
    if let Some(path) = report {
        std::fs::write(path, encoded).expect("write report");
    } else {
        println!("{encoded}");
    }
}

fn main() {
    let mut input = None;
    let mut request = None;
    let mut report = None;
    let mut markers = BTreeSet::new();
    let mut args = std::env::args().skip(1);
    while let Some(argument) = args.next() {
        let mut value = || args.next().expect("argument value");
        match argument.as_str() {
            "--input" => input = Some(PathBuf::from(value())),
            "--request" => request = Some(PathBuf::from(value())),
            "--report" => report = Some(PathBuf::from(value())),
            "--marker" => {
                markers.insert(value());
            }
            other => panic!("unknown argument: {other}"),
        }
    }

    let Some(input) = input else {
        write_or_print(
            report,
            &json!({
                "policy": SELECTED_MODEL_POLICY_V1,
                "valid": false,
                "error": "missing_input",
            }),
        );
        std::process::exit(2);
    };
    let Some(request) = request else {
        let output = match std::fs::read(&input) {
            Ok(bytes) => {
                let limits = ParseLimitsV1::try_new(
                    16 * 1024 * 1024,
                    8 * 1024 * 1024,
                    256 * 1024,
                    512 * 1024,
                )
                .expect("limits");
                match sipi_ibis::IbisTypedInventoryServiceV1::inspect(&bytes, limits, &markers) {
                    Ok(inventory) => json!({
                        "policy": SELECTED_MODEL_POLICY_V1,
                        "valid": false,
                        "error": "missing_required_selected_profile",
                        "required": ["role", "model_or_selector_branch", "corner_pvt", "table_family"],
                        "complete_document": true,
                        "model_count": inventory.models().len(),
                        "selector_count": inventory.selectors().len(),
                        "pin_count": inventory.pins().len(),
                    }),
                    Err(error) => json!({
                        "policy": SELECTED_MODEL_POLICY_V1,
                        "valid": false,
                        "error": "missing_required_selected_profile",
                        "complete_document": false,
                        "inventory_error": format!("{error:?}"),
                    }),
                }
            }
            Err(error) => json!({
                "policy": SELECTED_MODEL_POLICY_V1,
                "valid": false,
                "error": format!("input_read:{error}"),
            }),
        };
        write_or_print(report, &output);
        std::process::exit(2);
    };

    let output = match (std::fs::read(&input), std::fs::read(&request)) {
        (Ok(bytes), Ok(request_bytes)) => match serde_json::from_slice::<Value>(&request_bytes)
            .map_err(|error| error.to_string())
            .and_then(|value| parse_request(&value))
        {
            Ok(selection_request) => {
                let limits = ParseLimitsV1::try_new(
                    16 * 1024 * 1024,
                    8 * 1024 * 1024,
                    256 * 1024,
                    512 * 1024,
                )
                .expect("limits");
                match SelectedModelConsumerV1::select(&bytes, limits, &markers, &selection_request)
                {
                    Ok(selection) => json!({
                        "policy": SELECTED_MODEL_POLICY_V1,
                        "valid": true,
                        "status": "selected_model_resolved",
                        "role": {"kind": selection.role().kind(), "name": selection.role().name()},
                        "pin_name": selection.pin_name(),
                        "signal_name": selection.signal_name(),
                        "selector": selection.target().selector(),
                        "branch": selection.target().branch(),
                        "corner": selection.corner_pvt().corner(),
                        "voltage_v": selection.corner_pvt().voltage_v(),
                        "temperature_c": selection.corner_pvt().temperature_c(),
                        "table_family": selection.table().family().canonical_name(),
                        "table_row_count": selection.table().row_count(),
                        "table_section_line": selection.table().section_span().line(),
                        "model_type": format!("{:?}", selection.model_type()),
                    }),
                    Err(error) => json!({
                        "policy": SELECTED_MODEL_POLICY_V1,
                        "valid": false,
                        "error": format!("{error:?}"),
                    }),
                }
            }
            Err(error) => json!({
                "policy": SELECTED_MODEL_POLICY_V1,
                "valid": false,
                "error": "invalid_selected_profile",
                "detail": error,
            }),
        },
        (Err(error), _) => json!({
            "policy": SELECTED_MODEL_POLICY_V1,
            "valid": false,
            "error": format!("input_read:{error}"),
        }),
        (_, Err(error)) => json!({
            "policy": SELECTED_MODEL_POLICY_V1,
            "valid": false,
            "error": format!("request_read:{error}"),
        }),
    };
    let valid = output
        .get("valid")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    write_or_print(report, &output);
    if !valid {
        std::process::exit(2);
    }
}
