use jsonschema::{Draft, Resource, Validator};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    env, fs,
    path::{Path, PathBuf},
};

fn read_json(path: &Path) -> Value {
    serde_json::from_str(&fs::read_to_string(path).expect("read fixture")).expect("parse fixture")
}

fn read_case_document(
    fixture_root: &Path,
    case_dir: &Path,
    name: &str,
) -> Result<Value, &'static str> {
    let root = fixture_root.canonicalize().expect("canonical fixture root");
    let path = case_dir
        .join(name)
        .canonicalize()
        .expect("canonical fixture document");
    if !path.starts_with(&root) {
        return Err("fixture_path_escape");
    }
    Ok(read_json(&path))
}

fn schema_name(schema_id: &str) -> Option<&'static str> {
    match schema_id {
        "sipi.run-request.v1" => Some("run-request.v1.schema.json"),
        "sipi.run-result.v1" => Some("run-result.v1.schema.json"),
        "sipi.backend-execution-request.v1" => Some("backend-execution-request.v1.schema.json"),
        "sipi.backend-execution-result.v1" => Some("backend-execution-result.v1.schema.json"),
        "sipi.artifact-ref.v1" => Some("artifact-ref.v1.schema.json"),
        "sipi.run-event.v1" => Some("run-event.v1.schema.json"),
        "sipi.engine-capabilities.v1" => Some("engine-capabilities.v1.schema.json"),
        "sipi.validation-report.v1" => Some("validation-report.v1.schema.json"),
        _ => None,
    }
}

const RESOURCE_FIELDS: [&str; 5] = [
    "wall_time_s",
    "cpu_time_s",
    "memory_bytes",
    "process_count",
    "artifact_bytes",
];

fn terminal_valid(value: &Value) -> bool {
    match value["status"].as_str() {
        Some("succeeded") => value["error"].is_null(),
        Some("cancelled") => {
            value["error"].is_object() && value["error"]["category"] == "Cancelled"
        }
        Some("failed") => value["error"].is_object() && value["error"]["category"] != "Cancelled",
        _ => false,
    }
}

fn resource_slice_valid(parent: &Value, child: &Value, enforcement: &Value) -> bool {
    if parent["enforcement"] != child["enforcement"] {
        return false;
    }
    RESOURCE_FIELDS.iter().all(|field| {
        let parent_limit = &parent[*field];
        let child_limit = &child[*field];
        let assigned = !child_limit.is_null();
        let bounded = if parent_limit.is_null() {
            child_limit.is_null()
        } else {
            !child_limit.is_null() && child_limit.as_f64() <= parent_limit.as_f64()
        };
        let enforceable = !assigned
            || if child["enforcement"] == "required" {
                enforcement[*field] == "hard"
            } else {
                enforcement[*field] != "unsupported"
            };
        !(!parent_limit.is_null() && child_limit.is_null()) && bounded && enforceable
    })
}

fn run_result_terminal_valid(document: &Value) -> bool {
    let executions = match document["backend_executions"].as_array() {
        Some(value) => value,
        None => return false,
    };
    if !terminal_valid(document)
        || (document["status"] == "succeeded"
            && (executions.is_empty()
                || executions.iter().any(|item| item["status"] != "succeeded")))
    {
        return false;
    }
    if executions.iter().any(|item| {
        !terminal_valid(item)
            || (item["status"] == "succeeded"
                && (item["domain_result_schema"].is_null()
                    || item["artifacts"].as_array().is_none_or(Vec::is_empty)))
    }) {
        return false;
    }
    true
}

