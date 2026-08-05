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
    if case["entrypoint"] == "resource_slice" {
        let parent = read_json(&case_dir.join(documents["parent"].as_str().unwrap()));
        let child = read_json(&case_dir.join(documents["child"].as_str().unwrap()));
        let accepted = parent["enforcement"] == child["enforcement"]
            && child["wall_time_s"].as_f64() <= parent["wall_time_s"].as_f64();
        return json!({"id":case["id"],"decision":if accepted {"accept"} else {"reject"},"phase":if accepted {"relation"} else {"relation"}});
    }
    let document = read_json(&case_dir.join(documents["subject"].as_str().unwrap()));
    let name = schema_name(case["schema_id"].as_str().unwrap())
        .expect("schema supported by M1-06 Rust runner");
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
    let validator = options.build(&schema).expect("compile schema");
    let schema_valid = validator.is_valid(&document);
    let semantic_valid = if case["entrypoint"] == "event" {
        match document["scope"].as_str() {
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
        }
    } else {
        true
    };
    let decision = if schema_valid && semantic_valid {
        "accept"
    } else {
        "reject"
    };
    let phase = if !schema_valid {
        "schema"
    } else if !semantic_valid {
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
    json!({"id":case["id"],"decision":if preserved { decision } else { "reject" },"phase":phase,"preserved":preserved})
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
