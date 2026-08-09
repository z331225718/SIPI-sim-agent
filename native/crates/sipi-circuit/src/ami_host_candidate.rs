//! Explicit, unpromoted process transport for the clean-room AMI host.
//!
//! This module is intentionally reachable only through `ami-host-candidate`.
//! It is not listed in `engine.lock` and must not be selected by production
//! resolution. It transports raw ABI buffers and lifecycle evidence only.

use std::ffi::OsString;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Component, Path, PathBuf};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use sipi_ami::ami::{AmiHostMetadata, parse_ami_parameters};
use sipi_ami::contract::{AmiGetWaveRequest, AmiInitRequest};
use sipi_ami::host::{AmiDll, AmiGetWaveOutcome, AmiModel};
use sipi_ami::parse_ibis;

use super::build_info;

const REQUEST_SCHEMA: &str = "agent-spice.ami-host-request.v1";
const LIFECYCLE_REQUEST_SCHEMA: &str = "agent-spice.ami-host-request.v2";
const RESULT_SCHEMA: &str = "agent-spice.ami-host-result.v1";
const RESULT_NAME: &str = "result.json";

pub(super) fn run(mut arguments: impl Iterator<Item = OsString>) -> Result<(), String> {
    if !cfg!(windows) {
        return Err("ami-host-candidate is available only on Windows".into());
    }

    let mut request_path = None;
    let mut output_dir = None;
    while let Some(argument) = arguments.next() {
        if argument == "--request" {
            request_path = Some(PathBuf::from(arguments.next().ok_or_else(candidate_usage)?));
        } else if argument == "--output-dir" {
            output_dir = Some(PathBuf::from(arguments.next().ok_or_else(candidate_usage)?));
        } else {
            return Err(candidate_usage());
        }
    }
    let request_path = fs::canonicalize(request_path.ok_or_else(candidate_usage)?)
        .map_err(|error| format!("failed to resolve candidate request: {error}"))?;
    let output_dir = output_dir.ok_or_else(candidate_usage)?;
    let output_dir = if output_dir.is_absolute() {
        output_dir
    } else {
        std::env::current_dir()
            .map_err(|error| format!("failed to resolve candidate output directory: {error}"))?
            .join(output_dir)
    };
    if output_dir.exists() {
        return Err(format!(
            "candidate output directory already exists: {}",
            output_dir.display()
        ));
    }

    let request_bytes = fs::read(&request_path).map_err(|error| {
        format!(
            "failed to read candidate request '{}': {error}",
            request_path.display()
        )
    })?;
    let request_sha256 = sha256_bytes(&request_bytes);
    let request: CandidateRequest = serde_json::from_slice(&request_bytes)
        .map_err(|error| format!("invalid candidate request: {error}"))?;
    request.validate()?;
    let request_root = request_path.parent().ok_or_else(|| {
        format!(
            "candidate request has no parent directory: {}",
            request_path.display()
        )
    })?;
    let completed = execute(&request, request_root, request_sha256)?;
    write_result(&output_dir, &completed)
}

