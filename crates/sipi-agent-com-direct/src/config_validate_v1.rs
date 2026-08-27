//! COM-01 source-schema-driven direct port of Agent-COM config validate.
//!
//! The lane embeds the exact pinned r4.80 schema/default resources and
//! materializes the same source-order parameter/option assignments.  It does
//! not execute a COM runtime; the artifact is the upstream validation and
//! materialization boundary only.

use serde::Deserialize;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use sipi_com::{
    CellValueV1, ComSettingsV1, LiteralV1, ResolvedDefaultV1, WorkbookErrorV1, parse_literal_v1,
    read_com_settings_csv_v1, read_com_settings_mat_v1, read_com_settings_xlsx_v1,
    resolve_default_value_v1,
};
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::fmt::{Display, Formatter};
use std::fs;
use std::path::{Path, PathBuf};

use crate::config_preflight_v1::preflight_config_source_v1;

const SCHEMA_BYTES: &[u8] =
    include_bytes!("../quarantine/agent-com/schemas/r480-config.schema.yaml");
const BEHAVIOR_BYTES: &[u8] =
    include_bytes!("../quarantine/agent-com/schemas/behavior-presets.yaml");
const REGISTRY_BYTES: &[u8] =
    include_bytes!("../quarantine/agent-com/consumption-registry.v1.json");
const SCHEMA_SHA256: &str = "55a98abea9de8f8335cdfa327b3fded733f23ce60220b39117a951577c14760c";
const BEHAVIOR_SHA256: &str = "906e1b05bedf620fa431406b0ea41fae81dd235e759ff2155c17e68dccdf6d3e";
const REGISTRY_SHA256: &str = "43e2ddda5bb945c2ff5b82dc63e1c4581cb367ade6f63dc6e37cf15bc1667e54";
const MAX_CONFIG_FILE_BYTES: u64 = 16 * 1024 * 1024;
const MAX_CONFIG_CELLS: usize = 1_000_000;
const MAX_NUMERIC_ELEMENTS: usize = 1_000_000;
const MAX_COUNT_VALUE: usize = 1_000_000;
const MAX_MATERIALIZED_FINGERPRINT_BYTES: usize = MAX_CONFIG_FILE_BYTES as usize;

pub const CONFIG_VALIDATE_POLICY_V1: &str =
    "sipi.com-01.config-validate-v1.source-schema-materialized";
pub const CONFIG_VALIDATE_SCHEMA_V1: &str = "sipi.com-01.config-validate.v1";
pub const CONFIG_ERROR_EXIT_CODE_V1: i32 = 3;
pub const ARGUMENT_ERROR_EXIT_CODE_V1: i32 = 2;
pub const UNSUPPORTED_SCOPE_EXIT_CODE_V1: i32 = 5;

const KNOWN_FIX_IDS: &[&str] = &[
    "fix.calibration_per_case_td",
    "fix.cl120e_calibration_names",
    "fix.cl120e_calibration_pz_order",
    "fix.config_defaults",
    "fix.erl_best_phase",
    "fix.honor_tdr_bt_cutoff",
    "fix.quantization_without_rxffe",
    "fix.reject_duplicate_package_name",
    "fix.sigma_hp_rms",
];

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ConfigValidateRequestV1 {
    pub config: PathBuf,
    pub profile: String,
    pub reader: Option<String>,
    pub fix_ids: Vec<String>,
    pub overrides: Vec<String>,
    pub json: bool,
    pub materialized_json: bool,
}

