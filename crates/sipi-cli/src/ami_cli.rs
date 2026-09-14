#![forbid(unsafe_code)]

//! Bounded IBIS-AMI model execution gateway and runtime CLI adapter.
//!
//! This module provides the `sipi ami run` and `sipi ami help` CLI commands,
//! enabling safe, isolated execution of vendor IBIS-AMI models (DLL on Windows x64)
//! adhering to the IBIS 5.0 - 7.2 AMI ABI specifications (AMI_Init, AMI_GetWave, AMI_Close).

use std::{
    fs::{self, File},
    io::{BufWriter, Read, Write},
    path::Path,
};

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use sipi_ami_host::{
    AmiGetWaveRequestV1, AmiHostErrorV1, AmiHostV1, AmiInitRequestV1, DllSha256V1,
};
use sipi_ami_text::{ParseLimitsV1, parse_and_bind_v1};

pub const AMI_RECEIPT_SCHEMA: &str = "sipi.ami.receipt.v1";
const MAX_REQUEST_BYTES: u64 = 64 * 1024 * 1024;
fn default_parse_limits() -> ParseLimitsV1 {
    ParseLimitsV1::try_new(65536, 16, 256, 1024).expect("valid parse limits")
}

#[derive(Debug)]
pub enum AmiFailure {
    Usage,
    InvalidInput(String),
    Io,
    ModelError(String),
}

impl AmiFailure {
    pub fn exit_code(&self) -> i32 {
        match self {
            Self::Usage => 64,
            Self::InvalidInput(_) => 2,
            Self::Io => 5,
            Self::ModelError(_) => 3,
        }
    }

    pub fn code(&self) -> &'static str {
        match self {
            Self::Usage => "usage",
            Self::InvalidInput(_) => "invalid_input",
            Self::Io => "operational_failure",
            Self::ModelError(_) => "model_execution_failure",
        }
    }

    pub fn message(&self) -> &str {
        match self {
            Self::Usage => "usage",
            Self::InvalidInput(msg) => msg,
            Self::Io => "i/o failure",
            Self::ModelError(msg) => msg,
        }
    }
}

impl From<std::io::Error> for AmiFailure {
    fn from(_: std::io::Error) -> Self {
        Self::Io
    }
}

impl From<AmiHostErrorV1> for AmiFailure {
    fn from(error: AmiHostErrorV1) -> Self {
        Self::ModelError(error.to_string())
    }
}

/// Typed request for the `sipi ami run` command.
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AmiRunRequestV1 {
    pub dll_path: String,
    #[serde(default)]
    pub dll_sha256: Option<String>,
    #[serde(default)]
    pub parameters_in: Option<String>,
    pub sample_interval_s: f64,
    pub bit_time_s: f64,
    pub impulse_matrix: Vec<f64>,
    pub rows: usize,
    #[serde(default)]
    pub aggressors: usize,
    #[serde(default)]
    pub waveform_in: Option<Vec<f64>>,
    #[serde(default)]
    pub clock_capacity: Option<usize>,
}

pub(crate) fn execute(action: &str, arguments: &[String]) -> Result<String, AmiFailure> {
    let result = match (action, arguments) {
        ("help", []) => json!({
            "schema": "sipi.ami.help.v1",
            "commands": [
                "sipi ami help",
                "sipi ami run REQUEST.json --output-dir NEW_DIRECTORY"
            ],
            "input_schema": "sipi.ami.request.v1",
            "supported_abis": ["AMI_Init", "AMI_GetWave", "AMI_Close"],
            "platform": "windows-x64",
            // Declared artifacts are exactly the ones `ami run` commits.
            // `impulse_out.csv` is deliberately absent: the pinned AMI host
            // exposes no in/out impulse matrix, so declaring it would promise an
            // artifact that no run can produce. `waveform_out.csv` is written
            // only when the request supplies `waveformIn`.
            "output_artifacts": [
                "request.json",
                "waveform_out.csv",
                "clocks.csv",
                "parameters_out.txt",
                "meta.json",
                "receipt.json"
            ]
        }),
        ("run", [request, option, output])
            if !request.starts_with('-') && option == "--output-dir" && !output.starts_with('-') =>
        {
            run_ami(Path::new(request), Path::new(output))?
        }
        _ => return Err(AmiFailure::Usage),
    };
    serde_json::to_string(&result).map_err(|_| AmiFailure::Io)
}

fn file_identity(path: &Path) -> Result<Value, AmiFailure> {
    let mut file = File::open(path)?;
    let mut hasher = Sha256::new();
    let mut buffer = [0u8; 8192];
    let mut byte_length = 0u64;
    loop {
        let count = file.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        hasher.update(&buffer[..count]);
        byte_length += count as u64;
    }
    Ok(json!({
        "byte_length": byte_length,
        "sha256": format!("{:x}", hasher.finalize()),
    }))
}