fn run_result_selection_valid(document: &Value) -> bool {
    let executions = match document["backend_executions"].as_array() {
        Some(value) => value,
        None => return false,
    };
    let selection = &document["selection_requested"];
    let roles: Vec<&Value> = executions.iter().map(|item| &item["role"]).collect();
    match selection["mode"].as_str() {
        Some("strict") => {
            roles.iter().all(|role| **role == "primary")
                && executions.len() <= 1
                && executions
                    .first()
                    .is_none_or(|item| item["engine_instance_id"] == selection["instance"])
                && document["fallback_trace"]
                    .as_array()
                    .is_some_and(Vec::is_empty)
                && document["comparison"]
                    .as_object()
                    .is_some_and(|value| value.is_empty())
        }
        Some("auto") => {
            let trace = document["fallback_trace"]
                .as_array()
                .map(|items| {
                    items
                        .iter()
                        .map(|item| item["instance"].clone())
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default();
            let candidates = selection["candidates"]
                .as_array()
                .cloned()
                .unwrap_or_default();
            roles.iter().all(|role| **role == "primary")
                && executions.len() <= 1
                && trace
                    == candidates
                        .iter()
                        .take(trace.len())
                        .cloned()
                        .collect::<Vec<_>>()
                && (executions.is_empty()
                    && (document["status"] == "cancelled" || trace == candidates)
                    || executions.first().is_some_and(|item| {
                        trace.len() < candidates.len()
                            && item["engine_instance_id"] == candidates[trace.len()]
                    }))
                && document["comparison"]
                    .as_object()
                    .is_some_and(|value| value.is_empty())
        }
        Some("compare") => {
            roles.len() == 2
                && roles.iter().any(|role| **role == "reference")
                && roles.iter().any(|role| **role == "candidate")
                && executions.iter().all(|item| {
                    item["engine_instance_id"] == selection[&item["role"].as_str().unwrap_or("")]
                })
                && document["comparison"]["profile"] == selection["comparison_profile"]
                && document["fallback_trace"]
                    .as_array()
                    .is_some_and(Vec::is_empty)
        }
        _ => false,
    }
}

fn run_result_error(document: &Value) -> Option<&'static str> {
    if !run_result_terminal_valid(document) {
        Some("terminal_state")
    } else if !run_result_selection_valid(document) {
        Some("selection")
    } else {
        None
    }
}

fn backend_result_valid(document: &Value) -> bool {
    terminal_valid(document)
        && !(document["status"] == "succeeded"
            && (document["domain_result_schema"].is_null()
                || (document.get("domain_result").is_none()
                    && document["artifacts"].as_array().is_some_and(Vec::is_empty))))
}

fn validation_report_valid(document: &Value) -> bool {
    document["valid"].as_bool().is_some_and(|valid| {
        valid
            != document["errors"]
                .as_array()
                .is_some_and(|errors| !errors.is_empty())
    })
}

fn capabilities_valid(document: &Value) -> bool {
    let capabilities = match document["capabilities"].as_array() {
        Some(value) => value,
        None => return false,
    };
    let keys: Vec<String> = capabilities
        .iter()
        .map(|item| {
            [
                "operation",
                "payload_schema",
                "behavior_profile",
                "execution_mode",
            ]
            .iter()
            .map(|field| item[*field].to_string())
            .collect::<Vec<_>>()
            .join("\u{1f}")
                + "\u{1f}"
                + document["engine_instance_id"]
                    .as_str()
                    .expect("engine instance")
                + "\u{1f}"
                + document["platform"]["os"].as_str().expect("platform os")
                + "\u{1f}"
                + document["platform"]["architecture"]
                    .as_str()
                    .expect("platform architecture")
        })
        .collect();
    keys.len() == keys.iter().collect::<std::collections::BTreeSet<_>>().len()
}

fn semantic_valid(case: &Value, document: &Value) -> bool {
    match case["entrypoint"].as_str() {
        Some("run_request") => {
            let selection = &document["backend_selection"];
            selection.get("allow_internal") != Some(&Value::Bool(true))
                && (selection["mode"] != "compare"
                    || selection["reference"] != selection["candidate"])
                && (selection["mode"] != "auto"
                    || selection["fallback_on"].as_array().is_some_and(|items| {
                        items.len() == 2
                            && items.iter().any(|item| item == "EngineUnavailable")
                            && items.iter().any(|item| item == "UnsupportedCapability")
                    }))
        }
        Some("run_result") => run_result_error(document).is_none(),
        Some("backend_result") => backend_result_valid(document),
        Some("validation_report") => validation_report_valid(document),
        Some("capabilities") => capabilities_valid(document),
        Some("event") => match document["scope"].as_str() {
            Some("project") => {
                document["analysis_id"].is_null()
                    && document["attempt_id"].is_null()
                    && document["backend_execution_id"].is_null()
            }
            Some("analysis") => {
                !document["analysis_id"].is_null()
                    && document["attempt_id"].is_null()
                    && document["backend_execution_id"].is_null()
            }
            Some("attempt") => {
                !document["analysis_id"].is_null()
                    && !document["attempt_id"].is_null()
                    && document["backend_execution_id"].is_null()
            }
            Some("backend_execution") => {
                !document["analysis_id"].is_null()
                    && !document["attempt_id"].is_null()
                    && !document["backend_execution_id"].is_null()
            }
            _ => false,
        },
        _ => true,
    }
}

fn run_request_error(document: &Value) -> Option<&'static str> {
    let selection = &document["backend_selection"];
    if selection["mode"] == "compare" && selection["reference"] == selection["candidate"] {
        Some("selection")
    } else if selection["mode"] == "auto"
        && !selection["fallback_on"].as_array().is_some_and(|items| {
            items.len() == 2
                && items.iter().any(|item| item == "EngineUnavailable")
                && items.iter().any(|item| item == "UnsupportedCapability")
        })
    {
        Some("selection")
    } else if selection.get("allow_internal") == Some(&Value::Bool(true)) {
        Some("internal_policy")
    } else {
        None
    }
}

