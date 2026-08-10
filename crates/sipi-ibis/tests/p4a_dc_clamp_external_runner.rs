#![forbid(unsafe_code)]

//! Test-only bridge for the external P4A DC-clamp acceptance comparator.
//!
//! The library remains in-memory only. This ignored test is never a SIPI CLI
//! route or release artifact; it consumes an operator-created temporary
//! request and publishes a temporary result manifest for the comparator.

use std::{
    collections::BTreeMap,
    env,
    error::Error,
    fs,
    path::{Component, Path, PathBuf},
};

use sha2::{Digest, Sha256};
use sipi_ibis::{
    DcClampCornerV1, DcClampProbeV1, InputClampDcModelV1, ParseLimitsV1, SelectedDcClampProfileV1,
    build_semantic_envelope_v1, decode_selected_dc_clamps_v1, evaluate_dc_clamps_v1,
    parse_structural_v1,
};
use sipi_types::Volts;

const REQUEST_ENV: &str = "SIPI_P4A_DC_CLAMP_RUNNER_REQUEST";
const REQUEST_SCHEMA: &str = "sipi.p4a.dc-clamp-product-runner-request.v1";
const RESULT_SCHEMA: &str = "sipi.p4a.dc-clamp-product-runner-result.v1";
const TABLE_FINGERPRINT_DOMAIN: &[u8] = b"sipi.ibis.dc-clamp-table.v1\0";
const EXPECTED_PROBE_COUNT: usize = 6;

#[derive(Debug)]
struct RunnerError(&'static str);

impl std::fmt::Display for RunnerError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(self.0)
    }
}

impl Error for RunnerError {}

struct Request {
    root: PathBuf,
    asset: PathBuf,
    selector: PathBuf,
    probes: PathBuf,
    result: PathBuf,
    asset_sha256: String,
    asset_byte_length: usize,
    selector_sha256: String,
    charter_sha256: String,
}