fn run_ami(request_path: &Path, output_dir: &Path) -> Result<Value, AmiFailure> {
    let file = File::open(request_path)?;
    if !file.metadata()?.is_file() {
        return Err(AmiFailure::InvalidInput("request is not a regular file".into()));
    }
    let mut bytes = Vec::new();
    file.take(MAX_REQUEST_BYTES + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > MAX_REQUEST_BYTES {
        return Err(AmiFailure::InvalidInput("request exceeds maximum byte budget".into()));
    }

    let req: AmiRunRequestV1 = serde_json::from_slice(&bytes)
        .map_err(|e| AmiFailure::InvalidInput(format!("invalid ami request JSON: {e}")))?;
    let base_dir = request_path.parent().unwrap_or_else(|| Path::new("."));
    let dll_full_path = if Path::new(&req.dll_path).is_absolute() {
        std::path::PathBuf::from(&req.dll_path)
    } else {
        base_dir.join(&req.dll_path)
    };

    if !dll_full_path.is_file() {
        return Err(AmiFailure::InvalidInput(format!(
            "DLL file not found: {}",
            dll_full_path.display()
        )));
    }

    let dll_bytes = fs::read(&dll_full_path)?;
    let dll_actual_hash = Sha256::digest(&dll_bytes);
    let expected_hash = if let Some(hex_str) = &req.dll_sha256 {
        let h = decode_hex_32(hex_str)
            .ok_or_else(|| AmiFailure::InvalidInput("invalid expected sha256 hex".into()))?;
        DllSha256V1::from_bytes(h)
    } else {
        DllSha256V1::from_bytes(dll_actual_hash.into())
    };

    let params_str = req.parameters_in.unwrap_or_else(|| "()".into());
    let binding = parse_and_bind_v1(params_str.as_bytes(), default_parse_limits())
        .map_err(|e| AmiFailure::InvalidInput(format!("parsing ami parameters failed: {e:?}")))?;

    let init_req = AmiInitRequestV1::try_new(
        req.impulse_matrix.clone(),
        req.rows,
        req.aggressors,
        req.sample_interval_s,
        req.bit_time_s,
    )?;

    // Prepare output directory
    if let Some(parent) = output_dir.parent().filter(|p| !p.as_os_str().is_empty()) {
        fs::create_dir_all(parent)?;
    }
    fs::create_dir(output_dir)?;

    // Save request
    fs::write(output_dir.join("request.json"), &bytes)?;

    // Load and execute AMI model
    #[cfg(windows)]
    {
        let session = AmiHostV1::open(&dll_full_path, expected_hash)?;
        let mut instance = session.initialize_v2(init_req, &binding, default_parse_limits())?;

        let init_params_out = instance.init_parameters_out().to_string();
        fs::write(output_dir.join("parameters_out.txt"), &init_params_out)?;

        // If waveform_in is supplied, run AMI_GetWave
        let mut wave_out = None;
        let mut clocks_out = Vec::new();
        let mut getwave_params_out = None;

        if let Some(waveform) = req.waveform_in {
            let clock_cap = req.clock_capacity.unwrap_or(waveform.len());
            let getwave_req = AmiGetWaveRequestV1::try_new(waveform, clock_cap)?;
            let gw_result = instance.get_wave_v2(getwave_req)?;

            let out_wave = gw_result.waveform().to_vec();
            clocks_out = gw_result.clocks_s().to_vec();
            getwave_params_out = Some(gw_result.parameters_out().to_string());

            // Write waveform_out.csv
            let wave_path = output_dir.join("waveform_out.csv");
            let mut writer = BufWriter::new(File::create(&wave_path)?);
            writeln!(writer, "index,time_s,waveform_v")?;
            for (idx, &val) in out_wave.iter().enumerate() {
                writeln!(writer, "{idx},{:.6e},{:.6e}", idx as f64 * req.sample_interval_s, val)?;
            }
            writer.flush()?;

            wave_out = Some(out_wave);
        }

        // Write clocks.csv
        let clocks_path = output_dir.join("clocks.csv");
        let mut writer = BufWriter::new(File::create(&clocks_path)?);
        writeln!(writer, "index,clock_time_s")?;
        for (idx, &clk) in clocks_out.iter().enumerate() {
            writeln!(writer, "{idx},{:.6e}", clk)?;
        }
        writer.flush()?;

        instance.close()?;

        // Write meta.json
        let meta = json!({
            "schema": "sipi.ami.meta.v1",
            "modelDll": dll_full_path.display().to_string(),
            "dllSha256": format!("{:x}", dll_actual_hash),
            "sampleIntervalS": req.sample_interval_s,
            "bitTimeS": req.bit_time_s,
            "rows": req.rows,
            "aggressors": req.aggressors,
            "getWaveExecuted": wave_out.is_some(),
            "clockCount": clocks_out.len(),
            "parametersOut": init_params_out,
            "getWaveParametersOut": getwave_params_out,
        });
        fs::write(output_dir.join("meta.json"), serde_json::to_vec_pretty(&meta).unwrap())?;

        let mut artifacts = serde_json::Map::new();
        for name in ["request.json", "parameters_out.txt", "clocks.csv", "meta.json"] {
            if output_dir.join(name).is_file() {
                artifacts.insert(name.into(), file_identity(&output_dir.join(name))?);
            }
        }
        if output_dir.join("waveform_out.csv").is_file() {
            artifacts.insert("waveform_out.csv".into(), file_identity(&output_dir.join("waveform_out.csv"))?);
        }

        let receipt = json!({
            "schema": AMI_RECEIPT_SCHEMA,
            "command": "ami run",
            "status": "complete",
            "acceptance": false,
            "artifacts": artifacts
        });
        fs::write(output_dir.join("receipt.json"), serde_json::to_vec_pretty(&receipt).unwrap())?;

        Ok(receipt)
    }

    #[cfg(not(windows))]
    {
        Err(AmiFailure::ModelError("IBIS-AMI DLL execution requires Windows x64 host".into()))
    }
}

fn decode_hex_32(hex_str: &str) -> Option<[u8; 32]> {
    if hex_str.len() != 64 {
        return None;
    }
    let mut out = [0u8; 32];
    for i in 0..32 {
        let byte = u8::from_str_radix(&hex_str[i * 2..i * 2 + 2], 16).ok()?;
        out[i] = byte;
    }
    Some(out)
}