impl ConfigValidateRequestV1 {
    pub fn validate(&self) -> Result<ValidatedProfileV1, ConfigValidateErrorV1> {
        if self.json && self.materialized_json {
            return Err(ConfigValidateErrorV1::Argument(
                "config validate JSON modes are mutually exclusive".to_owned(),
            ));
        }
        let profile = validate_profile(&self.profile, self.reader.as_deref(), &self.fix_ids)?;
        parse_overrides(&self.overrides)?;
        if self.config.as_os_str().is_empty() {
            return Err(ConfigValidateErrorV1::Argument(
                "configuration path is required".to_owned(),
            ));
        }
        Ok(profile)
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ValidatedProfileV1 {
    pub name: String,
    pub reader_semantics: String,
    pub fix_ids: Vec<String>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ConfigValidateErrorV1 {
    Argument(String),
    Profile(String),
    Override(String),
    Unsupported(String),
    Workbook(String),
    Io(String),
}

impl Display for ConfigValidateErrorV1 {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Argument(message) => {
                write!(formatter, "invalid config validate request: {message}")
            }
            Self::Profile(message) => write!(formatter, "invalid behavior profile: {message}"),
            Self::Override(message) => write!(formatter, "invalid override: {message}"),
            Self::Unsupported(message) => write!(formatter, "unsupported COM-01 scope: {message}"),
            Self::Workbook(message) => write!(formatter, "configuration error: {message}"),
            Self::Io(message) => write!(formatter, "configuration I/O error: {message}"),
        }
    }
}

impl std::error::Error for ConfigValidateErrorV1 {}

impl ConfigValidateErrorV1 {
    pub const fn exit_code(&self) -> i32 {
        match self {
            Self::Argument(_) => ARGUMENT_ERROR_EXIT_CODE_V1,
            Self::Unsupported(_) => UNSUPPORTED_SCOPE_EXIT_CODE_V1,
            Self::Override(_) => ARGUMENT_ERROR_EXIT_CODE_V1,
            Self::Profile(_) | Self::Workbook(_) | Self::Io(_) => CONFIG_ERROR_EXIT_CODE_V1,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct ConfigValidateReportV1 {
    value: Value,
}

impl ConfigValidateReportV1 {
    pub fn value(&self) -> &Value {
        &self.value
    }

    pub fn to_json(&self) -> String {
        serde_json::to_string(&self.value).expect("report value is JSON")
    }

    pub fn to_pretty_json(&self) -> String {
        serde_json::to_string_pretty(&self.value).expect("report value is JSON")
    }
}

#[derive(Clone, Debug, Deserialize)]
struct SchemaDocument {
    schema_version: u64,
    #[allow(dead_code)]
    source: String,
    #[allow(dead_code)]
    source_sha256: String,
    parameters: Vec<SchemaParameter>,
    #[serde(default)]
    #[allow(dead_code)]
    dynamic_patterns: Vec<DynamicPattern>,
}

#[derive(Clone, Debug, Deserialize)]
struct DynamicPattern {
    #[allow(dead_code)]
    name: String,
    #[allow(dead_code)]
    regex: String,
    #[allow(dead_code)]
    scan: String,
}

#[derive(Clone, Debug, Deserialize)]
struct SchemaParameter {
    key: String,
    #[allow(dead_code)]
    source_lines: Vec<u64>,
    #[allow(dead_code)]
    required_in_any_call: bool,
    #[allow(dead_code)]
    evaluate_strings_in_any_call: bool,
    calls: Vec<SchemaCall>,
}

#[derive(Clone, Debug, Deserialize)]
struct SchemaCall {
    key: String,
    source_line: u64,
    target: Option<String>,
    scale: f64,
    evaluate_strings: bool,
    required: bool,
    default_expression: Option<String>,
}

#[derive(Clone, Debug, Deserialize)]
struct ConsumptionRegistry {
    #[serde(rename = "IMPLEMENTED_PARAMETERS")]
    implemented_parameters: Vec<String>,
    #[serde(rename = "IMPLEMENTED_OPTIONS")]
    implemented_options: Vec<String>,
    #[serde(rename = "REPORT_ONLY_PARAMETERS")]
    report_only_parameters: Vec<String>,
    #[serde(rename = "REPORT_ONLY_OPTIONS")]
    report_only_options: Vec<String>,
    #[serde(rename = "UNIMPLEMENTED_PARAMETERS")]
    unimplemented_parameters: Vec<String>,
    #[serde(rename = "UNIMPLEMENTED_OPTIONS")]
    unimplemented_options: Vec<String>,
    #[serde(rename = "OBSOLETE_PARAMETERS")]
    obsolete_parameters: Vec<String>,
    #[serde(rename = "OBSOLETE_OPTIONS")]
    obsolete_options: Vec<String>,
    #[serde(rename = "_source_sha256")]
    #[allow(dead_code)]
    source_sha256: String,
}

#[derive(Clone, Debug)]
struct PackageBlockV1 {
    name: String,
    #[allow(dead_code)]
    rows: Vec<Vec<sipi_com::RawCellV1>>,
}

#[derive(Clone, Debug, PartialEq)]
struct PackageInventoryV1 {
    count: usize,
    warnings: Vec<String>,
}

#[derive(Clone, Debug, PartialEq)]
enum LookupValueV1 {
    Present(ResolvedDefaultV1),
    Missing,
}

pub fn config_validate_v1(
    request: &ConfigValidateRequestV1,
) -> Result<ConfigValidateReportV1, ConfigValidateErrorV1> {
    let profile = request.validate()?;
    let schema = load_schema()?;
    let _ = load_behavior_catalog()?;
    let registry = load_consumption_registry()?;
    let overrides = canonicalize_override_keys(&schema, parse_overrides(&request.overrides)?)?;
    let settings = load_settings(&request.config)?;
    let (main_rows, packages, package) = split_packages(&settings, &profile)?;
    validate_package_references(&main_rows, &packages)?;
    let materialized = materialize_r480(&schema, &main_rows, &packages, &overrides, &profile)?;
    validate_output_budget(&materialized.parameters, &materialized.options)?;
    let source_sha256 = sha256_file(&request.config)?;
    let path = canonical_or_absolute(&request.config);
    let parameters = materialized.parameters.len();
    let options = materialized.options.len();
    let summary = json!({
        "config": path,
        "parameters": parameters,
        "options": options,
        "package_blocks": package.count,
        "warnings": package.warnings,
        "profile": profile.name,
    });

    if request.materialized_json {
        let parameters_json = json_map(&materialized.parameters);
        let options_json = json_map(&materialized.options);
        let fingerprint = materialized_fingerprint(
            &parameters_json,
            &options_json,
            &materialized.integer_parameters,
            &materialized.integer_options,
        )?;
        return Ok(ConfigValidateReportV1 {
            value: json!({
                "schema_version": 1,
                "execution": {"performed": false, "runtime_reads": "not_run"},
                "config": {
                    "path": canonical_or_absolute(&request.config),
                    "sha256": source_sha256,
                    "profile": profile.name,
                },
                "materialized_fingerprint": fingerprint,
                "materialized": {
                    "parameters": parameters_json,
                    "options": options_json,
                },
                "warnings": package.warnings,
                "config_consumption": consumption_report(
                    &materialized.parameters,
                    &materialized.options,
                    &registry,
                ),
            }),
        });
    }
    if request.json {
        return Ok(ConfigValidateReportV1 { value: summary });
    }
    let config = summary
        .get("config")
        .and_then(Value::as_str)
        .unwrap_or_default();
    Ok(ConfigValidateReportV1 {
        value: json!({
            "text": format!("valid: {config} ({parameters} parameters, {options} options)"),
        }),
    })
}

fn load_schema() -> Result<SchemaDocument, ConfigValidateErrorV1> {
    verify_bytes(SCHEMA_BYTES, SCHEMA_SHA256, "r480-config.schema.yaml")?;
    let document: SchemaDocument = serde_yaml::from_slice(SCHEMA_BYTES).map_err(|error| {
        ConfigValidateErrorV1::Workbook(format!("invalid embedded schema: {error}"))
    })?;
    if document.schema_version != 1 {
        return Err(ConfigValidateErrorV1::Workbook(
            "unsupported embedded r4.80 schema version".to_owned(),
        ));
    }
    Ok(document)
}

fn load_behavior_catalog() -> Result<Value, ConfigValidateErrorV1> {
    verify_bytes(BEHAVIOR_BYTES, BEHAVIOR_SHA256, "behavior-presets.yaml")?;
    serde_yaml::from_slice(BEHAVIOR_BYTES).map_err(|error| {
        ConfigValidateErrorV1::Workbook(format!("invalid behavior catalog: {error}"))
    })
}

fn load_consumption_registry() -> Result<ConsumptionRegistry, ConfigValidateErrorV1> {
    verify_bytes(
        REGISTRY_BYTES,
        REGISTRY_SHA256,
        "consumption-registry.v1.json",
    )?;
    serde_json::from_slice(REGISTRY_BYTES).map_err(|error| {
        ConfigValidateErrorV1::Workbook(format!("invalid consumption registry: {error}"))
    })
}

fn verify_bytes(bytes: &[u8], expected: &str, name: &str) -> Result<(), ConfigValidateErrorV1> {
    let actual = format!("{:x}", Sha256::digest(bytes));
    if actual != expected {
        return Err(ConfigValidateErrorV1::Workbook(format!(
            "embedded {name} hash mismatch"
        )));
    }
    Ok(())
}

fn materialize_r480(
    schema: &SchemaDocument,
    rows: &[Vec<sipi_com::RawCellV1>],
    packages: &[PackageBlockV1],
    overrides: &BTreeMap<String, String>,
    profile: &ValidatedProfileV1,
) -> Result<MaterializedV1, ConfigValidateErrorV1> {
    let mut calls: Vec<&SchemaCall> = schema
        .parameters
        .iter()
        .flat_map(|entry| entry.calls.iter())
        .filter(|call| call.target.is_some())
        .collect();
    calls.sort_by_key(|call| call.source_line);
    let mut parameters = BTreeMap::new();
    let mut integer_parameters = BTreeSet::new();
    let mut options = BTreeMap::from([
        ("TDMODE".to_owned(), ResolvedDefaultV1::Boolean(false)),
        ("GET_FD".to_owned(), ResolvedDefaultV1::Boolean(true)),
        (
            "CONFIG2MAT_ONLY".to_owned(),
            ResolvedDefaultV1::Boolean(false),
        ),
    ]);
    let mut integer_options = BTreeSet::new();
    for call in calls {
        let Some(target) = call.target.as_deref() else {
            continue;
        };
        if target.starts_with("param_struct.") {
            continue;
        }
        let (kind, field) = if let Some(field) = target.strip_prefix("param.") {
            ("parameters", field)
        } else if let Some(field) = target.strip_prefix("OP.") {
            ("options", field)
        } else {
            continue;
        };
        let value = call_value(
            rows,
            call,
            &parameters,
            &options,
            &integer_parameters,
            &integer_options,
            overrides,
        )?;
        let value = scale_value(value, call.scale)
            .map_err(|error| ConfigValidateErrorV1::Workbook(format!("{}: {error}", call.key)))?;
        let scalar_encoding = value.scalar_encoding;
        let value = value.value;
        if call.key == "b_max(1)" {
            parameters.insert("_bmax_first".to_owned(), value.clone());
            record_scalar_encoding(&mut integer_parameters, "_bmax_first", scalar_encoding);
        }
        if call.key == "b_min(1)" {
            parameters.insert("_bmin_first".to_owned(), value.clone());
            record_scalar_encoding(&mut integer_parameters, "_bmin_first", scalar_encoding);
        }
        if kind == "parameters" {
            parameters.insert(field.to_owned(), value);
            record_scalar_encoding(&mut integer_parameters, field, scalar_encoding);
        } else {
            options.insert(field.to_owned(), value);
            record_scalar_encoding(&mut integer_options, field, scalar_encoding);
        }
        validate_output_budget(&parameters, &options)?;
    }
    finalize_r480(
        &mut parameters,
        &mut options,
        &mut integer_parameters,
        &mut integer_options,
        schema,
        packages,
        overrides,
        profile,
    )?;
    Ok(MaterializedV1 {
        parameters,
        options,
        integer_parameters,
        integer_options,
    })
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum ScalarEncodingV1 {
    Integer,
    Float,
}

#[derive(Clone, Debug)]
struct ResolvedValueV1 {
    value: ResolvedDefaultV1,
    scalar_encoding: Option<ScalarEncodingV1>,
}

#[derive(Clone, Debug)]
struct MaterializedV1 {
    parameters: BTreeMap<String, ResolvedDefaultV1>,
    options: BTreeMap<String, ResolvedDefaultV1>,
    integer_parameters: BTreeSet<String>,
    integer_options: BTreeSet<String>,
}

fn record_scalar_encoding(
    integer_keys: &mut BTreeSet<String>,
    key: &str,
    encoding: Option<ScalarEncodingV1>,
) {
    if encoding == Some(ScalarEncodingV1::Integer) {
        integer_keys.insert(key.to_owned());
    } else {
        integer_keys.remove(key);
    }
}

fn call_value(
    rows: &[Vec<sipi_com::RawCellV1>],
    call: &SchemaCall,
    parameters: &BTreeMap<String, ResolvedDefaultV1>,
    options: &BTreeMap<String, ResolvedDefaultV1>,
    integer_parameters: &BTreeSet<String>,
    integer_options: &BTreeSet<String>,
    overrides: &BTreeMap<String, String>,
) -> Result<ResolvedValueV1, ConfigValidateErrorV1> {
    if let Some(raw) = overrides.get(&call.key) {
        if let Ok(parsed) = parse_literal_v1(raw) {
            let value = parsed.to_resolved();
            return Ok(ResolvedValueV1 {
                scalar_encoding: override_scalar_encoding(rows, &call.key, &value)?,
                value,
            });
        }
        return Ok(ResolvedValueV1 {
            value: ResolvedDefaultV1::String(raw.clone()),
            scalar_encoding: None,
        });
    }
    match lookup_value(rows, &call.key)? {
        LookupValueV1::Present(value) => {
            if call.evaluate_strings
                && let ResolvedDefaultV1::String(text) = value
            {
                return parse_literal_v1(&text)
                    .map(|literal| ResolvedValueV1 {
                        value: literal.to_resolved(),
                        scalar_encoding: None,
                    })
                    .map_err(|error| {
                        ConfigValidateErrorV1::Workbook(format!(
                            "invalid MATLAB literal for {}: {error:?}",
                            call.key
                        ))
                    });
            }
            Ok(ResolvedValueV1 {
                value,
                scalar_encoding: source_scalar_encoding(rows, &call.key, call.evaluate_strings)?,
            })
        }
        LookupValueV1::Missing => {
            if call.required || call.default_expression.is_none() {
                return Err(ConfigValidateErrorV1::Workbook(format!(
                    "missing required configuration parameter: {}",
                    call.key
                )));
            }
            resolve_default(
                call.default_expression.as_deref().unwrap_or_default(),
                parameters,
                options,
                integer_parameters,
                integer_options,
            )
        }
    }
}

fn override_scalar_encoding(
    rows: &[Vec<sipi_com::RawCellV1>],
    key: &str,
    value: &ResolvedDefaultV1,
) -> Result<Option<ScalarEncodingV1>, ConfigValidateErrorV1> {
    let Some(cell) = lookup_source_cell(rows, key)? else {
        return Ok(None);
    };
    let is_source_integer = matches!(cell.value(), CellValueV1::Integer(_));
    let is_integer_literal =
        as_scalar(value).is_some_and(|value| value.is_finite() && value.fract() == 0.0);
    Ok((is_source_integer && is_integer_literal).then_some(ScalarEncodingV1::Integer))
}

fn source_scalar_encoding(
    rows: &[Vec<sipi_com::RawCellV1>],
    key: &str,
    evaluate_strings: bool,
) -> Result<Option<ScalarEncodingV1>, ConfigValidateErrorV1> {
    let Some(cell) = lookup_source_cell(rows, key)? else {
        return Ok(None);
    };
    Ok(match cell.value() {
        CellValueV1::Integer(_) => Some(ScalarEncodingV1::Integer),
        CellValueV1::Number(_) => Some(ScalarEncodingV1::Float),
        CellValueV1::String(text) if evaluate_strings => {
            parse_literal_v1(text).ok().and_then(|literal| {
                matches!(literal, LiteralV1::Scalar(_)).then_some(ScalarEncodingV1::Float)
            })
        }
        _ => None,
    })
}

fn resolve_default(
    expression: &str,
    parameters: &BTreeMap<String, ResolvedDefaultV1>,
    options: &BTreeMap<String, ResolvedDefaultV1>,
    integer_parameters: &BTreeSet<String>,
    integer_options: &BTreeSet<String>,
) -> Result<ResolvedValueV1, ConfigValidateErrorV1> {
    let expression = expression.trim();
    if expression == "-param.bmax(1)" {
        let value = parameters
            .get("_bmax_first")
            .or_else(|| parameters.get("bmax"))
            .and_then(as_scalar)
            .ok_or_else(|| {
                ConfigValidateErrorV1::Workbook(
                    "default expression requires scalar param.bmax(1)".to_owned(),
                )
            })?;
        return Ok(ResolvedValueV1 {
            value: ResolvedDefaultV1::Scalar(-value),
            scalar_encoding: Some(ScalarEncodingV1::Float),
        });
    }
    if expression == "-1*param.bmax(2:param.ndfe)" {
        let count = bounded_count(parameters.get("ndfe"), "N_b", 0)?;
        if count <= 1 {
            return Ok(ResolvedValueV1 {
                value: ResolvedDefaultV1::Empty,
                scalar_encoding: None,
            });
        }
        let first = parameters
            .get("_bmax_first")
            .and_then(as_scalar)
            .ok_or_else(|| {
                ConfigValidateErrorV1::Workbook(
                    "default expression requires bmax first element".to_owned(),
                )
            })?;
        let rest = parameters.get("bmax").ok_or_else(|| {
            ConfigValidateErrorV1::Workbook("default expression requires bmax values".to_owned())
        })?;
        let mut values = vec![first];
        match rest {
            ResolvedDefaultV1::Scalar(value) => {
                values.extend(std::iter::repeat_n(*value, count - 1))
            }
            ResolvedDefaultV1::Vector(tail) => values.extend(tail.iter().copied()),
            _ => {
                return Err(ConfigValidateErrorV1::Workbook(
                    "default expression requires numeric bmax values".to_owned(),
                ));
            }
        }
        if values.len() < count {
            return Err(ConfigValidateErrorV1::Workbook(
                "default expression requires bmax values through N_b".to_owned(),
            ));
        }
        return Ok(ResolvedValueV1 {
            value: ResolvedDefaultV1::Vector(
                values
                    .into_iter()
                    .skip(1)
                    .take(count - 1)
                    .map(|value| -value)
                    .collect(),
            ),
            scalar_encoding: None,
        });
    }
    if expression.starts_with('\'') && expression.ends_with('\'') && expression.len() >= 2 {
        let inner = expression[1..expression.len() - 1].replace("''", "'");
        return Ok(ResolvedValueV1 {
            value: parse_literal_v1(&inner)
                .map(|literal| literal.to_resolved())
                .unwrap_or(ResolvedDefaultV1::String(inner)),
            scalar_encoding: None,
        });
    }
    if let Some((namespace, field)) = direct_default_reference(expression) {
        let (values, integer_keys) = if namespace == "param" {
            (parameters, integer_parameters)
        } else {
            (options, integer_options)
        };
        if let Some(value) = values.get(field) {
            return Ok(ResolvedValueV1 {
                value: value.clone(),
                scalar_encoding: if integer_keys.contains(field) {
                    Some(ScalarEncodingV1::Integer)
                } else {
                    None
                },
            });
        }
    }
    validate_materialized_storage_budget(parameters, options)?;
    let mut parameters_hash = HashMap::new();
    parameters_hash.extend(
        parameters
            .iter()
            .map(|(key, value)| (key.clone(), value.clone())),
    );
    let mut options_hash = HashMap::new();
    options_hash.extend(
        options
            .iter()
            .map(|(key, value)| (key.clone(), value.clone())),
    );
    let normalized = expression.replace("(1)", "").replace("( 1 )", "");
    let value = resolve_default_value_v1(&normalized, &parameters_hash, &options_hash).map_err(
        |error| {
            ConfigValidateErrorV1::Workbook(format!(
                "cannot resolve default {expression:?}: {error:?}"
            ))
        },
    )?;
    Ok(ResolvedValueV1 {
        value,
        scalar_encoding: Some(ScalarEncodingV1::Float),
    })
}

fn direct_default_reference(expression: &str) -> Option<(&str, &str)> {
    let (namespace, field) = expression.trim().split_once('.')?;
    if namespace != "param" && namespace != "OP" {
        return None;
    }
    let field = field.trim_end_matches("(1)").trim();
    (!field.is_empty()
        && field
            .chars()
            .all(|character| character.is_ascii_alphanumeric() || character == '_'))
    .then_some((namespace, field))
}

fn scale_value(
    value: ResolvedValueV1,
    scale: f64,
) -> Result<ResolvedValueV1, ConfigValidateErrorV1> {
    if scale == 1.0 {
        validate_resolved_value(&value.value, "configuration value")?;
        return Ok(value);
    }
    if !scale.is_finite() {
        return Err(ConfigValidateErrorV1::Workbook(
            "configuration scale must be finite".to_owned(),
        ));
    }
    let scaled = match value.value {
        ResolvedDefaultV1::Scalar(value) => ResolvedDefaultV1::Scalar(value * scale),
        ResolvedDefaultV1::Vector(values) => {
            ResolvedDefaultV1::Vector(values.into_iter().map(|value| value * scale).collect())
        }
        ResolvedDefaultV1::Matrix(rows) => ResolvedDefaultV1::Matrix(
            rows.into_iter()
                .map(|row| row.into_iter().map(|value| value * scale).collect())
                .collect(),
        ),
        other @ (ResolvedDefaultV1::Boolean(_)
        | ResolvedDefaultV1::String(_)
        | ResolvedDefaultV1::Empty) => other,
    };
    validate_resolved_value(&scaled, "scaled configuration value")?;
    let scalar_encoding = if matches!(scaled, ResolvedDefaultV1::Scalar(_)) {
        Some(ScalarEncodingV1::Float)
    } else {
        None
    };
    Ok(ResolvedValueV1 {
        value: scaled,
        scalar_encoding,
    })
}

#[allow(clippy::too_many_arguments)]
fn finalize_r480(
    parameters: &mut BTreeMap<String, ResolvedDefaultV1>,
    options: &mut BTreeMap<String, ResolvedDefaultV1>,
    integer_parameters: &mut BTreeSet<String>,
    integer_options: &mut BTreeSet<String>,
    schema: &SchemaDocument,
    packages: &[PackageBlockV1],
    overrides: &BTreeMap<String, String>,
    profile: &ValidatedProfileV1,
) -> Result<(), ConfigValidateErrorV1> {
    if truthy(options.get("FORCE_TR")) {
        options.insert("T_r_meas_point".to_owned(), ResolvedDefaultV1::Scalar(0.0));
        options.insert("T_r_filter_type".to_owned(), ResolvedDefaultV1::Scalar(1.0));
        record_scalar_encoding(
            integer_options,
            "T_r_meas_point",
            Some(ScalarEncodingV1::Integer),
        );
        record_scalar_encoding(
            integer_options,
            "T_r_filter_type",
            Some(ScalarEncodingV1::Integer),
        );
    }
    if truthy(options.get("WC_PORTZ")) {
        options.insert("TDR".to_owned(), ResolvedDefaultV1::Scalar(1.0));
        record_scalar_encoding(integer_options, "TDR", Some(ScalarEncodingV1::Integer));
    }
    transpose_package_fields(parameters)?;
    expand_package_fields(parameters)?;
    apply_selected_package_blocks(parameters, schema, packages, overrides)?;
    assemble_dfe_limits(parameters)?;
    parameter_size_adjustment(parameters, options)?;
    validate_gqual(parameters)?;
    derive_core_parameters(parameters, integer_parameters)?;
    if is_nonempty(parameters.get("f_HP_Z")) {
        parameters.insert(
            "CTLE_type".to_owned(),
            ResolvedDefaultV1::String("CL120e".to_owned()),
        );
    } else if is_nonempty(parameters.get("g_DC_HP_values")) {
        parameters.insert(
            "CTLE_type".to_owned(),
            ResolvedDefaultV1::String("CL120d".to_owned()),
        );
    }
    if matches!(parameters.get("CTLE_type"), Some(ResolvedDefaultV1::String(value)) if value == "CL120e")
        && let (Some(fz), Some(gdc)) = (
            as_vector(parameters.get("CTLE_fz")),
            as_vector(parameters.get("ctle_gdc_values")),
        )
    {
        let values = fz
            .iter()
            .zip(gdc.iter())
            .map(|(value, gain)| value / 10f64.powf(gain / 20.0))
            .collect();
        parameters.insert("CTLE_fz".to_owned(), ResolvedDefaultV1::Vector(values));
    }
    if matches!(options.get("PHY"), Some(ResolvedDefaultV1::String(value)) if value.eq_ignore_ascii_case("c2m"))
    {
        options.insert("EW".to_owned(), ResolvedDefaultV1::Boolean(true));
    } else {
        parameters.insert("T_O".to_owned(), ResolvedDefaultV1::Scalar(0.0));
        record_scalar_encoding(integer_parameters, "T_O", Some(ScalarEncodingV1::Integer));
    }
    if parameters
        .get("Gx")
        .and_then(as_scalar)
        .is_some_and(|value| value as i64 == 1)
    {
        parameters.insert("Grr".to_owned(), ResolvedDefaultV1::Scalar(2.0));
        record_scalar_encoding(integer_parameters, "Grr", Some(ScalarEncodingV1::Integer));
    }
    let pre = parameters
        .get("ffe_pre_tap_len")
        .and_then(as_scalar)
        .unwrap_or(0.0);
    let post = parameters
        .get("ffe_post_tap_len")
        .and_then(as_scalar)
        .unwrap_or(0.0);
    let step = parameters
        .get("ffe_tap_step_size")
        .and_then(as_scalar)
        .unwrap_or(0.0);
    bounded_integer(pre, "ffe_pre_tap_len", 0)?;
    bounded_integer(post, "ffe_post_tap_len", 0)?;
    let nbg = parameters.get("N_bg").and_then(as_scalar).unwrap_or(0.0);
    let nbg_count = bounded_integer(nbg, "N_bg", 0)?;
    parameters.insert("RxFFE_cmx".to_owned(), ResolvedDefaultV1::Scalar(pre));
    parameters.insert("RxFFE_cpx".to_owned(), ResolvedDefaultV1::Scalar(post));
    parameters.insert("RxFFE_stepz".to_owned(), ResolvedDefaultV1::Scalar(step));
    record_scalar_encoding(
        integer_parameters,
        "RxFFE_cmx",
        Some(ScalarEncodingV1::Integer),
    );
    record_scalar_encoding(
        integer_parameters,
        "RxFFE_cpx",
        Some(ScalarEncodingV1::Integer),
    );
    record_scalar_encoding(
        integer_parameters,
        "RxFFE_stepz",
        Some(ScalarEncodingV1::Float),
    );
    options.insert(
        "RxFFE".to_owned(),
        ResolvedDefaultV1::Boolean(pre != 0.0 || post != 0.0),
    );
    let rxffe = truthy(options.get("RxFFE"));
    parameters.insert(
        "Floating_RXFFE".to_owned(),
        ResolvedDefaultV1::Boolean(rxffe && nbg_count > 0),
    );
    parameters.insert(
        "Floating_DFE".to_owned(),
        ResolvedDefaultV1::Boolean(!rxffe && nbg_count > 0),
    );
    if truthy(options.get("dynamic_txffe")) {
        for field in [
            "tx_ffe_cm4_values",
            "tx_ffe_cp2_values",
            "tx_ffe_cp3_values",
        ] {
            parameters.remove(field);
        }
    }
    let _ = profile;
    Ok(())
}

fn materialize_package_r480(
    schema: &SchemaDocument,
    package: &PackageBlockV1,
    overrides: &BTreeMap<String, String>,
) -> Result<BTreeMap<String, ResolvedDefaultV1>, ConfigValidateErrorV1> {
    let mut calls: Vec<&SchemaCall> = schema
        .parameters
        .iter()
        .flat_map(|entry| entry.calls.iter())
        .filter(|call| {
            call.target
                .as_deref()
                .is_some_and(|target| target.starts_with("param_struct."))
        })
        .collect();
    calls.sort_by_key(|call| call.source_line);
    let mut parameters = BTreeMap::new();
    let empty_integer_keys = BTreeSet::new();
    for call in calls {
        let value = scale_value(
            call_value(
                &package.rows,
                call,
                &parameters,
                &BTreeMap::new(),
                &empty_integer_keys,
                &empty_integer_keys,
                overrides,
            )?,
            call.scale,
        )
        .map_err(|error| ConfigValidateErrorV1::Workbook(format!("{}: {error}", call.key)))?;
        let field = call
            .target
            .as_deref()
            .and_then(|target| target.strip_prefix("param_struct."))
            .ok_or_else(|| ConfigValidateErrorV1::Workbook("invalid package target".to_owned()))?;
        parameters.insert(field.to_owned(), value.value);
        validate_output_budget(&parameters, &BTreeMap::new())?;
    }
    transpose_package_fields(&mut parameters)?;
    expand_package_fields(&mut parameters)?;
    Ok(parameters)
}

fn apply_selected_package_blocks(
    parameters: &mut BTreeMap<String, ResolvedDefaultV1>,
    schema: &SchemaDocument,
    packages: &[PackageBlockV1],
    overrides: &BTreeMap<String, String>,
) -> Result<(), ConfigValidateErrorV1> {
    let Some(ResolvedDefaultV1::String(raw_names)) = parameters.get("PKG_NAME").cloned() else {
        return Ok(());
    };
    let names = raw_names.split_whitespace().collect::<Vec<_>>();
    if names.is_empty() {
        return Ok(());
    }
    let tx_name = names[0];
    let rx_name = names.get(1).copied().unwrap_or(tx_name);
    let find_last = |name: &str| packages.iter().rev().find(|package| package.name == name);
    let tx = find_last(tx_name).ok_or_else(|| {
        ConfigValidateErrorV1::Workbook(format!("missing package block {tx_name:?}"))
    })?;
    let rx = find_last(rx_name).ok_or_else(|| {
        ConfigValidateErrorV1::Workbook(format!("missing package block {rx_name:?}"))
    })?;
    let tx_values = materialize_package_r480(schema, tx, overrides)?;
    let rx_values = materialize_package_r480(schema, rx, overrides)?;
    for field in ["C_pkg_board", "R_diepad"] {
        let tx_value = tx_values.get(field).ok_or_else(|| {
            ConfigValidateErrorV1::Workbook(format!("package {tx_name:?} missing {field}"))
        })?;
        let rx_value = rx_values.get(field).ok_or_else(|| {
            ConfigValidateErrorV1::Workbook(format!("package {rx_name:?} missing {field}"))
        })?;
        parameters.insert(
            field.to_owned(),
            ResolvedDefaultV1::Vector(vec![
                linear_element(tx_value, 1, field, tx_name)?,
                linear_element(rx_value, 2, field, rx_name)?,
            ]),
        );
    }
    let tx_zc = as_matrix(tx_values.get("pkg_Z_c")).ok_or_else(|| {
        ConfigValidateErrorV1::Workbook("selected package_Z_c must be a matrix".to_owned())
    })?;
    let rx_zc = as_matrix(rx_values.get("pkg_Z_c")).ok_or_else(|| {
        ConfigValidateErrorV1::Workbook("selected package_Z_c must be a matrix".to_owned())
    })?;
    if tx_zc.is_empty() || rx_zc.len() < 2 {
        return Err(ConfigValidateErrorV1::Workbook(
            "selected package_Z_c must provide TX row 1 and RX row 2".to_owned(),
        ));
    }
    parameters.insert(
        "pkg_Z_c".to_owned(),
        ResolvedDefaultV1::Matrix(vec![tx_zc[0].clone(), rx_zc[1].clone()]),
    );
    for field in [
        "z_p_tx_cases",
        "z_p_fext_cases",
        "pkg_gamma0_a1_a2",
        "pkg_tau",
        "a_thru",
        "a_fext",
    ] {
        if let Some(value) = tx_values.get(field) {
            parameters.insert(field.to_owned(), value.clone());
        }
    }
    for field in ["z_p_rx_cases", "a_next", "z_p_next_cases"] {
        if let Some(value) = rx_values.get(field) {
            parameters.insert(field.to_owned(), value.clone());
        }
    }
    Ok(())
}

fn linear_element(
    value: &ResolvedDefaultV1,
    index: usize,
    field: &str,
    package_name: &str,
) -> Result<f64, ConfigValidateErrorV1> {
    let mut values = Vec::new();
    match value {
        ResolvedDefaultV1::Scalar(value) => values.push(*value),
        ResolvedDefaultV1::Vector(values_ref) => values.extend(values_ref.iter().copied()),
        ResolvedDefaultV1::Matrix(rows) => {
            let columns = rows.first().map_or(0, Vec::len);
            if rows.iter().any(|row| row.len() != columns) {
                return Err(ConfigValidateErrorV1::Workbook(format!(
                    "selected package {package_name:?} field {field:?} is not rectangular"
                )));
            }
            for column in 0..columns {
                for row in rows {
                    values.push(row[column]);
                }
            }
        }
        _ => {}
    }
    values.get(index.saturating_sub(1)).copied().ok_or_else(|| {
        ConfigValidateErrorV1::Workbook(format!(
            "selected package block {package_name:?} field {field:?} must provide MATLAB element {index}"
        ))
    })
}

fn transpose_package_fields(
    parameters: &mut BTreeMap<String, ResolvedDefaultV1>,
) -> Result<(), ConfigValidateErrorV1> {
    for field in [
        "z_p_tx_cases",
        "z_p_next_cases",
        "z_p_fext_cases",
        "z_p_rx_cases",
        "pkg_Z_c",
    ] {
        let Some(value) = parameters.get(field).cloned() else {
            continue;
        };
        let ResolvedDefaultV1::Matrix(rows) = value else {
            continue;
        };
        if rows.is_empty() {
            continue;
        }
        let width = rows[0].len();
        if rows.iter().any(|row| row.len() != width) {
            return Err(ConfigValidateErrorV1::Workbook(format!(
                "{field} must be a rectangular matrix"
            )));
        }
        let transposed = (0..width)
            .map(|column| rows.iter().map(|row| row[column]).collect::<Vec<_>>())
            .collect::<Vec<_>>();
        parameters.insert(field.to_owned(), ResolvedDefaultV1::Matrix(transposed));
    }
    Ok(())
}

fn expand_package_fields(
    parameters: &mut BTreeMap<String, ResolvedDefaultV1>,
) -> Result<(), ConfigValidateErrorV1> {
    let Some(ResolvedDefaultV1::Matrix(package_zc)) = parameters.get("pkg_Z_c").cloned() else {
        return Ok(());
    };
    let columns = package_zc.first().map_or(0, Vec::len);
    if columns != 2 {
        return Ok(());
    }
    let mut expanded_zc = package_zc;
    for row in &mut expanded_zc {
        row.extend([100.0, 100.0]);
    }
    parameters.insert("pkg_Z_c".to_owned(), ResolvedDefaultV1::Matrix(expanded_zc));
    for field in [
        "z_p_tx_cases",
        "z_p_next_cases",
        "z_p_fext_cases",
        "z_p_rx_cases",
    ] {
        if let Some(ResolvedDefaultV1::Matrix(rows)) = parameters.get(field).cloned() {
            let mut expanded = rows;
            for row in &mut expanded {
                row.extend([0.0, 0.0]);
            }
            parameters.insert(field.to_owned(), ResolvedDefaultV1::Matrix(expanded));
        }
    }
    Ok(())
}

fn assemble_dfe_limits(
    parameters: &mut BTreeMap<String, ResolvedDefaultV1>,
) -> Result<(), ConfigValidateErrorV1> {
    let count = bounded_count(parameters.get("ndfe"), "N_b", 0)?;
    for name in ["bmax", "bmin"] {
        let first = parameters.remove(&format!("_{name}_first"));
        let Some(first) = first else {
            continue;
        };
        let first = as_scalar(&first).ok_or_else(|| {
            ConfigValidateErrorV1::Workbook(format!("{name}(1) must resolve to a scalar"))
        })?;
        if count == 0 {
            parameters.insert(name.to_owned(), ResolvedDefaultV1::Empty);
        } else if count == 1 {
            parameters.insert(name.to_owned(), ResolvedDefaultV1::Vector(vec![first]));
        } else {
            let Some(rest) = parameters.get(name).cloned() else {
                return Err(ConfigValidateErrorV1::Workbook(format!(
                    "{name}(2..N_b) is missing"
                )));
            };
            let mut tail = match rest {
                ResolvedDefaultV1::Scalar(value) => vec![value; count - 1],
                ResolvedDefaultV1::Vector(values) => values,
                _ => {
                    return Err(ConfigValidateErrorV1::Workbook(format!(
                        "{name}(2..N_b) must be numeric"
                    )));
                }
            };
            if tail.len() == 1 {
                tail = vec![tail[0]; count - 1];
            }
            if tail.len() != count - 1 {
                return Err(ConfigValidateErrorV1::Workbook(format!(
                    "R480-CONFIG-DFE-TAIL-SHAPE: {name}(2..N_b) length mismatch"
                )));
            }
            let mut result = vec![first];
            result.append(&mut tail);
            parameters.insert(name.to_owned(), ResolvedDefaultV1::Vector(result));
        }
    }
    Ok(())
}

fn parameter_size_adjustment(
    parameters: &mut BTreeMap<String, ResolvedDefaultV1>,
    options: &BTreeMap<String, ResolvedDefaultV1>,
) -> Result<(), ConfigValidateErrorV1> {
    fn broadcast(
        parameters: &mut BTreeMap<String, ResolvedDefaultV1>,
        fields: &[&str],
        len: usize,
    ) -> Result<(), ConfigValidateErrorV1> {
        if len > MAX_NUMERIC_ELEMENTS {
            return Err(ConfigValidateErrorV1::Workbook(
                "materialized broadcast exceeds numeric-element budget".to_owned(),
            ));
        }
        for field in fields {
            match parameters.get(*field).cloned() {
                Some(ResolvedDefaultV1::Scalar(value)) => {
                    parameters.insert(
                        (*field).to_owned(),
                        ResolvedDefaultV1::Vector(vec![value; len]),
                    );
                }
                Some(ResolvedDefaultV1::Vector(values)) if values.len() == 1 => {
                    parameters.insert(
                        (*field).to_owned(),
                        ResolvedDefaultV1::Vector(vec![values[0]; len]),
                    );
                }
                _ => {}
            }
        }
        validate_output_budget(parameters, &BTreeMap::new())
    }
    broadcast(
        parameters,
        &[
            "C_pkg_board",
            "C_diepad",
            "L_comp",
            "C_bump",
            "tfx",
            "C_v",
            "C_0",
            "C_1",
            "pkg_Z_c",
            "brd_Z_c",
            "R_diepad",
        ],
        2,
    )?;
    let tx_rows = as_matrix(parameters.get("z_p_tx_cases"))
        .map(|rows| rows.len())
        .unwrap_or(1);
    broadcast(parameters, &["AC_CM_RMS"], tx_rows)?;
    let gdc_len = as_vector(parameters.get("ctle_gdc_values"))
        .map(|values| values.len())
        .unwrap_or(1);
    broadcast(
        parameters,
        &["CTLE_fp1", "CTLE_fp2", "CTLE_fz", "f_HP_Z", "f_HP_P"],
        gdc_len,
    )?;
    let hp_len = as_vector(parameters.get("g_DC_HP_values"))
        .map(|values| values.len())
        .unwrap_or(1);
    broadcast(parameters, &["f_HP"], hp_len)?;
    let wc = truthy(options.get("WC_PORTZ"));
    let pkg_selections = as_vector(options.get("pkg_len_select")).unwrap_or_else(|| vec![1.0]);
    if pkg_selections.is_empty() {
        return Err(ConfigValidateErrorV1::Workbook(
            "z_p select must contain positive MATLAB package indices".to_owned(),
        ));
    }
    let pkg_len = pkg_selections
        .into_iter()
        .map(|value| bounded_integer(value, "z_p select", 1))
        .collect::<Result<Vec<_>, _>>()?
        .into_iter()
        .max()
        .unwrap_or(1);
    broadcast(
        parameters,
        &["a_thru", "a_fext", "a_next", "SNDR"],
        if wc { 2 } else { pkg_len },
    )?;
    Ok(())
}

fn validate_gqual(
    parameters: &BTreeMap<String, ResolvedDefaultV1>,
) -> Result<(), ConfigValidateErrorV1> {
    let gqual = parameters.get("gqual");
    let g2qual = parameters.get("g2qual");
    if gqual.is_none() || g2qual.is_none() || (!is_nonempty(gqual) && !is_nonempty(g2qual)) {
        return Ok(());
    }
    let matrix = as_matrix(gqual).ok_or_else(|| {
        ConfigValidateErrorV1::Workbook("G_Qual must be an N-by-2 matrix".to_owned())
    })?;
    let rows = matrix.len();
    let cols = matrix.first().map_or(0, Vec::len);
    let length = as_vector(g2qual).map_or(0, |values| values.len());
    if cols != 2 || rows != length {
        return Err(ConfigValidateErrorV1::Workbook(
            "G_Qual row count must equal G2_Qual length".to_owned(),
        ));
    }
    Ok(())
}

fn derive_core_parameters(
    parameters: &mut BTreeMap<String, ResolvedDefaultV1>,
    integer_parameters: &mut BTreeSet<String>,
) -> Result<(), ConfigValidateErrorV1> {
    let fb = parameters.get("fb").and_then(as_scalar).ok_or_else(|| {
        ConfigValidateErrorV1::Workbook("f_b must yield a positive finite baud rate".to_owned())
    })?;
    let m = parameters
        .get("samples_per_ui")
        .and_then(as_scalar)
        .ok_or_else(|| {
            ConfigValidateErrorV1::Workbook("M must be a positive even integer".to_owned())
        })?;
    let levels = parameters
        .get("levels")
        .and_then(as_scalar)
        .ok_or_else(|| ConfigValidateErrorV1::Workbook("L must be at least two".to_owned()))?;
    let fr = parameters.get("f_r").and_then(as_scalar).unwrap_or(4.0);
    let samples_per_ui = bounded_integer(m, "M", 1)?;
    let levels_count = bounded_integer(levels, "L", 2)?;
    if !fb.is_finite() || fb <= 0.0 || samples_per_ui % 2 != 0 || !fr.is_finite() {
        return Err(ConfigValidateErrorV1::Workbook(
            "invalid r4.80 core timing values".to_owned(),
        ));
    }
    let m = samples_per_ui as f64;
    let levels = levels_count as f64;
    let ui = 1.0 / fb;
    parameters.insert("ui".to_owned(), ResolvedDefaultV1::Scalar(ui));
    record_scalar_encoding(integer_parameters, "ui", Some(ScalarEncodingV1::Float));
    parameters.insert("sample_dt".to_owned(), ResolvedDefaultV1::Scalar(ui / m));
    record_scalar_encoding(
        integer_parameters,
        "sample_dt",
        Some(ScalarEncodingV1::Float),
    );
    parameters.insert(
        "sigma_X".to_owned(),
        ResolvedDefaultV1::Scalar(
            ((levels * levels - 1.0) / (3.0 * (levels - 1.0).powi(2))).sqrt(),
        ),
    );
    record_scalar_encoding(integer_parameters, "sigma_X", Some(ScalarEncodingV1::Float));
    parameters.insert(
        "fb_BT_cutoff".to_owned(),
        ResolvedDefaultV1::Scalar(0.473037 * fr),
    );
    record_scalar_encoding(
        integer_parameters,
        "fb_BT_cutoff",
        Some(ScalarEncodingV1::Float),
    );
    parameters.insert("fb_BW_cutoff".to_owned(), ResolvedDefaultV1::Scalar(fr));
    record_scalar_encoding(
        integer_parameters,
        "fb_BW_cutoff",
        Some(ScalarEncodingV1::Float),
    );
    parameters.insert("Tx_rd_sel".to_owned(), ResolvedDefaultV1::Scalar(1.0));
    parameters.insert("Rx_rd_sel".to_owned(), ResolvedDefaultV1::Scalar(2.0));
    record_scalar_encoding(
        integer_parameters,
        "Tx_rd_sel",
        Some(ScalarEncodingV1::Integer),
    );
    record_scalar_encoding(
        integer_parameters,
        "Rx_rd_sel",
        Some(ScalarEncodingV1::Integer),
    );
    Ok(())
}

fn lookup_value(
    rows: &[Vec<sipi_com::RawCellV1>],
    key: &str,
) -> Result<LookupValueV1, ConfigValidateErrorV1> {
    let Some(value) = lookup_source_cell(rows, key)? else {
        return Ok(LookupValueV1::Missing);
    };
    if matches!(value.value(), CellValueV1::None) {
        return Err(ConfigValidateErrorV1::Workbook(format!(
            "{key}: right-hand value"
        )));
    }
    if matches!(value.value(), CellValueV1::Number(value) if value.is_nan()) {
        return Ok(LookupValueV1::Missing);
    }
    Ok(LookupValueV1::Present(cell_value(value.value()).map_err(
        |error| ConfigValidateErrorV1::Workbook(format!("{key}: {error}")),
    )?))
}

fn lookup_source_cell<'a>(
    rows: &'a [Vec<sipi_com::RawCellV1>],
    key: &str,
) -> Result<Option<&'a sipi_com::RawCellV1>, ConfigValidateErrorV1> {
    let folded = key.to_ascii_lowercase();
    let mut found = None;
    for (row_index, row) in rows.iter().enumerate() {
        for (column_index, cell) in row.iter().enumerate() {
            if let CellValueV1::String(value) = cell.value()
                && value.to_ascii_lowercase() == folded
            {
                if found.is_some() {
                    return Err(ConfigValidateErrorV1::Workbook(format!(
                        "duplicate configuration parameter: {key}"
                    )));
                }
                found = Some((row_index, column_index));
            }
        }
    }
    let Some((row_index, column_index)) = found else {
        return Ok(None);
    };
    rows[row_index]
        .get(column_index + 1)
        .map(Some)
        .ok_or_else(|| ConfigValidateErrorV1::Workbook(format!("{key}: right-hand value")))
}

fn cell_value(value: &CellValueV1) -> Result<ResolvedDefaultV1, ConfigValidateErrorV1> {
    let resolved = match value {
        CellValueV1::None => ResolvedDefaultV1::Empty,
        CellValueV1::Integer(value) => {
            const MAX_EXACT_F64_INTEGER: i64 = 1_i64 << 53;
            if !(-MAX_EXACT_F64_INTEGER..=MAX_EXACT_F64_INTEGER).contains(value) {
                return Err(ConfigValidateErrorV1::Workbook(
                    "configuration integer is not exactly representable as f64".to_owned(),
                ));
            }
            ResolvedDefaultV1::Scalar(*value as f64)
        }
        CellValueV1::Number(value) => {
            if !value.is_finite() {
                return Err(ConfigValidateErrorV1::Workbook(
                    "configuration numeric input must be finite".to_owned(),
                ));
            }
            ResolvedDefaultV1::Scalar(*value)
        }
        CellValueV1::Bool(value) => ResolvedDefaultV1::Boolean(*value),
        CellValueV1::String(value) => ResolvedDefaultV1::String(value.clone()),
        CellValueV1::Array { dims, data } => {
            if dims.is_empty() || dims.len() > 2 {
                return Err(ConfigValidateErrorV1::Workbook(
                    "configuration array must have one or two dimensions".to_owned(),
                ));
            }
            let expected = dims.iter().try_fold(1_usize, |product, dimension| {
                product.checked_mul(*dimension as usize)
            });
            if expected != Some(data.len()) || data.len() > MAX_NUMERIC_ELEMENTS {
                return Err(ConfigValidateErrorV1::Workbook(
                    "configuration array dimensions or element budget are invalid".to_owned(),
                ));
            }
            if data.iter().any(|value| !value.is_finite()) {
                return Err(ConfigValidateErrorV1::Workbook(
                    "configuration array input must be finite".to_owned(),
                ));
            }
            if dims.len() == 2 && dims[0] > 0 && dims[1] > 0 {
                let columns = dims[1] as usize;
                ResolvedDefaultV1::Matrix(data.chunks(columns).map(|row| row.to_vec()).collect())
            } else {
                ResolvedDefaultV1::Vector(data.clone())
            }
        }
    };
    validate_resolved_value(&resolved, "configuration cell")?;
    Ok(resolved)
}

#[allow(clippy::type_complexity)]
fn split_packages(
    settings: &ComSettingsV1,
    profile: &ValidatedProfileV1,
) -> Result<
    (
        Vec<Vec<sipi_com::RawCellV1>>,
        Vec<PackageBlockV1>,
        PackageInventoryV1,
    ),
    ConfigValidateErrorV1,
> {
    let rows = settings.rows();
    let starts: Vec<usize> = rows
        .iter()
        .enumerate()
        .filter_map(|(index, row)| {
            row.first().and_then(|cell| match cell.value() {
                CellValueV1::String(value) if value == ".START" => Some(index),
                _ => None,
            })
        })
        .collect();
    let ends: Vec<usize> = rows
        .iter()
        .enumerate()
        .filter_map(|(index, row)| {
            row.first().and_then(|cell| match cell.value() {
                CellValueV1::String(value) if value == ".END" => Some(index),
                _ => None,
            })
        })
        .collect();
    if starts.is_empty() && ends.is_empty() {
        return Ok((
            rows.to_vec(),
            Vec::new(),
            PackageInventoryV1 {
                count: 0,
                warnings: Vec::new(),
            },
        ));
    }
    if starts.len() != ends.len()
        || starts
            .iter()
            .zip(ends.iter())
            .any(|(start, end)| start >= end)
        || ends
            .iter()
            .zip(starts.iter().skip(1))
            .any(|(end, next_start)| end >= next_start)
    {
        return Err(ConfigValidateErrorV1::Workbook(
            "package .START/.END markers are unbalanced".to_owned(),
        ));
    }
    let mut blocks = Vec::new();
    let mut names = Vec::new();
    for (&start, &end) in starts.iter().zip(ends.iter()) {
        let name = rows[start]
            .get(1)
            .and_then(|cell| match cell.value() {
                CellValueV1::String(value) if !value.is_empty() => Some(value.clone()),
                _ => None,
            })
            .ok_or_else(|| {
                ConfigValidateErrorV1::Workbook(
                    "package .START requires a package name in column B".to_owned(),
                )
            })?;
        names.push(name.clone());
        blocks.push(PackageBlockV1 {
            name,
            rows: rows[start + 1..end].to_vec(),
        });
    }
    let mut seen = BTreeSet::new();
    let mut warnings = Vec::new();
    for name in names {
        if !seen.insert(name) {
            warnings.push("R480-PKG-DUP-NAME".to_owned());
        }
    }
    if warnings.iter().any(|code| code == "R480-PKG-DUP-NAME")
        && profile
            .fix_ids
            .iter()
            .any(|fix| fix == "fix.reject_duplicate_package_name")
    {
        return Err(ConfigValidateErrorV1::Workbook(
            "fix.reject_duplicate_package_name: duplicate package block name".to_owned(),
        ));
    }
    let main = rows[..starts[0]].to_vec();
    Ok((
        main,
        blocks,
        PackageInventoryV1 {
            count: starts.len(),
            warnings,
        },
    ))
}

fn validate_package_references(
    rows: &[Vec<sipi_com::RawCellV1>],
    packages: &[PackageBlockV1],
) -> Result<(), ConfigValidateErrorV1> {
    let LookupValueV1::Present(ResolvedDefaultV1::String(names)) = lookup_value(rows, "PKG_NAME")?
    else {
        return Ok(());
    };
    if names.trim().is_empty() {
        return Ok(());
    }
    let available: BTreeSet<&str> = packages
        .iter()
        .map(|package| package.name.as_str())
        .collect();
    for name in names.split_whitespace() {
        if !available.contains(name) {
            return Err(ConfigValidateErrorV1::Workbook(format!(
                "PKG_NAME references undefined package blocks: {name}"
            )));
        }
    }
    Ok(())
}

fn canonicalize_override_keys(
    schema: &SchemaDocument,
    overrides: BTreeMap<String, String>,
) -> Result<BTreeMap<String, String>, ConfigValidateErrorV1> {
    let mut canonical = BTreeMap::new();
    for (key, value) in overrides {
        let Some(entry) = schema
            .parameters
            .iter()
            .find(|entry| entry.key.eq_ignore_ascii_case(&key))
        else {
            return Err(ConfigValidateErrorV1::Workbook(format!(
                "override has no r4.80 source-schema evidence: {key}"
            )));
        };
        if canonical.insert(entry.key.clone(), value).is_some() {
            return Err(ConfigValidateErrorV1::Override(format!(
                "duplicate override after canonicalization: {}",
                entry.key
            )));
        }
    }
    Ok(canonical)
}

fn json_map(values: &BTreeMap<String, ResolvedDefaultV1>) -> Value {
    let object = values
        .iter()
        .map(|(key, value)| (key.clone(), json_value_for_key(key, value)))
        .collect::<serde_json::Map<_, _>>();
    Value::Object(object)
}

fn json_value_for_key(key: &str, value: &ResolvedDefaultV1) -> Value {
    if key == "PKG_NAME"
        && let ResolvedDefaultV1::String(names) = value
    {
        return Value::Array(
            names
                .split_whitespace()
                .map(|name| Value::String(name.to_owned()))
                .collect(),
        );
    }
    json_value(value)
}

fn json_value(value: &ResolvedDefaultV1) -> Value {
    match value {
        ResolvedDefaultV1::Scalar(value) => {
            if value.is_nan() {
                json!({"$special_float": "NaN"})
            } else if value.is_infinite() {
                json!({"$special_float": if *value > 0.0 { "Infinity" } else { "-Infinity" }})
            } else {
                json!(value)
            }
        }
        ResolvedDefaultV1::Vector(values) => Value::Array(
            values
                .iter()
                .map(|value| json_value(&ResolvedDefaultV1::Scalar(*value)))
                .collect(),
        ),
        ResolvedDefaultV1::Matrix(rows) => Value::Array(
            rows.iter()
                .map(|row| {
                    Value::Array(
                        row.iter()
                            .map(|value| json_value(&ResolvedDefaultV1::Scalar(*value)))
                            .collect(),
                    )
                })
                .collect(),
        ),
        ResolvedDefaultV1::Boolean(value) => json!(value),
        ResolvedDefaultV1::String(value) => json!(value),
        ResolvedDefaultV1::Empty => Value::Array(Vec::new()),
    }
}

fn materialized_fingerprint(
    parameters: &Value,
    options: &Value,
    integer_parameters: &BTreeSet<String>,
    integer_options: &BTreeSet<String>,
) -> Result<String, ConfigValidateErrorV1> {
    let bytes =
        canonical_materialized_bytes(parameters, options, integer_parameters, integer_options)?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}

fn canonical_materialized_bytes(
    parameters: &Value,
    options: &Value,
    integer_parameters: &BTreeSet<String>,
    integer_options: &BTreeSet<String>,
) -> Result<Vec<u8>, ConfigValidateErrorV1> {
    canonical_materialized_bytes_with_limit(
        parameters,
        options,
        integer_parameters,
        integer_options,
        MAX_MATERIALIZED_FINGERPRINT_BYTES,
    )
}

fn canonical_materialized_bytes_with_limit(
    parameters: &Value,
    options: &Value,
    integer_parameters: &BTreeSet<String>,
    integer_options: &BTreeSet<String>,
    limit: usize,
) -> Result<Vec<u8>, ConfigValidateErrorV1> {
    // The pinned implementation hashes Python's compact json.dumps payload.
    // serde_json deliberately uses a different float spelling, so this is a
    // small writer rather than a generic serde serialization.
    let mut writer = BoundedFingerprintWriter::new(limit);
    writer.push(b'{')?;
    write_python_json_string("options", &mut writer)?;
    writer.push(b':')?;
    write_python_canonical_value(options, &mut writer, Some(integer_options), false)?;
    writer.push(b',')?;
    write_python_json_string("parameters", &mut writer)?;
    writer.push(b':')?;
    write_python_canonical_value(parameters, &mut writer, Some(integer_parameters), false)?;
    writer.push(b'}')?;
    Ok(writer.into_bytes())
}

struct BoundedFingerprintWriter {
    bytes: Vec<u8>,
    limit: usize,
}

impl BoundedFingerprintWriter {
    fn new(limit: usize) -> Self {
        Self {
            bytes: Vec::with_capacity(limit.min(4096)),
            limit,
        }
    }

    fn push(&mut self, byte: u8) -> Result<(), ConfigValidateErrorV1> {
        self.ensure(1)?;
        self.bytes.push(byte);
        Ok(())
    }

    fn extend(&mut self, bytes: &[u8]) -> Result<(), ConfigValidateErrorV1> {
        self.ensure(bytes.len())?;
        self.bytes.extend_from_slice(bytes);
        Ok(())
    }

    fn ensure(&self, additional: usize) -> Result<(), ConfigValidateErrorV1> {
        let next = self.bytes.len().checked_add(additional).ok_or_else(|| {
            ConfigValidateErrorV1::Workbook(
                "materialized fingerprint byte-count overflow".to_owned(),
            )
        })?;
        if next > self.limit {
            return Err(ConfigValidateErrorV1::Workbook(format!(
                "materialized fingerprint exceeds {}-byte budget",
                self.limit
            )));
        }
        Ok(())
    }

    fn into_bytes(self) -> Vec<u8> {
        self.bytes
    }
}

fn write_python_canonical_value(
    value: &Value,
    output: &mut BoundedFingerprintWriter,
    integer_keys: Option<&BTreeSet<String>>,
    integer_scalar: bool,
) -> Result<(), ConfigValidateErrorV1> {
    match value {
        Value::Null => output.extend(b"null")?,
        Value::Bool(value) => output.extend(if *value { b"true" } else { b"false" })?,
        Value::Number(number) => {
            if integer_scalar {
                let value = number.as_f64().ok_or_else(|| {
                    ConfigValidateErrorV1::Workbook(
                        "cannot encode non-f64 integer fingerprint scalar".to_owned(),
                    )
                })?;
                if !value.is_finite() || value.fract() != 0.0 {
                    return Err(ConfigValidateErrorV1::Workbook(
                        "integer fingerprint scalar is not an exact finite integer".to_owned(),
                    ));
                }
                let integer = value as i64;
                if integer as f64 != value {
                    return Err(ConfigValidateErrorV1::Workbook(
                        "integer fingerprint scalar is outside exact i64 range".to_owned(),
                    ));
                }
                output.extend(integer.to_string().as_bytes())?;
            } else if let Some(value) = number.as_i64() {
                output.extend(value.to_string().as_bytes())?;
            } else if let Some(value) = number.as_u64() {
                output.extend(value.to_string().as_bytes())?;
            } else {
                let value = number.as_f64().ok_or_else(|| {
                    ConfigValidateErrorV1::Workbook("cannot decode fingerprint number".to_owned())
                })?;
                output.extend(python_float_repr(value)?.as_bytes())?;
            }
        }
        Value::String(value) => write_python_json_string(value, output)?,
        Value::Array(values) => {
            output.push(b'[')?;
            for (index, value) in values.iter().enumerate() {
                if index != 0 {
                    output.push(b',')?;
                }
                write_python_canonical_value(value, output, None, false)?;
            }
            output.push(b']')?;
        }
        Value::Object(values) => {
            if let Some(special) = special_float_name(values) {
                output.extend(b"{\"__float__\":")?;
                write_python_json_string(special, output)?;
                output.push(b'}')?;
                return Ok(());
            }
            let mut keys = values.keys().collect::<Vec<_>>();
            keys.sort();
            output.push(b'{')?;
            for (index, key) in keys.iter().enumerate() {
                if index != 0 {
                    output.push(b',')?;
                }
                write_python_json_string(key, output)?;
                output.push(b':')?;
                let child_is_integer = integer_keys.is_some_and(|keys| keys.contains(*key));
                write_python_canonical_value(&values[*key], output, None, child_is_integer)?;
            }
            output.push(b'}')?;
        }
    }
    Ok(())
}

fn special_float_name(values: &serde_json::Map<String, Value>) -> Option<&'static str> {
    if values.len() != 1 {
        return None;
    }
    let Value::String(value) = values.get("$special_float")? else {
        return None;
    };
    match value.as_str() {
        "NaN" => Some("nan"),
        "Infinity" => Some("inf"),
        "-Infinity" => Some("-inf"),
        _ => None,
    }
}

fn write_python_json_string(
    value: &str,
    output: &mut BoundedFingerprintWriter,
) -> Result<(), ConfigValidateErrorV1> {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    output.push(b'"')?;
    for character in value.chars() {
        match character {
            '"' => output.extend(b"\\\"")?,
            '\\' => output.extend(b"\\\\")?,
            '\u{08}' => output.extend(b"\\b")?,
            '\u{0c}' => output.extend(b"\\f")?,
            '\n' => output.extend(b"\\n")?,
            '\r' => output.extend(b"\\r")?,
            '\t' => output.extend(b"\\t")?,
            character if character.is_ascii_control() => {
                let value = character as u32;
                output.extend(b"\\u00")?;
                output.push(HEX[(value >> 4) as usize])?;
                output.push(HEX[(value & 0x0f) as usize])?;
            }
            character if character.is_ascii() => output.push(character as u8)?,
            character => {
                let value = character as u32;
                if value <= 0xffff {
                    output.extend(b"\\u")?;
                    output.push(HEX[((value >> 12) & 0x0f) as usize])?;
                    output.push(HEX[((value >> 8) & 0x0f) as usize])?;
                    output.push(HEX[((value >> 4) & 0x0f) as usize])?;
                    output.push(HEX[(value & 0x0f) as usize])?;
                } else {
                    let value = value - 0x1_0000;
                    let high = 0xd800 + (value >> 10);
                    let low = 0xdc00 + (value & 0x3ff);
                    for value in [high, low] {
                        output.extend(b"\\u")?;
                        output.push(HEX[((value >> 12) & 0x0f) as usize])?;
                        output.push(HEX[((value >> 8) & 0x0f) as usize])?;
                        output.push(HEX[((value >> 4) & 0x0f) as usize])?;
                        output.push(HEX[(value & 0x0f) as usize])?;
                    }
                }
            }
        }
    }
    output.push(b'"')?;
    Ok(())
}

fn python_float_repr(value: f64) -> Result<String, ConfigValidateErrorV1> {
    if !value.is_finite() {
        return Err(ConfigValidateErrorV1::Workbook(
            "non-finite number missing special-float envelope".to_owned(),
        ));
    }
    let raw = value.to_string();
    if value == 0.0 {
        return Ok(if value.is_sign_negative() {
            "-0.0".to_owned()
        } else {
            "0.0".to_owned()
        });
    }
    let scientific = value.abs() < 1e-4 || value.abs() >= 1e16;
    let (negative, mantissa, exponent) = split_decimal_repr(&raw)?;
    let mut result = if scientific {
        let digits = mantissa.trim_end_matches('0');
        let mut chars = digits.chars();
        let first = chars.next().ok_or_else(|| {
            ConfigValidateErrorV1::Workbook("empty floating-point mantissa".to_owned())
        })?;
        let rest = chars.collect::<String>();
        let mut result = String::new();
        if negative {
            result.push('-');
        }
        result.push(first);
        if !rest.is_empty() {
            result.push('.');
            result.push_str(&rest);
        }
        result.push('e');
        if exponent >= 0 {
            result.push('+');
        } else {
            result.push('-');
        }
        result.push_str(&format!("{:02}", exponent.unsigned_abs()));
        result
    } else {
        let mut result = decimal_from_digits(&mantissa, exponent);
        if negative {
            result.insert(0, '-');
        }
        result
    };
    if !result.contains('.') && !result.contains('e') {
        result.push_str(".0");
    }
    Ok(result)
}

fn split_decimal_repr(raw: &str) -> Result<(bool, String, i32), ConfigValidateErrorV1> {
    let (negative, unsigned) = match raw.strip_prefix('-') {
        Some(value) => (true, value),
        None => (false, raw),
    };
    let (mantissa, exponent) = match unsigned.split_once(['e', 'E']) {
        Some((mantissa, exponent)) => (
            mantissa,
            exponent.parse::<i32>().map_err(|_| {
                ConfigValidateErrorV1::Workbook("invalid floating-point exponent".to_owned())
            })?,
        ),
        None => (unsigned, 0),
    };
    let (whole, fraction) = mantissa.split_once('.').unwrap_or((mantissa, ""));
    let digits = format!("{whole}{fraction}");
    let first = digits
        .find(|character: char| character != '0')
        .ok_or_else(|| {
            ConfigValidateErrorV1::Workbook("zero floating-point mantissa".to_owned())
        })?;
    let digits = digits[first..].to_owned();
    let decimal_position = whole.len() as i32 - first as i32;
    Ok((negative, digits, exponent + decimal_position - 1))
}

fn decimal_from_digits(digits: &str, exponent: i32) -> String {
    let decimal_position = exponent + 1;
    if decimal_position <= 0 {
        return format!("0.{}{}", "0".repeat((-decimal_position) as usize), digits);
    }
    if decimal_position as usize >= digits.len() {
        return format!(
            "{}{}",
            digits,
            "0".repeat(decimal_position as usize - digits.len())
        );
    }
    let position = decimal_position as usize;
    format!("{}.{}", &digits[..position], &digits[position..])
}

fn consumption_report(
    parameters: &BTreeMap<String, ResolvedDefaultV1>,
    options: &BTreeMap<String, ResolvedDefaultV1>,
    registry: &ConsumptionRegistry,
) -> Value {
    let buckets = [
        (
            "implemented",
            &registry.implemented_parameters,
            &registry.implemented_options,
        ),
        (
            "report_only",
            &registry.report_only_parameters,
            &registry.report_only_options,
        ),
        (
            "unimplemented",
            &registry.unimplemented_parameters,
            &registry.unimplemented_options,
        ),
        (
            "obsolete",
            &registry.obsolete_parameters,
            &registry.obsolete_options,
        ),
    ];
    let mut result = serde_json::Map::new();
    for (status, parameter_names, option_names) in buckets {
        result.insert(
            status.to_owned(),
            json!({
                "parameters": select_values(parameters, parameter_names),
                "options": select_values(options, option_names),
            }),
        );
    }
    let classified_parameters: BTreeSet<&str> = buckets
        .iter()
        .flat_map(|(_, names, _)| names.iter().map(String::as_str))
        .collect();
    let classified_options: BTreeSet<&str> = buckets
        .iter()
        .flat_map(|(_, _, names)| names.iter().map(String::as_str))
        .collect();
    result.insert(
        "unverified".to_owned(),
        json!({
            "parameters": select_unverified(parameters, &classified_parameters),
            "options": select_unverified(options, &classified_options),
        }),
    );
    let mut status_counts = serde_json::Map::new();
    for status in [
        "implemented",
        "report_only",
        "unimplemented",
        "obsolete",
        "unverified",
    ] {
        let entry = result
            .get(status)
            .and_then(Value::as_object)
            .expect("bucket");
        let p = entry
            .get("parameters")
            .and_then(Value::as_object)
            .map_or(0, |m| m.len());
        let o = entry
            .get("options")
            .and_then(Value::as_object)
            .map_or(0, |m| m.len());
        status_counts.insert(
            status.to_owned(),
            json!({
                "parameters": p,
                "options": o,
                "total": p + o,
            }),
        );
    }
    result.insert(
        "summary".to_owned(),
        json!({
            "total": parameters.len() + options.len(),
            "status_counts": status_counts,
        }),
    );
    Value::Object(result)
}

fn select_values(values: &BTreeMap<String, ResolvedDefaultV1>, names: &[String]) -> Value {
    let name_set: BTreeSet<&str> = names.iter().map(String::as_str).collect();
    Value::Object(
        values
            .iter()
            .filter(|(key, _)| name_set.contains(key.as_str()))
            .map(|(key, value)| (key.clone(), json_value_for_key(key, value)))
            .collect(),
    )
}

fn select_unverified(
    values: &BTreeMap<String, ResolvedDefaultV1>,
    classified: &BTreeSet<&str>,
) -> Value {
    Value::Object(
        values
            .iter()
            .filter(|(key, _)| !classified.contains(key.as_str()))
            .map(|(key, value)| (key.clone(), json_value_for_key(key, value)))
            .collect(),
    )
}

fn load_settings(path: &Path) -> Result<ComSettingsV1, ConfigValidateErrorV1> {
    let bytes = fs::metadata(path)
        .map_err(|error| {
            if error.kind() == std::io::ErrorKind::NotFound {
                ConfigValidateErrorV1::Workbook("configuration file not found".to_owned())
            } else {
                ConfigValidateErrorV1::Workbook(error.to_string())
            }
        })?
        .len();
    if bytes > MAX_CONFIG_FILE_BYTES {
        return Err(ConfigValidateErrorV1::Workbook(format!(
            "configuration input exceeds {MAX_CONFIG_FILE_BYTES}-byte budget"
        )));
    }
    let extension = path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase();
    preflight_config_source_v1(path, &extension)?;
    let settings = match extension.as_str() {
        "xlsx" => read_com_settings_xlsx_v1(path).map_err(workbook_error),
        "csv" => read_com_settings_csv_v1(path).map_err(workbook_error),
        "mat" => read_com_settings_mat_v1(path).map_err(workbook_error),
        _ => Err(ConfigValidateErrorV1::Workbook(
            "configuration loader supports only .xlsx, .csv, or .mat".to_owned(),
        )),
    }?;
    validate_settings_budget(&settings)?;
    Ok(settings)
}

fn validate_settings_budget(settings: &ComSettingsV1) -> Result<(), ConfigValidateErrorV1> {
    let mut cells = 0_usize;
    let mut numeric_elements = 0_usize;
    for row in settings.rows() {
        cells = cells.checked_add(row.len()).ok_or_else(|| {
            ConfigValidateErrorV1::Workbook("configuration cell count overflow".to_owned())
        })?;
        if cells > MAX_CONFIG_CELLS {
            return Err(ConfigValidateErrorV1::Workbook(format!(
                "configuration input exceeds {MAX_CONFIG_CELLS}-cell budget"
            )));
        }
        for cell in row {
            let count = match cell.value() {
                CellValueV1::Integer(_) | CellValueV1::Number(_) => 1,
                CellValueV1::Array { dims, data } => {
                    if dims.is_empty() || dims.len() > 2 {
                        return Err(ConfigValidateErrorV1::Workbook(
                            "configuration array must have one or two dimensions".to_owned(),
                        ));
                    }
                    let expected = dims.iter().try_fold(1_usize, |product, dimension| {
                        product.checked_mul(*dimension as usize)
                    });
                    if expected != Some(data.len()) {
                        return Err(ConfigValidateErrorV1::Workbook(
                            "configuration array dimensions are invalid".to_owned(),
                        ));
                    }
                    data.len()
                }
                CellValueV1::None | CellValueV1::Bool(_) | CellValueV1::String(_) => 0,
            };
            numeric_elements = numeric_elements.checked_add(count).ok_or_else(|| {
                ConfigValidateErrorV1::Workbook(
                    "configuration numeric-element count overflow".to_owned(),
                )
            })?;
            if numeric_elements > MAX_NUMERIC_ELEMENTS {
                return Err(ConfigValidateErrorV1::Workbook(format!(
                    "configuration input exceeds {MAX_NUMERIC_ELEMENTS}-numeric-element budget"
                )));
            }
        }
    }
    Ok(())
}

fn workbook_error(error: WorkbookErrorV1) -> ConfigValidateErrorV1 {
    ConfigValidateErrorV1::Workbook(format!("{error:?}"))
}

fn sha256_file(path: &Path) -> Result<String, ConfigValidateErrorV1> {
    let bytes = fs::read(path).map_err(|error| ConfigValidateErrorV1::Io(error.to_string()))?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}

fn canonical_or_absolute(path: &Path) -> String {
    let value = fs::canonicalize(path)
        .unwrap_or_else(|_| path.to_path_buf())
        .to_string_lossy()
        .into_owned();
    value.strip_prefix(r"\\?\").unwrap_or(&value).to_owned()
}

fn parse_overrides(
    specifications: &[String],
) -> Result<BTreeMap<String, String>, ConfigValidateErrorV1> {
    let mut result = BTreeMap::new();
    for specification in specifications {
        let Some((key, value)) = specification.split_once('=') else {
            return Err(ConfigValidateErrorV1::Override(format!(
                "{specification:?}; expected KEY=VALUE"
            )));
        };
        if key.is_empty() || value.is_empty() {
            return Err(ConfigValidateErrorV1::Override(format!(
                "{specification:?}; expected non-empty KEY and VALUE"
            )));
        }
        if result
            .keys()
            .any(|known: &String| known.eq_ignore_ascii_case(key))
        {
            return Err(ConfigValidateErrorV1::Override(format!(
                "duplicate override: {key}"
            )));
        }
        result.insert(key.to_owned(), value.to_owned());
    }
    Ok(result)
}

fn validate_profile(
    profile: &str,
    reader: Option<&str>,
    fix_ids: &[String],
) -> Result<ValidatedProfileV1, ConfigValidateErrorV1> {
    let (name, reader_semantics, profile_fix_ids) = if reader.is_some() || !fix_ids.is_empty() {
        if profile != "custom" {
            return Err(ConfigValidateErrorV1::Profile(
                "--reader and --fix-id require --profile custom".to_owned(),
            ));
        }
        (
            "custom".to_owned(),
            reader.unwrap_or("r480").to_owned(),
            fix_ids.to_vec(),
        )
    } else if profile == "custom" {
        return Err(ConfigValidateErrorV1::Profile(
            "--profile custom requires --reader or --fix-id".to_owned(),
        ));
    } else if profile == "r480" {
        ("r480".to_owned(), "r480".to_owned(), Vec::new())
    } else if profile == "experimental_corrected" {
        (
            profile.to_owned(),
            "r480".to_owned(),
            vec![
                "fix.erl_best_phase".to_owned(),
                "fix.reject_duplicate_package_name".to_owned(),
            ],
        )
    } else {
        return Err(ConfigValidateErrorV1::Profile(format!(
            "profile is disabled or unknown: {profile}"
        )));
    };
    if !matches!(reader_semantics.as_str(), "r480" | "standard") {
        return Err(ConfigValidateErrorV1::Profile(
            "reader semantics must be r480 or standard".to_owned(),
        ));
    }
    for fix_id in &profile_fix_ids {
        if !KNOWN_FIX_IDS.contains(&fix_id.as_str()) {
            return Err(ConfigValidateErrorV1::Profile(format!(
                "unknown behavior-profile fix id: {fix_id}"
            )));
        }
    }
    Ok(ValidatedProfileV1 {
        name,
        reader_semantics,
        fix_ids: profile_fix_ids,
    })
}

fn as_scalar(value: &ResolvedDefaultV1) -> Option<f64> {
    match value {
        ResolvedDefaultV1::Scalar(value) => Some(*value),
        ResolvedDefaultV1::Boolean(value) => Some(if *value { 1.0 } else { 0.0 }),
        _ => None,
    }
}

fn bounded_count(
    value: Option<&ResolvedDefaultV1>,
    name: &str,
    minimum: usize,
) -> Result<usize, ConfigValidateErrorV1> {
    let scalar = value.and_then(as_scalar).ok_or_else(|| {
        ConfigValidateErrorV1::Workbook(format!("{name} must be a scalar integer"))
    })?;
    bounded_integer(scalar, name, minimum)
}

fn bounded_integer(value: f64, name: &str, minimum: usize) -> Result<usize, ConfigValidateErrorV1> {
    if !value.is_finite()
        || value.fract() != 0.0
        || value < minimum as f64
        || value > MAX_COUNT_VALUE as f64
    {
        return Err(ConfigValidateErrorV1::Workbook(format!(
            "{name} must be a finite integer in {minimum}..={MAX_COUNT_VALUE}"
        )));
    }
    Ok(value as usize)
}

fn numeric_element_count(value: &ResolvedDefaultV1) -> Result<usize, ConfigValidateErrorV1> {
    match value {
        ResolvedDefaultV1::Scalar(value) => {
            if value.is_nan() || *value == f64::NEG_INFINITY {
                return Err(ConfigValidateErrorV1::Workbook(
                    "configuration contains a non-finite numeric value".to_owned(),
                ));
            }
            Ok(1)
        }
        ResolvedDefaultV1::Vector(values) => {
            if values
                .iter()
                .any(|value| value.is_nan() || *value == f64::NEG_INFINITY)
            {
                return Err(ConfigValidateErrorV1::Workbook(
                    "configuration contains a non-finite numeric value".to_owned(),
                ));
            }
            Ok(values.len())
        }
        ResolvedDefaultV1::Matrix(rows) => {
            let width = rows.first().map_or(0, Vec::len);
            if rows.iter().any(|row| row.len() != width) {
                return Err(ConfigValidateErrorV1::Workbook(
                    "configuration contains a non-rectangular matrix".to_owned(),
                ));
            }
            let count = rows.len().checked_mul(width).ok_or_else(|| {
                ConfigValidateErrorV1::Workbook(
                    "configuration matrix dimensions overflow".to_owned(),
                )
            })?;
            if rows
                .iter()
                .flatten()
                .any(|value| value.is_nan() || *value == f64::NEG_INFINITY)
            {
                return Err(ConfigValidateErrorV1::Workbook(
                    "configuration contains a non-finite numeric value".to_owned(),
                ));
            }
            Ok(count)
        }
        ResolvedDefaultV1::Boolean(_) | ResolvedDefaultV1::String(_) | ResolvedDefaultV1::Empty => {
            Ok(0)
        }
    }
}

fn validate_resolved_value(
    value: &ResolvedDefaultV1,
    label: &str,
) -> Result<(), ConfigValidateErrorV1> {
    let count = numeric_element_count(value)?;
    if count > MAX_NUMERIC_ELEMENTS {
        return Err(ConfigValidateErrorV1::Workbook(format!(
            "{label} exceeds {MAX_NUMERIC_ELEMENTS}-numeric-element budget"
        )));
    }
    Ok(())
}

fn validate_output_budget(
    parameters: &BTreeMap<String, ResolvedDefaultV1>,
    options: &BTreeMap<String, ResolvedDefaultV1>,
) -> Result<(), ConfigValidateErrorV1> {
    let total = parameters
        .values()
        .chain(options.values())
        .try_fold(0_usize, |total, value| {
            let count = numeric_element_count(value)?;
            total.checked_add(count).ok_or_else(|| {
                ConfigValidateErrorV1::Workbook(
                    "materialized numeric-element count overflow".to_owned(),
                )
            })
        })?;
    if total > MAX_NUMERIC_ELEMENTS {
        return Err(ConfigValidateErrorV1::Workbook(format!(
            "materialized output exceeds {MAX_NUMERIC_ELEMENTS}-numeric-element budget"
        )));
    }
    validate_materialized_storage_budget(parameters, options)
}

fn validate_materialized_storage_budget(
    parameters: &BTreeMap<String, ResolvedDefaultV1>,
    options: &BTreeMap<String, ResolvedDefaultV1>,
) -> Result<(), ConfigValidateErrorV1> {
    validate_materialized_storage_budget_with_limit(
        parameters,
        options,
        MAX_MATERIALIZED_FINGERPRINT_BYTES,
    )
}

fn validate_materialized_storage_budget_with_limit(
    parameters: &BTreeMap<String, ResolvedDefaultV1>,
    options: &BTreeMap<String, ResolvedDefaultV1>,
    limit: usize,
) -> Result<(), ConfigValidateErrorV1> {
    let total =
        parameters
            .iter()
            .chain(options.iter())
            .try_fold(0_usize, |total, (key, value)| {
                let total = total.checked_add(key.len()).ok_or_else(|| {
                    ConfigValidateErrorV1::Workbook(
                        "materialized key/default-copy byte count overflow".to_owned(),
                    )
                })?;
                let bytes = resolved_value_owned_bytes(value)?;
                total.checked_add(bytes).ok_or_else(|| {
                    ConfigValidateErrorV1::Workbook(
                        "materialized value/default-copy byte count overflow".to_owned(),
                    )
                })
            })?;
    if total > limit {
        return Err(ConfigValidateErrorV1::Workbook(format!(
            "materialized values/default copies exceed {}-byte budget",
            limit
        )));
    }
    Ok(())
}

fn resolved_value_owned_bytes(value: &ResolvedDefaultV1) -> Result<usize, ConfigValidateErrorV1> {
    match value {
        ResolvedDefaultV1::Scalar(_) | ResolvedDefaultV1::Boolean(_) => Ok(8),
        ResolvedDefaultV1::String(value) => Ok(value.len()),
        ResolvedDefaultV1::Empty => Ok(0),
        ResolvedDefaultV1::Vector(values) => values.len().checked_mul(8).ok_or_else(|| {
            ConfigValidateErrorV1::Workbook(
                "materialized vector/default-copy byte count overflow".to_owned(),
            )
        }),
        ResolvedDefaultV1::Matrix(rows) => rows.iter().try_fold(0_usize, |total, row| {
            let bytes = row.len().checked_mul(8).ok_or_else(|| {
                ConfigValidateErrorV1::Workbook(
                    "materialized matrix/default-copy byte count overflow".to_owned(),
                )
            })?;
            total.checked_add(bytes).ok_or_else(|| {
                ConfigValidateErrorV1::Workbook(
                    "materialized matrix/default-copy byte count overflow".to_owned(),
                )
            })
        }),
    }
}

fn as_vector(value: Option<&ResolvedDefaultV1>) -> Option<Vec<f64>> {
    match value {
        Some(ResolvedDefaultV1::Vector(values)) => Some(values.clone()),
        Some(ResolvedDefaultV1::Scalar(value)) => Some(vec![*value]),
        Some(ResolvedDefaultV1::Matrix(rows)) if rows.len() == 1 => Some(rows[0].clone()),
        _ => None,
    }
}

fn as_matrix(value: Option<&ResolvedDefaultV1>) -> Option<Vec<Vec<f64>>> {
    match value {
        Some(ResolvedDefaultV1::Matrix(rows)) => Some(rows.clone()),
        _ => None,
    }
}

fn truthy(value: Option<&ResolvedDefaultV1>) -> bool {
    match value {
        Some(ResolvedDefaultV1::Boolean(value)) => *value,
        Some(ResolvedDefaultV1::Scalar(value)) => *value != 0.0,
        Some(ResolvedDefaultV1::String(value)) => !value.is_empty(),
        Some(ResolvedDefaultV1::Vector(value)) => !value.is_empty(),
        Some(ResolvedDefaultV1::Matrix(value)) => !value.is_empty(),
        _ => false,
    }
}

fn is_nonempty(value: Option<&ResolvedDefaultV1>) -> bool {
    match value {
        Some(ResolvedDefaultV1::Empty) | None => false,
        Some(ResolvedDefaultV1::Vector(values)) => !values.is_empty(),
        Some(ResolvedDefaultV1::Matrix(rows)) => !rows.is_empty(),
        _ => true,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use std::time::{SystemTime, UNIX_EPOCH};
    use zip::ZipWriter;
    use zip::write::SimpleFileOptions;

    fn csv_file(contents: &str) -> PathBuf {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock")
            .as_nanos();
        let path = std::env::temp_dir().join(format!("sipi-com-01-{nonce}.csv"));
        fs::write(&path, contents).expect("write fixture");
        path
    }

    fn xlsx_file(rows: &[(&str, &str)]) -> PathBuf {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock")
            .as_nanos();
        let path = std::env::temp_dir().join(format!("sipi-com-01-{nonce}.xlsx"));
        let file = fs::File::create(&path).expect("xlsx fixture");
        let mut archive = ZipWriter::new(file);
        let options = SimpleFileOptions::default();
        let mut sheet = String::from("<worksheet><sheetData>");
        for (index, (key, value)) in rows.iter().enumerate() {
            let row = index + 1;
            sheet.push_str(&format!("<row r=\"{row}\">"));
            sheet.push_str(&format!(
                "<c r=\"A{row}\" t=\"inlineStr\"><is><t>{key}</t></is></c>"
            ));
            if value.parse::<f64>().is_ok() {
                sheet.push_str(&format!("<c r=\"B{row}\"><v>{value}</v></c>"));
            } else {
                sheet.push_str(&format!(
                    "<c r=\"B{row}\" t=\"inlineStr\"><is><t>{value}</t></is></c>"
                ));
            }
            sheet.push_str("</row>");
        }
        sheet.push_str("</sheetData></worksheet>");
        for (name, contents) in [
            (
                "xl/workbook.xml",
                "<workbook xmlns:r=\"r\"><sheets><sheet name=\"COM_Settings\" r:id=\"rId1\"/></sheets></workbook>",
            ),
            (
                "xl/_rels/workbook.xml.rels",
                "<Relationships><Relationship Id=\"rId1\" Target=\"worksheets/sheet1.xml\"/></Relationships>",
            ),
            ("xl/worksheets/sheet1.xml", sheet.as_str()),
        ] {
            archive.start_file(name, options).expect("xlsx entry");
            archive
                .write_all(contents.as_bytes())
                .expect("xlsx contents");
        }
        archive.finish().expect("finish xlsx");
        path
    }

    fn request(path: PathBuf) -> ConfigValidateRequestV1 {
        ConfigValidateRequestV1 {
            config: path,
            profile: "r480".to_owned(),
            reader: None,
            fix_ids: Vec::new(),
            overrides: Vec::new(),
            json: true,
            materialized_json: false,
        }
    }

    #[test]
    fn schema_and_catalog_are_exactly_bound() {
        let schema = load_schema().expect("schema");
        assert_eq!(schema.parameters.len(), 235);
        assert_eq!(
            load_behavior_catalog().expect("behavior")["schema_version"],
            1
        );
        load_consumption_registry().expect("registry");
    }

    #[test]
    fn request_rejects_duplicate_override_before_file_read() {
        let input = ConfigValidateRequestV1 {
            config: PathBuf::from("missing.csv"),
            profile: "r480".to_owned(),
            reader: None,
            fix_ids: Vec::new(),
            overrides: vec!["f_b=1".to_owned(), "f_b=2".to_owned()],
            json: true,
            materialized_json: false,
        };
        assert!(matches!(
            input.validate(),
            Err(ConfigValidateErrorV1::Override(_))
        ));
    }

    #[test]
    fn profile_edges_follow_upstream_cli() {
        let input = ConfigValidateRequestV1 {
            config: PathBuf::from("missing.csv"),
            profile: "custom".to_owned(),
            reader: Some("standard".to_owned()),
            fix_ids: vec!["fix.erl_best_phase".to_owned()],
            overrides: Vec::new(),
            json: true,
            materialized_json: false,
        };
        assert!(input.validate().is_ok());
    }

    #[test]
    fn duplicate_package_fix_is_rejected() {
        let path = csv_file(".START,A\nx,1\n.END,\n.START,A\nx,1\n.END,\n");
        let mut input = request(path.clone());
        input.profile = "custom".to_owned();
        input.fix_ids = vec!["fix.reject_duplicate_package_name".to_owned()];
        let error = config_validate_v1(&input).expect_err("duplicate package");
        assert!(error.to_string().contains("duplicate package"));
        fs::remove_file(path).expect("cleanup");
    }

    #[test]
    fn literal_and_default_catalog_are_executable() {
        assert_eq!(
            resolve_default(
                "0.5",
                &BTreeMap::new(),
                &BTreeMap::new(),
                &BTreeSet::new(),
                &BTreeSet::new(),
            )
            .expect("literal")
            .value,
            ResolvedDefaultV1::Scalar(0.5)
        );
    }

    #[test]
    fn override_keys_are_canonical_and_case_folded_duplicates_fail() {
        let schema = load_schema().expect("schema");
        let overrides = BTreeMap::from([("F_B".to_owned(), "53.125".to_owned())]);
        let canonical = canonicalize_override_keys(&schema, overrides).expect("canonical override");
        assert_eq!(canonical.get("f_b").map(String::as_str), Some("53.125"));
        assert!(matches!(
            parse_overrides(&["f_b=1".to_owned(), "F_B=2".to_owned()]),
            Err(ConfigValidateErrorV1::Override(_))
        ));
        assert!(
            canonicalize_override_keys(
                &schema,
                BTreeMap::from([("c(4)".to_owned(), "0.1".to_owned())])
            )
            .is_err()
        );
    }

    #[test]
    fn count_and_array_boundaries_fail_closed() {
        for value in [
            f64::NAN,
            f64::INFINITY,
            -1.0,
            1.5,
            (MAX_COUNT_VALUE + 1) as f64,
        ] {
            assert!(bounded_integer(value, "count", 0).is_err());
        }
        assert_eq!(bounded_integer(2.0, "count", 1).expect("count"), 2);
        assert!(cell_value(&CellValueV1::Number(f64::NAN)).is_err());
        assert!(
            cell_value(&CellValueV1::Array {
                dims: vec![u32::MAX, u32::MAX],
                data: vec![1.0],
            })
            .is_err()
        );
        assert!(
            cell_value(&CellValueV1::Array {
                dims: vec![1],
                data: vec![f64::INFINITY],
            })
            .is_err()
        );
    }

    #[test]
    fn core_count_fields_require_finite_bounded_integers() {
        let mut parameters = BTreeMap::from([
            ("fb".to_owned(), ResolvedDefaultV1::Scalar(53.125e9)),
            ("samples_per_ui".to_owned(), ResolvedDefaultV1::Scalar(32.5)),
            ("levels".to_owned(), ResolvedDefaultV1::Scalar(4.0)),
            ("f_r".to_owned(), ResolvedDefaultV1::Scalar(4.0)),
        ]);
        assert!(derive_core_parameters(&mut parameters, &mut BTreeSet::new()).is_err());
        parameters.insert("samples_per_ui".to_owned(), ResolvedDefaultV1::Scalar(32.0));
        parameters.insert("levels".to_owned(), ResolvedDefaultV1::Scalar(f64::NAN));
        assert!(derive_core_parameters(&mut parameters, &mut BTreeSet::new()).is_err());
    }

    #[test]
    fn fingerprint_writer_matches_python_types_float_spelling_and_specials() {
        let parameters = json!({"z": 1.0});
        let options = json!({
            "f": 1e-5,
            "i": 2.0,
            "special": {"$special_float": "Infinity"},
            "unicode": "π"
        });
        let bytes = canonical_materialized_bytes(
            &parameters,
            &options,
            &BTreeSet::new(),
            &BTreeSet::from(["i".to_owned()]),
        )
        .expect("canonical payload");
        assert_eq!(
            String::from_utf8(bytes).expect("ASCII canonical payload"),
            r#"{"options":{"f":1e-05,"i":2,"special":{"__float__":"inf"},"unicode":"\u03c0"},"parameters":{"z":1.0}}"#
        );
        assert_eq!(python_float_repr(1e-5).expect("small float"), "1e-05");
        assert_eq!(
            python_float_repr(9.5909e-5).expect("small fixed float"),
            "9.5909e-05"
        );
        assert_eq!(python_float_repr(1e-4).expect("fixed threshold"), "0.0001");
        assert_eq!(python_float_repr(1e16).expect("large threshold"), "1e+16");
        assert_eq!(python_float_repr(-0.0).expect("negative zero"), "-0.0");
    }

    #[test]
    fn fingerprint_writer_sorts_nested_keys_and_escapes_python_strings() {
        let parameters = json!({
            "é": "line\nquote\"",
            "astral": "😀",
            "control": "\u{0001}"
        });
        let options = json!({"b": [true, null], "a": {"z": 1.0, "a": 2.0}});
        let bytes =
            canonical_materialized_bytes(&parameters, &options, &BTreeSet::new(), &BTreeSet::new())
                .expect("canonical payload");
        assert_eq!(
            String::from_utf8(bytes).expect("ASCII canonical payload"),
            r#"{"options":{"a":{"a":2.0,"z":1.0},"b":[true,null]},"parameters":{"astral":"\ud83d\ude00","control":"\u0001","\u00e9":"line\nquote\""}}"#
        );
    }

    #[test]
    fn fingerprint_distinguishes_python_integer_and_float_scalars() {
        let parameters = json!({"n": 2.0});
        let options = json!({});
        assert_eq!(
            materialized_fingerprint(
                &parameters,
                &options,
                &BTreeSet::from(["n".to_owned()]),
                &BTreeSet::new(),
            )
            .expect("integer fingerprint"),
            "06195e8effb1a430714e2d9327bbcd7d8016ac3e3c2b0ebe120cd21d9581fdd2"
        );
        assert_eq!(
            materialized_fingerprint(&parameters, &options, &BTreeSet::new(), &BTreeSet::new(),)
                .expect("float fingerprint"),
            "a3cea6b1a1226ec898b7ff5010eefa460587857fc7d6f761905034d40fe2b261"
        );
    }

    #[test]
    fn fingerprint_writer_enforces_single_cumulative_and_unicode_byte_limits() {
        let empty = BTreeSet::new();
        let large = json!({"payload": "x".repeat(64)});
        let single_error =
            canonical_materialized_bytes_with_limit(&large, &json!({}), &empty, &empty, 32)
                .expect_err("single large string must be bounded");
        assert!(
            single_error
                .to_string()
                .contains("fingerprint exceeds 32-byte")
        );

        let one = json!({"a": "123456"});
        let one_bytes =
            canonical_materialized_bytes_with_limit(&one, &json!({}), &empty, &empty, 256)
                .expect("one string");
        let two = json!({"a": "123456", "b": "123456"});
        let cumulative_error = canonical_materialized_bytes_with_limit(
            &two,
            &json!({}),
            &empty,
            &empty,
            one_bytes.len(),
        )
        .expect_err("cumulative strings must be bounded");
        assert!(cumulative_error.to_string().contains("fingerprint exceeds"));

        let ascii = json!({"u": "aaaa"});
        let ascii_bytes =
            canonical_materialized_bytes_with_limit(&ascii, &json!({}), &empty, &empty, 256)
                .expect("ASCII string");
        let unicode = json!({"u": "😀"});
        let unicode_error = canonical_materialized_bytes_with_limit(
            &unicode,
            &json!({}),
            &empty,
            &empty,
            ascii_bytes.len(),
        )
        .expect_err("Unicode surrogate expansion must be bounded");
        assert!(unicode_error.to_string().contains("fingerprint exceeds"));

        let mut defaults = BTreeMap::from([(
            "a".to_owned(),
            ResolvedDefaultV1::String("123456".to_owned()),
        )]);
        let one_default_bytes =
            resolved_value_owned_bytes(defaults.get("a").expect("value")).expect("default bytes");
        assert_eq!(one_default_bytes, 6);
        defaults.insert(
            "b".to_owned(),
            ResolvedDefaultV1::String("123456".to_owned()),
        );
        let default_error = validate_materialized_storage_budget_with_limit(
            &defaults,
            &BTreeMap::new(),
            one_default_bytes + 1,
        )
        .expect_err("cumulative default copies must be bounded");
        assert!(default_error.to_string().contains("default copies exceed"));
    }

    #[test]
    fn matrix_json_projection_recurses_special_float_envelopes() {
        let matrix =
            ResolvedDefaultV1::Matrix(vec![vec![f64::INFINITY, f64::NEG_INFINITY, f64::NAN, 1.0]]);
        assert_eq!(
            json_value(&matrix),
            json!([[
                {"$special_float": "Infinity"},
                {"$special_float": "-Infinity"},
                {"$special_float": "NaN"},
                1.0
            ]])
        );
    }

    #[test]
    fn derive_core_parameters_removes_integer_origin_from_derived_floats() {
        let mut parameters = BTreeMap::from([
            ("fb".to_owned(), ResolvedDefaultV1::Scalar(53.125e9)),
            ("samples_per_ui".to_owned(), ResolvedDefaultV1::Scalar(32.0)),
            ("levels".to_owned(), ResolvedDefaultV1::Scalar(4.0)),
            ("f_r".to_owned(), ResolvedDefaultV1::Scalar(4.0)),
            ("fb_BT_cutoff".to_owned(), ResolvedDefaultV1::Scalar(1.0)),
        ]);
        let mut integer_parameters = BTreeSet::from(["fb_BT_cutoff".to_owned()]);
        derive_core_parameters(&mut parameters, &mut integer_parameters).expect("derived core");
        assert_eq!(
            parameters.get("fb_BT_cutoff"),
            Some(&ResolvedDefaultV1::Scalar(1.892148e0))
        );
        assert!(!integer_parameters.contains("fb_BT_cutoff"));
        for key in ["ui", "sample_dt", "sigma_X", "fb_BW_cutoff"] {
            assert!(!integer_parameters.contains(key), "{key} must be float");
        }
        let parameters_json = json_map(&parameters);
        let options_json = json!({});
        assert_eq!(
            parameters_json.get("fb_BT_cutoff"),
            Some(&json!(1.892148_f64))
        );
        let digest = materialized_fingerprint(
            &parameters_json,
            &options_json,
            &integer_parameters,
            &BTreeSet::new(),
        )
        .expect("derived float fingerprint");
        assert_eq!(digest.len(), 64);
    }

    #[test]
    fn xlsx_integer_source_to_derived_float_reaches_digest_boundary() {
        let path = xlsx_file(&[
            ("A_DD", "0.02"),
            ("b_max(1)", "0.4"),
            ("c(0)", "0.54"),
            ("Delta_f", "10000000"),
            ("DER_0", "0.00001"),
            ("eta_0", "0.000000041"),
            ("f_b", "53125000000"),
            ("f_min", "50000000"),
            ("g_DC", "[-13 -12]"),
            ("Include PCB", "0"),
            ("L", "4"),
            ("M", "32"),
            ("N_b", "4"),
            ("R_0", "50"),
            ("R_LM", "0.95"),
            ("RESULT_DIR", "."),
            ("sigma_RJ", "0.01"),
            ("SNR_TX", "[32.5 32.5]"),
            ("TDR_f_BT_3db", "1"),
        ]);
        let request = request(path.clone());
        let profile = request.validate().expect("profile");
        let schema = load_schema().expect("schema");
        let settings = load_settings(&path).expect("xlsx settings");
        let (rows, packages, _) = split_packages(&settings, &profile).expect("package split");
        let materialized = materialize_r480(&schema, &rows, &packages, &BTreeMap::new(), &profile)
            .expect("materialize");
        assert!(!materialized.integer_parameters.contains("fb_BT_cutoff"));
        let parameters_json = json_map(&materialized.parameters);
        let options_json = json_map(&materialized.options);
        assert_eq!(
            parameters_json.get("fb_BT_cutoff"),
            Some(&json!(1.892148_f64))
        );
        let digest = materialized_fingerprint(
            &parameters_json,
            &options_json,
            &materialized.integer_parameters,
            &materialized.integer_options,
        )
        .expect("materialized digest");
        assert_eq!(digest.len(), 64);
        fs::remove_file(path).expect("cleanup");
    }

    #[test]
    fn python_float_repr_matches_nextafter_thresholds_subnormal_and_maximum() {
        let below_small = f64::from_bits(1e-4_f64.to_bits() - 1);
        let above_small = f64::from_bits(1e-4_f64.to_bits() + 1);
        let below_large = f64::from_bits(1e16_f64.to_bits() - 1);
        let above_large = f64::from_bits(1e16_f64.to_bits() + 1);
        assert_eq!(
            python_float_repr(below_small).expect("below small threshold"),
            "9.999999999999999e-05"
        );
        assert_eq!(python_float_repr(1e-4).expect("small threshold"), "0.0001");
        assert_eq!(
            python_float_repr(above_small).expect("above small threshold"),
            "0.00010000000000000002"
        );
        assert_eq!(
            python_float_repr(below_large).expect("below large threshold"),
            "9999999999999998.0"
        );
        assert_eq!(python_float_repr(1e16).expect("large threshold"), "1e+16");
        assert_eq!(
            python_float_repr(above_large).expect("above large threshold"),
            "1.0000000000000002e+16"
        );
        assert_eq!(
            python_float_repr(f64::from_bits(1)).expect("subnormal"),
            "5e-324"
        );
        assert_eq!(
            python_float_repr(f64::MAX).expect("maximum"),
            "1.7976931348623157e+308"
        );
        assert_eq!(
            python_float_repr(-below_small).expect("negative below small"),
            "-9.999999999999999e-05"
        );
    }
}