fn candidate_usage() -> String {
    "agent-spice-sim ami-host-candidate --request <request.json> --output-dir <directory>".into()
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct CandidateRequest {
    schema: String,
    mode: CandidateMode,
    model: ModelFiles,
    expected_metadata: ExpectedMetadata,
    sample_interval_seconds: f64,
    bit_time_seconds: f64,
    ami_parameters_in: String,
    init_impulse: F64Input,
    get_wave: Option<GetWaveInput>,
    get_waves: Option<Vec<GetWaveInput>>,
}

impl CandidateRequest {
    fn validate(&self) -> Result<(), String> {
        if self.schema != REQUEST_SCHEMA && self.schema != LIFECYCLE_REQUEST_SCHEMA {
            return Err(format!(
                "unsupported AMI host request schema '{}'; expected {REQUEST_SCHEMA} or {LIFECYCLE_REQUEST_SCHEMA}",
                self.schema
            ));
        }
        match (
            self.schema.as_str(),
            self.mode,
            self.get_wave.is_some(),
            self.get_waves.as_ref(),
        ) {
            (REQUEST_SCHEMA, CandidateMode::Init, false, None)
            | (REQUEST_SCHEMA, CandidateMode::InitGetWave, true, None) => Ok(()),
            (REQUEST_SCHEMA, _, _, _) => Err("v1 request mode/getWave contract is invalid".into()),
            (LIFECYCLE_REQUEST_SCHEMA, CandidateMode::Init, false, None) => Ok(()),
            (LIFECYCLE_REQUEST_SCHEMA, CandidateMode::InitGetWaveSequence, false, Some(inputs))
                if !inputs.is_empty() =>
            {
                Ok(())
            }
            (LIFECYCLE_REQUEST_SCHEMA, _, _, _) => Err(
                "v2 request requires init or init-get-wave-sequence with non-empty getWaves".into(),
            ),
            _ => unreachable!("schema already validated"),
        }
    }
}

#[derive(Debug, Clone, Copy, Deserialize)]
#[serde(rename_all = "kebab-case")]
enum CandidateMode {
    Init,
    InitGetWave,
    InitGetWaveSequence,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct ModelFiles {
    ibis: FileInput,
    ami: FileInput,
    dll: FileInput,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct FileInput {
    path: PathBuf,
    sha256: String,
    byte_length: u64,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct ExpectedMetadata {
    ami_version: String,
    init_returns_impulse: bool,
    get_wave_exists: bool,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct F64Input {
    path: PathBuf,
    sha256: String,
    element_count: usize,
    byte_length: u64,
    encoding: String,
    endianness: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct GetWaveInput {
    waveform: F64Input,
    clock_capacity: usize,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct CandidateResult {
    schema: &'static str,
    request_sha256: String,
    mode: CandidateModeOutput,
    candidate: CandidateIdentity,
    model: ModelIdentity,
    metadata: MetadataOutput,
    lifecycle: LifecycleOutput,
    init: InitOutput,
    #[serde(skip_serializing_if = "Option::is_none")]
    get_wave: Option<GetWaveOutput>,
    #[serde(skip_serializing_if = "Option::is_none")]
    get_waves: Option<Vec<GetWaveOutput>>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "kebab-case")]
enum CandidateModeOutput {
    Init,
    InitGetWave,
    InitGetWaveSequence,
}

impl From<CandidateMode> for CandidateModeOutput {
    fn from(value: CandidateMode) -> Self {
        match value {
            CandidateMode::Init => Self::Init,
            CandidateMode::InitGetWave => Self::InitGetWave,
            CandidateMode::InitGetWaveSequence => Self::InitGetWaveSequence,
        }
    }
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct CandidateIdentity {
    mode: &'static str,
    executable_sha256: String,
    build_info: serde_json::Value,
    platform: String,
    primary_column: u8,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ModelIdentity {
    ibis: FileOutput,
    ami: FileOutput,
    dll: FileOutput,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct FileOutput {
    path: String,
    sha256: String,
    byte_length: u64,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct MetadataOutput {
    ami_version: String,
    init_returns_impulse: bool,
    get_wave_exists: bool,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct LifecycleOutput {
    init_succeeded: bool,
    get_wave_attempted: bool,
    close_succeeded: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    get_wave_call_count: Option<usize>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct InitOutput {
    impulse_response: Option<F64Output>,
    parameters_out: Option<String>,
    message: Option<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct GetWaveOutput {
    waveform: F64Output,
    clock_times: F64Output,
    parameters_out: Option<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct F64Output {
    path: String,
    sha256: String,
    element_count: usize,
    byte_length: u64,
    encoding: &'static str,
    endianness: &'static str,
}

struct PendingSidecar {
    name: String,
    values: Vec<f64>,
}

struct CompletedRun {
    result: CandidateResult,
    sidecars: Vec<PendingSidecar>,
}

fn execute(
    request: &CandidateRequest,
    request_root: &Path,
    request_sha256: String,
) -> Result<CompletedRun, String> {
    let ibis = read_file(request_root, &request.model.ibis, "IBIS model")?;
    let ami = read_file(request_root, &request.model.ami, "AMI parameter file")?;
    let dll = resolve_input_path(request_root, &request.model.dll.path, "AMI DLL")?;
    verify_file_identity(&dll, &request.model.dll, "AMI DLL")?;
    let ibis_text =
        std::str::from_utf8(&ibis).map_err(|error| format!("IBIS model is not UTF-8: {error}"))?;
    parse_ibis(ibis_text).map_err(|error| format!("invalid IBIS model: {error}"))?;
    let ami_text = std::str::from_utf8(&ami)
        .map_err(|error| format!("AMI parameter file is not UTF-8: {error}"))?;
    let tree = parse_ami_parameters(ami_text)
        .map_err(|error| format!("invalid AMI parameters: {error}"))?;
    let metadata = AmiHostMetadata::from_tree(&tree)
        .map_err(|error| format!("invalid AMI host metadata: {error}"))?;
    verify_metadata(&metadata, &request.expected_metadata)?;
    if matches!(
        request.mode,
        CandidateMode::InitGetWave | CandidateMode::InitGetWaveSequence
    ) && !metadata.get_wave_exists()
    {
        return Err("GetWave mode requires GetWave_Exists=true".into());
    }

    let init_values = read_f64_input(request_root, &request.init_impulse, "initImpulse")?;
    let init = AmiInitRequest::new(request.sample_interval_seconds, init_values)
        .map_err(|error| format!("invalid init request: {error}"))?;
    let parse_get_wave = |input: &GetWaveInput| {
        if input.clock_capacity == 0 {
            return Err("getWave clockCapacity must be greater than zero".into());
        }
        read_f64_input(request_root, &input.waveform, "getWave waveform")
            .and_then(|waveform| {
                AmiGetWaveRequest::new(request.sample_interval_seconds, waveform)
                    .map_err(|error| format!("invalid GetWave request: {error}"))
            })
            .map(|request| (request, input.clock_capacity))
    };
    let get_waves = match request.mode {
        CandidateMode::Init => Vec::new(),
        CandidateMode::InitGetWave => vec![parse_get_wave(
            request
                .get_wave
                .as_ref()
                .expect("v1 validation requires getWave"),
        )?],
        CandidateMode::InitGetWaveSequence => request
            .get_waves
            .as_ref()
            .expect("v2 validation requires getWaves")
            .iter()
            .map(parse_get_wave)
            .collect::<Result<Vec<_>, _>>()?,
    };

    let dll =
        AmiDll::load(&dll, &metadata).map_err(|error| format!("AMI DLL load failed: {error}"))?;
    let mut model = AmiModel::new(dll, metadata.clone());
    let init_outcome = model
        .initialize(&init, request.bit_time_seconds, &request.ami_parameters_in)
        .map_err(|error| format!("AMI_Init failed: {error}"))?;
    let get_wave_outcomes = get_waves
        .iter()
        .map(|(get_wave, clock_capacity)| {
            model
                .get_wave(get_wave, *clock_capacity)
                .map_err(|error| format!("AMI_GetWave failed: {error}"))
        })
        .collect::<Result<Vec<_>, _>>()?;
    model
        .close()
        .map_err(|error| format!("AMI_Close failed: {error}"))?;

    let init_impulse = init_outcome
        .response()
        .impulse_response()
        .map(|values| PendingSidecar {
            name: "init-impulse-response.f64le".into(),
            values: values.to_vec(),
        });
    let executable = std::env::current_exe()
        .map_err(|error| format!("failed to locate candidate executable: {error}"))?;
    let executable_sha256 = sha256_file(&executable, "candidate executable")?;
    let model = ModelIdentity {
        ibis: file_output(&request.model.ibis),
        ami: file_output(&request.model.ami),
        dll: file_output(&request.model.dll),
    };
    let metadata_output = MetadataOutput {
        ami_version: metadata.ami_version().to_owned(),
        init_returns_impulse: metadata.init_returns_impulse(),
        get_wave_exists: metadata.get_wave_exists(),
    };
    let candidate = CandidateIdentity {
        mode: "rust-host-candidate",
        executable_sha256,
        build_info: build_info(),
        platform: format!("windows-{}", std::env::consts::ARCH),
        primary_column: 0,
    };

    let mut sidecars = Vec::new();
    let init_impulse_output = init_impulse.as_ref().map(sidecar_output);
    if let Some(sidecar) = init_impulse {
        sidecars.push(sidecar);
    }
    let get_wave_attempted = !get_wave_outcomes.is_empty();
    let mut to_output = |index: usize, outcome: &AmiGetWaveOutcome| {
        let suffix = if matches!(request.mode, CandidateMode::InitGetWave) {
            String::new()
        } else {
            format!("-{index}")
        };
        let waveform = PendingSidecar {
            name: format!("get-wave{suffix}-response.f64le"),
            values: outcome.response().waveform().to_vec(),
        };
        let clocks = PendingSidecar {
            name: format!("clock-times{suffix}.f64le"),
            values: outcome.response().clock_times().to_vec(),
        };
        let output = GetWaveOutput {
            waveform: sidecar_output(&waveform),
            clock_times: sidecar_output(&clocks),
            parameters_out: outcome.parameters_out().map(str::to_owned),
        };
        sidecars.push(waveform);
        sidecars.push(clocks);
        output
    };
    let get_wave_output = if matches!(request.mode, CandidateMode::InitGetWave) {
        Some(to_output(0, &get_wave_outcomes[0]))
    } else {
        None
    };
    let get_waves_output = if matches!(request.mode, CandidateMode::InitGetWaveSequence) {
        Some(
            get_wave_outcomes
                .iter()
                .enumerate()
                .map(|(index, outcome)| to_output(index, outcome))
                .collect(),
        )
    } else {
        None
    };

    Ok(CompletedRun {
        result: CandidateResult {
            schema: RESULT_SCHEMA,
            request_sha256,
            mode: request.mode.into(),
            candidate,
            model,
            metadata: metadata_output,
            lifecycle: LifecycleOutput {
                init_succeeded: true,
                get_wave_attempted,
                close_succeeded: true,
                get_wave_call_count: matches!(request.mode, CandidateMode::InitGetWaveSequence)
                    .then_some(get_wave_outcomes.len()),
            },
            init: InitOutput {
                impulse_response: init_impulse_output,
                parameters_out: init_outcome.parameters_out().map(str::to_owned),
                message: init_outcome.message().map(str::to_owned),
            },
            get_wave: get_wave_output,
            get_waves: get_waves_output,
        },
        sidecars,
    })
}

fn write_result(output_dir: &Path, completed: &CompletedRun) -> Result<(), String> {
    let parent = output_dir.parent().ok_or_else(|| {
        format!(
            "candidate output directory has no parent: {}",
            output_dir.display()
        )
    })?;
    if !parent.is_dir() {
        return Err(format!(
            "candidate output parent does not exist: {}",
            parent.display()
        ));
    }
    let output_name = output_dir
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or_else(|| "candidate output directory name must be valid Unicode".to_owned())?;
    let staging = parent.join(format!(".{output_name}.partial-{}", std::process::id()));
    if staging.exists() {
        return Err(format!(
            "candidate staging directory already exists: {}",
            staging.display()
        ));
    }
    fs::create_dir(&staging)
        .map_err(|error| format!("failed to create candidate staging directory: {error}"))?;
    let outcome = write_result_staging(&staging, completed);
    if outcome.is_err() {
        let _ = fs::remove_dir_all(&staging);
        return outcome;
    }
    fs::rename(&staging, output_dir)
        .map_err(|error| format!("failed to publish candidate output atomically: {error}"))
}

fn write_result_staging(staging: &Path, completed: &CompletedRun) -> Result<(), String> {
    for sidecar in &completed.sidecars {
        write_new_file(&staging.join(&sidecar.name), &f64_bytes(&sidecar.values))?;
    }
    let json = serde_json::to_vec_pretty(&completed.result)
        .map_err(|error| format!("failed to serialize candidate result: {error}"))?;
    write_new_file(&staging.join(RESULT_NAME), &json)
}

fn sidecar_output(sidecar: &PendingSidecar) -> F64Output {
    let bytes = f64_bytes(&sidecar.values);
    F64Output {
        path: sidecar.name.to_owned(),
        sha256: sha256_bytes(&bytes),
        element_count: sidecar.values.len(),
        byte_length: u64::try_from(bytes.len()).expect("sidecar length fits u64"),
        encoding: "f64le",
        endianness: "little",
    }
}

fn read_file(root: &Path, input: &FileInput, label: &str) -> Result<Vec<u8>, String> {
    let path = resolve_input_path(root, &input.path, label)?;
    let bytes = fs::read(&path).map_err(|error| format!("failed to read {label}: {error}"))?;
    verify_bytes_identity(&bytes, input, label)?;
    Ok(bytes)
}

fn verify_file_identity(path: &Path, input: &FileInput, label: &str) -> Result<(), String> {
    let bytes = fs::read(path).map_err(|error| format!("failed to read {label}: {error}"))?;
    verify_bytes_identity(&bytes, input, label)
}

fn verify_bytes_identity(bytes: &[u8], input: &FileInput, label: &str) -> Result<(), String> {
    let actual_length = u64::try_from(bytes.len()).expect("buffer length fits u64");
    if actual_length != input.byte_length {
        return Err(format!(
            "{label} byteLength mismatch: expected {}, got {actual_length}",
            input.byte_length
        ));
    }
    let actual_hash = sha256_bytes(bytes);
    if !actual_hash.eq_ignore_ascii_case(&input.sha256) {
        return Err(format!("{label} sha256 mismatch"));
    }
    Ok(())
}

fn read_f64_input(root: &Path, input: &F64Input, label: &str) -> Result<Vec<f64>, String> {
    if input.encoding != "f64le" || input.endianness != "little" {
        return Err(format!("{label} must use f64le little-endian encoding"));
    }
    let expected_length = input
        .element_count
        .checked_mul(std::mem::size_of::<f64>())
        .ok_or_else(|| format!("{label} elementCount overflows byte length"))?;
    if u64::try_from(expected_length).expect("expected length fits u64") != input.byte_length {
        return Err(format!("{label} byteLength does not match elementCount"));
    }
    let path = resolve_input_path(root, &input.path, label)?;
    let bytes = fs::read(path).map_err(|error| format!("failed to read {label}: {error}"))?;
    let identity = FileInput {
        path: input.path.clone(),
        sha256: input.sha256.clone(),
        byte_length: input.byte_length,
    };
    verify_bytes_identity(&bytes, &identity, label)?;
    if bytes.len() % std::mem::size_of::<f64>() != 0 {
        return Err(format!("{label} contains trailing bytes"));
    }
    Ok(bytes
        .chunks_exact(std::mem::size_of::<f64>())
        .map(|chunk| f64::from_le_bytes(chunk.try_into().expect("f64 chunk is exact")))
        .collect())
}

fn resolve_input_path(root: &Path, relative: &Path, label: &str) -> Result<PathBuf, String> {
    if relative.is_absolute()
        || relative.components().any(|component| {
            matches!(
                component,
                Component::ParentDir | Component::RootDir | Component::Prefix(_)
            )
        })
    {
        return Err(format!(
            "{label} path must be relative to the request manifest"
        ));
    }
    let path = root.join(relative);
    if !path.is_file() {
        return Err(format!("{label} file does not exist: {}", path.display()));
    }
    Ok(path)
}

fn verify_metadata(metadata: &AmiHostMetadata, expected: &ExpectedMetadata) -> Result<(), String> {
    if metadata.ami_version() != expected.ami_version
        || metadata.init_returns_impulse() != expected.init_returns_impulse
        || metadata.get_wave_exists() != expected.get_wave_exists
    {
        return Err("AMI metadata does not match the request's pinned expectations".into());
    }
    Ok(())
}

fn file_output(input: &FileInput) -> FileOutput {
    FileOutput {
        path: input.path.to_string_lossy().into_owned(),
        sha256: input.sha256.clone(),
        byte_length: input.byte_length,
    }
}

fn write_new_file(path: &Path, bytes: &[u8]) -> Result<(), String> {
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .map_err(|error| format!("failed to create output '{}': {error}", path.display()))?;
    file.write_all(bytes)
        .and_then(|_| file.flush())
        .map_err(|error| format!("failed to write output '{}': {error}", path.display()))
}

fn f64_bytes(values: &[f64]) -> Vec<u8> {
    let mut bytes = Vec::with_capacity(std::mem::size_of_val(values));
    for value in values {
        bytes.extend_from_slice(&value.to_le_bytes());
    }
    bytes
}

fn sha256_file(path: &Path, label: &str) -> Result<String, String> {
    fs::read(path)
        .map_err(|error| format!("failed to read {label}: {error}"))
        .map(|bytes| sha256_bytes(&bytes))
}

fn sha256_bytes(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