fn semantic_error(case: &Value, document: &Value) -> Option<&'static str> {
    if case["entrypoint"] == "run_request" {
        return run_request_error(document);
    }
    if case["entrypoint"] == "run_result" {
        return run_result_error(document);
    }
    if semantic_valid(case, document) {
        return None;
    }
    match case["entrypoint"].as_str() {
        Some("backend_result") => Some("terminal_state"),
        Some("validation_report") => Some("validity"),
        Some("capabilities") => Some("duplicate_capability"),
        Some("event") => Some("scope"),
        _ => Some("semantic"),
    }
}

fn schema_valid(schema_root: &Path, name: &str, document: &Value) -> bool {
    let schema = read_json(&schema_root.join(name));
    let mut options = Validator::options()
        .with_draft(Draft::Draft202012)
        .with_base_uri("file:///sipi/schemas/");
    for relative in [
        "run-request.v1.schema.json",
        "artifact-ref.v1.schema.json",
        "run-event.v1.schema.json",
        "_defs/runtime-validation.v1.schema.json",
        "_defs/provenance.v1.schema.json",
    ] {
        let content = read_json(&schema_root.join(relative));
        options = options.with_resource(
            relative,
            Resource::from_contents(content.clone()).expect("schema resource"),
        );
        options = options.with_resource(
            format!("file:///sipi/schemas/{relative}"),
            Resource::from_contents(content).expect("schema resource"),
        );
    }
    options
        .build(&schema)
        .expect("compile schema")
        .is_valid(document)
}