fn hex_sha256(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    digest.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn is_hex_hash(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

fn parse_request(path: &Path) -> Result<Request, Box<dyn Error>> {
    let canonical_request = path.canonicalize()?;
    let root = canonical_request
        .parent()
        .ok_or(RunnerError("request has no temporary root"))?
        .canonicalize()?;
    let content = fs::read_to_string(&canonical_request)?;
    let mut fields = BTreeMap::new();
    for line in content.lines() {
        let (key, value) = line
            .split_once('=')
            .ok_or(RunnerError("invalid request line"))?;
        if key.is_empty() || value.is_empty() || fields.insert(key, value).is_some() {
            return Err(Box::new(RunnerError("invalid request field")));
        }
    }
    const KEYS: [&str; 9] = [
        "schema",
        "asset",
        "asset_sha256",
        "asset_byte_length",
        "selector",
        "selector_sha256",
        "probes",
        "charter_sha256",
        "result",
    ];
    if fields.len() != KEYS.len() || KEYS.iter().any(|key| !fields.contains_key(key)) {
        return Err(Box::new(RunnerError("request fields are not exact")));
    }
    if fields["schema"] != REQUEST_SCHEMA {
        return Err(Box::new(RunnerError("request schema mismatch")));
    }
    let relative_path = |key: &str, must_exist: bool| -> Result<PathBuf, Box<dyn Error>> {
        let value = Path::new(fields[key]);
        if value.is_absolute()
            || value.components().any(|component| {
                matches!(
                    component,
                    Component::ParentDir | Component::RootDir | Component::Prefix(_)
                )
            })
        {
            return Err(Box::new(RunnerError("request path is not contained")));
        }
        let joined = root.join(value);
        if must_exist {
            let canonical = joined.canonicalize()?;
            if canonical.parent() != Some(root.as_path()) || !canonical.is_file() {
                return Err(Box::new(RunnerError(
                    "request input escapes temporary root",
                )));
            }
            Ok(canonical)
        } else {
            if joined.parent() != Some(root.as_path()) || joined.exists() {
                return Err(Box::new(RunnerError("result path is invalid")));
            }
            Ok(joined)
        }
    };
    let asset_sha256 = fields["asset_sha256"].to_owned();
    let selector_sha256 = fields["selector_sha256"].to_owned();
    let charter_sha256 = fields["charter_sha256"].to_owned();
    if !is_hex_hash(&asset_sha256)
        || !is_hex_hash(&selector_sha256)
        || !is_hex_hash(&charter_sha256)
    {
        return Err(Box::new(RunnerError("request hash is invalid")));
    }
    let asset = relative_path("asset", true)?;
    let selector = relative_path("selector", true)?;
    let probes = relative_path("probes", true)?;
    let result = relative_path("result", false)?;
    Ok(Request {
        root,
        asset,
        selector,
        probes,
        result,
        asset_sha256,
        asset_byte_length: fields["asset_byte_length"]
            .parse()
            .map_err(|_| RunnerError("asset byte length is invalid"))?,
        selector_sha256,
        charter_sha256,
    })
}

fn read_selector(request: &Request) -> Result<String, Box<dyn Error>> {
    let bytes = fs::read(&request.selector)?;
    if hex_sha256(&bytes) != request.selector_sha256 {
        return Err(Box::new(RunnerError("selector hash mismatch")));
    }
    let selector = std::str::from_utf8(&bytes).map_err(|_| RunnerError("selector is not UTF-8"))?;
    if selector.is_empty()
        || selector
            .bytes()
            .any(|byte| byte.is_ascii_whitespace() || byte.is_ascii_control())
    {
        return Err(Box::new(RunnerError("selector spelling is invalid")));
    }
    Ok(selector.to_owned())
}

fn read_probes(request: &Request) -> Result<Vec<f64>, Box<dyn Error>> {
    let bytes = fs::read(&request.probes)?;
    if bytes.len() != EXPECTED_PROBE_COUNT * std::mem::size_of::<f64>() {
        return Err(Box::new(RunnerError("probe sidecar length is invalid")));
    }
    bytes
        .chunks_exact(8)
        .map(|chunk| {
            let value = f64::from_le_bytes(
                chunk
                    .try_into()
                    .map_err(|_| RunnerError("probe decode failed"))?,
            );
            value
                .is_finite()
                .then_some(value)
                .ok_or(RunnerError("probe is non-finite"))
        })
        .collect::<Result<Vec<_>, _>>()
        .map_err(Into::into)
}

fn table_fingerprint(model: &InputClampDcModelV1) -> String {
    let mut hasher = Sha256::new();
    hasher.update(TABLE_FINGERPRINT_DOMAIN);
    for (label, table) in [
        (b"gnd".as_slice(), model.gnd_clamp()),
        (b"power".as_slice(), model.power_clamp()),
    ] {
        hasher.update((label.len() as u64).to_be_bytes());
        hasher.update(label);
        hasher.update((table.knots().len() as u64).to_be_bytes());
        for knot in table.knots() {
            hasher.update(knot.voltage().get().to_bits().to_be_bytes());
            hasher.update(knot.current().get().to_bits().to_be_bytes());
        }
    }
    hasher
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn render_result(
    request: &Request,
    model: &InputClampDcModelV1,
    probes: &[f64],
) -> Result<String, Box<dyn Error>> {
    let mut items = Vec::with_capacity(probes.len());
    for voltage in probes {
        let drive = Volts::try_new(*voltage).map_err(|_| RunnerError("probe is non-finite"))?;
        let response = evaluate_dc_clamps_v1(model, DcClampProbeV1::new(drive, drive))
            .map_err(|_| RunnerError("product clamp evaluation failed"))?;
        items.push(format!(
            "{{\"voltage_v\":{voltage:.17e},\"gnd_current_a\":{:.17e},\"power_current_a\":{:.17e},\"total_current_a\":{:.17e},\"capacitive_current_a\":0.0}}",
            response.gnd_current().get(),
            response.power_current().get(),
            response.total_shunt_current().get(),
        ));
    }
    Ok(format!(
        "{{\"schema\":\"{RESULT_SCHEMA}\",\"status\":\"ok\",\"asset_sha256\":\"{}\",\"asset_byte_length\":{},\"selector_sha256\":\"{}\",\"charter_sha256\":\"{}\",\"table_fingerprint\":\"{}\",\"probes\":[{}]}}\n",
        request.asset_sha256,
        request.asset_byte_length,
        request.selector_sha256,
        request.charter_sha256,
        table_fingerprint(model),
        items.join(","),
    ))
}

fn run(request_path: &Path) -> Result<(), Box<dyn Error>> {
    let request = parse_request(request_path)?;
    let asset = fs::read(&request.asset)?;
    if asset.len() != request.asset_byte_length || hex_sha256(&asset) != request.asset_sha256 {
        return Err(Box::new(RunnerError("asset identity mismatch")));
    }
    let selector = read_selector(&request)?;
    let probes = read_probes(&request)?;
    let limits = ParseLimitsV1::try_new(1_048_576, 16_384, 262_144, 262_144)
        .map_err(|_| RunnerError("runner limits are invalid"))?;
    let structural = parse_structural_v1(&asset, limits)?;
    let semantic = build_semantic_envelope_v1(&structural)?;
    let profile = SelectedDcClampProfileV1::try_new(
        semantic.version().spelling(),
        &selector,
        DcClampCornerV1::Typical,
    )?;
    let decoded = decode_selected_dc_clamps_v1(&semantic, &profile)?;
    let result = render_result(&request, decoded.model(), &probes)?;
    let _ = &request.root;
    fs::write(&request.result, result)?;
    Ok(())
}

#[test]
#[ignore = "external-only P4A comparator runner"]
fn p4a_dc_clamp_external_runner() {
    let request = env::var_os(REQUEST_ENV).expect("runner request environment is required");
    run(Path::new(&request)).expect("external runner failed");
}