fn validate(fixture_root: &Path, schema_root: &Path, case: &Value) -> Value {
    if !case["required_languages"]
        .as_array()
        .expect("required languages")
        .iter()
        .any(|language| language == "rust")
    {
        return json!({"id":case["id"],"decision":"not_required","phase":"not_required"});
    }
    if case.get("deferred_to").is_some() {
        return json!({"id":case["id"],"decision":"deferred","phase":case["deferred_to"]});
    }
    let case_dir = fixture_root.join(case["path"].as_str().expect("case path"));
    let case_data = read_json(&case_dir.join("case.json"));
    let documents = case_data["documents"].as_object().expect("documents");
    if case["entrypoint"] == "selection_chain" {
        let run_request = match read_case_document(
            fixture_root,
            &case_dir,
            documents["run_request"].as_str().unwrap(),
        ) {
            Ok(document) => document,
            Err(code) => {
                return json!({"id":case["id"],"decision":"reject","phase":"integrity","code":code});
            }
        };
        let backend_request = match read_case_document(
            fixture_root,
            &case_dir,
            documents["backend_request"].as_str().unwrap(),
        ) {
            Ok(document) => document,
            Err(code) => {
                return json!({"id":case["id"],"decision":"reject","phase":"integrity","code":code});
            }
        };
        let backend_result = match read_case_document(
            fixture_root,
            &case_dir,
            documents["backend_result"].as_str().unwrap(),
        ) {
            Ok(document) => document,
            Err(code) => {
                return json!({"id":case["id"],"decision":"reject","phase":"integrity","code":code});
            }
        };
        let run_result = match read_case_document(
            fixture_root,
            &case_dir,
            documents["run_result"].as_str().unwrap(),
        ) {
            Ok(document) => document,
            Err(code) => {
                return json!({"id":case["id"],"decision":"reject","phase":"integrity","code":code});
            }
        };
        if !schema_valid(schema_root, "run-request.v1.schema.json", &run_request)
            || !schema_valid(
                schema_root,
                "backend-execution-request.v1.schema.json",
                &backend_request,
            )
            || !schema_valid(
                schema_root,
                "backend-execution-result.v1.schema.json",
                &backend_result,
            )
            || !schema_valid(schema_root, "run-result.v1.schema.json", &run_result)
        {
            return json!({"id":case["id"],"decision":"reject","phase":"schema","code":"schema"});
        }
        if run_request["backend_selection"]["mode"] != "strict" {
            return json!({"id":case["id"],"decision":"reject","phase":"integrity","code":"fixture_configuration"});
        }
        let identity_fields = [
            "run_id",
            "analysis_id",
            "attempt_id",
            "operation",
            "payload_schema",
        ];
        let request_identity = identity_fields
            .iter()
            .all(|field| backend_request[*field] == run_request[*field]);
        let backend_identity = [
            "run_id",
            "analysis_id",
            "attempt_id",
            "backend_execution_id",
            "role",
            "engine_instance_id",
            "bundle_hash",
            "operation",
            "payload_schema",
        ]
        .iter()
        .all(|field| backend_result[*field] == backend_request[*field]);
        let result_identity = identity_fields
            .iter()
            .all(|field| run_result[*field] == run_request[*field]);
        if !request_identity {
            return json!({"id":case["id"],"decision":"reject","phase":"relation","code":"identity"});
        }
        if backend_request["selection_hash"] != case_data["parameters"]["selection_hash"] {
            return json!({"id":case["id"],"decision":"reject","phase":"relation","code":"selection_hash"});
        }
        if backend_request["role"] != "primary"
            || backend_request["engine_instance_id"] != run_request["backend_selection"]["instance"]
        {
            return json!({"id":case["id"],"decision":"reject","phase":"relation","code":"selection"});
        }
        if backend_result.get("comparison").is_some() {
            return json!({"id":case["id"],"decision":"reject","phase":"relation","code":"orchestration"});
        }
        if !backend_identity || !result_identity {
            return json!({"id":case["id"],"decision":"reject","phase":"relation","code":"identity"});
        }
        if !run_result["backend_executions"]
            .as_array()
            .is_some_and(|items| {
                items.iter().any(|item| {
                    item["backend_execution_id"] == backend_result["backend_execution_id"]
                })
            })
        {
            return json!({"id":case["id"],"decision":"reject","phase":"relation","code":"identity"});
        }
        if run_result["selection_requested"] != run_request["backend_selection"] {
            return json!({"id":case["id"],"decision":"reject","phase":"relation","code":"selection"});
        }
        return json!({"id":case["id"],"decision":"accept","phase":"relation","code":Value::Null});
    }
    if case["entrypoint"] == "resource_slice" {
        let parent = read_case_document(
            fixture_root,
            &case_dir,
            documents["parent"].as_str().unwrap(),
        )
        .expect("contained resource parent");
        let child = read_case_document(
            fixture_root,
            &case_dir,
            documents["child"].as_str().unwrap(),
        )
        .expect("contained resource child");
        let accepted = resource_slice_valid(
            &parent,
            &child,
            &read_case_document(
                fixture_root,
                &case_dir,
                documents["enforcement"].as_str().unwrap(),
            )
            .expect("contained enforcement"),
        );
        return json!({"id":case["id"],"decision":if accepted {"accept"} else {"reject"},"phase":if accepted {"relation"} else {"relation"}});
    }
    let document = read_case_document(
        fixture_root,
        &case_dir,
        documents["subject"].as_str().unwrap(),
    )
    .expect("contained subject");
    let name = schema_name(case["schema_id"].as_str().unwrap())
        .expect("schema supported by M1-06 Rust runner");
    let schema_valid = schema_valid(schema_root, name, &document);
    let semantic_error = if schema_valid {
        semantic_error(case, &document)
    } else {
        None
    };
    let decision = if schema_valid && semantic_error.is_none() {
        "accept"
    } else {
        "reject"
    };
    let phase = if !schema_valid {
        "schema"
    } else if semantic_error.is_some() {
        "semantic"
    } else {
        case["expect"]["phase"].as_str().unwrap()
    };
    let rendered = serde_json::to_string(&document).expect("render wire value");
    let round_trip: Value = serde_json::from_str(&rendered).expect("parse rendered wire value");
    let preserved = case["expect"]["preserve"]
        .as_array()
        .map_or(true, |pointers| {
            pointers.iter().all(|pointer| {
                let pointer = pointer.as_str().expect("JSON pointer");
                document.pointer(pointer).is_some()
                    && document.pointer(pointer) == round_trip.pointer(pointer)
            })
        });
    let code = if !schema_valid {
        Some("schema")
    } else {
        semantic_error
    };
    json!({"id":case["id"],"decision":if preserved { decision } else { "reject" },"phase":phase,"code":code,"preserved":preserved})
}

fn main() {
    let root = PathBuf::from(env::args().nth(1).expect("fixture root argument"));
    let suite = read_json(&root.join("suite.json"));
    let schemas = root
        .parent()
        .and_then(Path::parent)
        .and_then(Path::parent)
        .expect("repo root")
        .join("schemas");
    let mut results = BTreeMap::new();
    for case in suite["cases"].as_array().expect("cases") {
        let result = validate(&root, &schemas, case);
        results.insert(case["id"].as_str().unwrap().to_owned(), result);
    }
    println!(
        "{}",
        serde_json::to_string(
            &json!({"runner":"rust","results":results.values().collect::<Vec<_>>() })
        )
        .unwrap()
    );
}
