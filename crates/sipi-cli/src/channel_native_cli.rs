//! Local PB-02 integration. Numerical work and compatibility artifacts belong
//! to the existing direct crate; this boundary adds argv, CSV and presentation.

use std::{
    fs::{self, File, OpenOptions},
    io::{self, BufWriter, Read, Write},
    path::Path,
};

use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use sipi_pybert_direct::{DirectRunError, DirectRunReport, SimulationInputV1, run_sim_native_json};

pub(crate) const RECEIPT_SCHEMA: &str = "sipi.channel.native-receipt.v1";
const TEMPLATE: &[u8] = include_bytes!("../../../examples/channel-native/metallic-line.json");
const MAX_REQUEST_BYTES: u64 = 16 * 1024 * 1024;
const MAX_CSV_BYTES: usize = 256 * 1024 * 1024;
const WAVEFORMS: &[&str] = &[
    "tx_waveform_v",
    "channel_output_v",
    "rx_input_v",
    "rx_output_v",
];

#[derive(Debug)]
pub(crate) enum Failure {
    Usage,
    InvalidInput,
    Io,
    Native(DirectRunError),
}

impl Failure {
    pub(crate) fn code(&self) -> &'static str {
        match self {
            Self::Usage => "usage",
            Self::InvalidInput => "invalid_input",
            Self::Io => "operational_failure",
            Self::Native(error) => match error.code() {
                "invalid_input" | "invalid_native_input" => "invalid_input",
                "unsupported_native_input" => "unsupported",
                "resource_limit_exceeded" => "resource_limit_exceeded",
                _ => "operational_failure",
            },
        }
    }

    pub(crate) fn exit_code(&self) -> i32 {
        match self.code() {
            "usage" => 64,
            "invalid_input" => 2,
            "unsupported" => 4,
            "resource_limit_exceeded" => 5,
            _ => 5,
        }
    }
}

impl From<io::Error> for Failure {
    fn from(_: io::Error) -> Self {
        Self::Io
    }
}

impl From<DirectRunError> for Failure {
    fn from(error: DirectRunError) -> Self {
        Self::Native(error)
    }
}

pub(crate) fn execute(action: &str, arguments: &[String]) -> Result<String, Failure> {
    let result = match (action, arguments) {
        ("help", []) => json!({
            "schema": "sipi.channel.native-help.v1",
            "commands": [
                "sipi channel init REQUEST.json",
                "sipi channel simulate REQUEST.json --output-dir NEW_DIRECTORY"
            ],
            "input_schema": "pybert.simulation.v1",
            "input_units": "SI; impulseResponseVoltsPerSecond is converted by the owning core",
            "backend": "in_process_sipi_pybert_direct",
            "workflow": "PB-02 sim-native",
            "maximum_request_bytes": MAX_REQUEST_BYTES,
            "maximum_csv_bytes_per_file": MAX_CSV_BYTES,
            "output_policy": "new_directory_only; receipt.json is written last; failures retain partial output",
            "artifacts": ["request.json", "meta.json", "arrays.npz", "waveforms.csv", "channel-impulse.csv", "report.html", "receipt.json"],
            "scope": "local_candidate; not external ADS parity or release acceptance",
            "kernel_command": "sipi channel run --stdin remains the separate matched-S21 kernel contract"
        }),
        ("init", [request]) if !request.starts_with('-') => {
            let mut file = OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(request)?;
            file.write_all(TEMPLATE)?;
            file.sync_all()?;
            json!({
                "schema": "sipi.channel.native-init.v1",
                "input_schema": "pybert.simulation.v1",
                "template": "metallic-line-prbs9",
                "sha256": format!("{:x}", Sha256::digest(TEMPLATE)),
                "acceptance": false
            })
        }
        ("simulate", [request, option, output])
            if !request.starts_with('-')
                && option == "--output-dir"
                && !output.starts_with('-') =>
        {
            simulate(Path::new(request), Path::new(output))?
        }
        _ => return Err(Failure::Usage),
    };
    serde_json::to_string(&result).map_err(|_| Failure::Io)
}

fn simulate(request: &Path, output: &Path) -> Result<Value, Failure> {
    let file = File::open(request)?;
    if !file.metadata()?.is_file() {
        return Err(Failure::InvalidInput);
    }
    let mut bytes = Vec::new();
    file.take(MAX_REQUEST_BYTES + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > MAX_REQUEST_BYTES {
        return Err(Failure::InvalidInput);
    }
    // Deserialize the original bytes too, before the owner's Value-based
    // preflight, so duplicate typed fields cannot silently pick the last value.
    let input: SimulationInputV1 =
        serde_json::from_slice(&bytes).map_err(|_| Failure::InvalidInput)?;
    input.validate().map_err(|_| Failure::InvalidInput)?;
    sipi_pybert_direct::strict_simulation_input_json(&bytes)?;

    if let Some(parent) = output.parent().filter(|path| !path.as_os_str().is_empty()) {
        fs::create_dir_all(parent)?;
    }
    // Exclusive creation protects prior runs, including empty directories and
    // links. The direct writer may only reuse this newly claimed directory.
    fs::create_dir(output)?;
    write_new(&output.join("request.json"), &bytes)?;
    let report = run_sim_native_json(&bytes, request, output)?;
    let time = array(&report, "time_s")?;
    if time.is_empty() {
        return Err(Failure::Io);
    }
    let waveforms = WAVEFORMS
        .iter()
        .map(|name| array(&report, name))
        .collect::<Result<Vec<_>, _>>()?;
    if waveforms.iter().any(|values| values.len() != time.len()) {
        return Err(Failure::Io);
    }
    write_csv(&output.join("waveforms.csv"), time, WAVEFORMS, &waveforms)?;
    let impulse = array(&report, "channel_impulse_v_per_v")?;
    let impulse_time = (0..impulse.len())
        .map(|index| index as f64 * report.input.timebase.sample_interval.0)
        .collect::<Vec<_>>();
    write_csv(
        &output.join("channel-impulse.csv"),
        &impulse_time,
        &["channel_impulse_v_per_v"],
        &[impulse],
    )?;
    let preview_samples = time
        .len()
        .min(32 * report.input.timebase.samples_per_ui as usize)
        .min(4096);
    let html = render_report(
        &report,
        time,
        &waveforms,
        &impulse_time,
        impulse,
        preview_samples,
    );
    write_new(&output.join("report.html"), html.as_bytes())?;

    let mut artifacts = serde_json::Map::new();
    for name in [
        "request.json",
        "meta.json",
        "arrays.npz",
        "waveforms.csv",
        "channel-impulse.csv",
        "report.html",
    ] {
        artifacts.insert(name.into(), file_identity(&output.join(name))?);
    }
    let receipt = json!({
        "schema": RECEIPT_SCHEMA,
        "status": "complete",
        "workflow": "PB-02 sim-native",
        "backend": "in_process_sipi_pybert_direct",
        "upstream_commit": "5bf6d7ea0ace261891aaeb611ffc1c267e160afe",
        "executable": file_identity(&std::env::current_exe()?)?,
        "waveform_samples": time.len(),
        "channel_impulse_samples": impulse.len(),
        "native_array_count": report.output.arrays.len(),
        "preview_samples": preview_samples,
        "csv_policy": "all_samples_original_grid_roundtrip_f64_no_alignment_or_scaling",
        "compatibility_metadata": "meta.json preserves the PB-02 upstream schema and engine labels; executable identifies this SIPI run",
        "artifacts": artifacts,
        "acceptance": false,
        "scope": "local_candidate_not_full_upstream_parity_or_ads_acceptance_or_release"
    });
    let receipt_bytes = serde_json::to_vec_pretty(&receipt).map_err(|_| Failure::Io)?;
    write_new(&output.join("receipt.json"), &receipt_bytes)?;
    Ok(receipt)
}

fn array<'a>(report: &'a DirectRunReport, name: &str) -> Result<&'a [f64], Failure> {
    report
        .output
        .arrays
        .get(name)
        .map(Vec::as_slice)
        .ok_or(Failure::Io)
}

fn write_new(path: &Path, bytes: &[u8]) -> Result<(), Failure> {
    let mut file = OpenOptions::new().write(true).create_new(true).open(path)?;
    file.write_all(bytes)?;
    file.sync_all()?;
    Ok(())
}

fn write_csv(path: &Path, time: &[f64], names: &[&str], columns: &[&[f64]]) -> Result<(), Failure> {
    let mut writer = BufWriter::new(OpenOptions::new().write(true).create_new(true).open(path)?);
    let header = format!("time_s,{}\n", names.join(","));
    writer.write_all(header.as_bytes())?;
    let mut byte_count = header.len();
    for (index, t) in time.iter().enumerate() {
        let mut row = t.to_string();
        for values in columns {
            row.push(',');
            row.push_str(&values[index].to_string());
        }
        row.push('\n');
        byte_count = byte_count.checked_add(row.len()).ok_or(Failure::Io)?;
        if byte_count > MAX_CSV_BYTES {
            return Err(Failure::Io);
        }
        writer.write_all(row.as_bytes())?;
    }
    writer.flush()?;
    writer.get_ref().sync_all()?;
    Ok(())
}

fn file_identity(path: &Path) -> Result<Value, Failure> {
    let mut file = File::open(path)?;
    let mut hash = Sha256::new();
    let mut length = 0_u64;
    let mut buffer = [0_u8; 65536];
    loop {
        let count = file.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        length += count as u64;
        hash.update(&buffer[..count]);
    }
    Ok(json!({"byte_length": length, "sha256": format!("{:x}", hash.finalize())}))
}

fn escape(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#39;")
}

fn render_report(
    report: &DirectRunReport,
    time: &[f64],
    waves: &[&[f64]],
    impulse_time: &[f64],
    impulse: &[f64],
    preview: usize,
) -> String {
    let mut html = String::from(
        r#"<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>SIPI Channel</title><style>
*{box-sizing:border-box;letter-spacing:0}body{margin:0;color:#202723;background:#fff;font:14px 'Segoe UI',sans-serif}
header,main{max-width:1160px;margin:auto;padding:24px}header{border-bottom:2px solid #206e55}
h1{font-size:26px;margin:0 0 8px}h2{font-size:17px;margin:0 0 12px}p{line-height:1.6;margin:8px 0}
a{color:#1d628b;text-underline-offset:3px}nav{display:flex;flex-wrap:wrap;gap:12px 24px;margin-top:16px}
section{padding:24px 0;border-bottom:1px solid #d8dfdc}.muted{color:#55625d}.status{color:#a42d53;font-weight:600}
.summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:20px;padding:0 0 24px}
.summary dt{color:#55625d;margin-bottom:6px}.summary dd{margin:0;font:20px Consolas,monospace;overflow-wrap:anywhere}
.plot{overflow-x:auto}.plot svg{display:block;width:100%;min-width:700px;height:auto}
.legend{display:flex;gap:12px 24px;flex-wrap:wrap;margin:12px 0;font-family:Consolas,monospace}
.legend span{overflow-wrap:anywhere}.legend i{display:inline-block;width:18px;height:3px;margin-right:8px;vertical-align:middle}
details{margin-top:24px}summary{cursor:pointer;font-weight:600}pre{background:#f3f6f5;padding:16px;max-height:420px;overflow:auto;line-height:1.5}
@media(max-width:600px){header,main{padding:18px}.summary{grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}h1{font-size:23px}}
</style></head><body><header><h1>SIPI Channel</h1><p class="status">Local Rust candidate / acceptance: false</p>"#,
    );
    html.push_str(&format!("<p>{}</p>", escape(&report.output.run_id)));
    html.push_str(r#"<nav aria-label="Artifacts"><a href="waveforms.csv">Waveforms CSV</a><a href="channel-impulse.csv">Impulse CSV</a><a href="arrays.npz">Native arrays</a><a href="meta.json">Native metadata</a><a href="request.json">Request</a><a href="receipt.json">Run receipt</a></nav></header><main>"#);
    html.push_str(&format!("<dl class=\"summary\"><div><dt>Samples</dt><dd>{}</dd></div><div><dt>Sample interval</dt><dd>{:.6} ps</dd></div><div><dt>Data rate</dt><dd>{:.3} GHz</dd></div><div><dt>Native arrays</dt><dd>{}</dd></div></dl>", time.len(), report.input.timebase.sample_interval.0 * 1e12, report.input.timebase.data_rate.0 * 1e-9, report.output.arrays.len()));
    html.push_str(&format!("<section><h2>Stage waveforms</h2><p class=\"muted\">Samples 0..{} of {}. CSV contains the full original grid. Coincident stages share a trace.</p>", preview.saturating_sub(1), time.len()));
    let preview_waves = waves
        .iter()
        .map(|values| &values[..preview])
        .collect::<Vec<_>>();
    html.push_str(&plot(&time[..preview], WAVEFORMS, &preview_waves, "V"));
    html.push_str("</section><section><h2>Channel discrete impulse</h2>");
    let impulse_preview = impulse.len().min(4096);
    html.push_str(&format!("<p class=\"muted\">Samples 0..{} of {}. Discrete convolution coefficients, not volts per second.</p>", impulse_preview.saturating_sub(1), impulse.len()));
    html.push_str(&plot(
        &impulse_time[..impulse_preview],
        &["channel_impulse_v_per_v"],
        &[&impulse[..impulse_preview]],
        "V/V",
    ));
    html.push_str("</section><details><summary>Effective request</summary><pre>");
    html.push_str(&escape(
        &serde_json::to_string_pretty(&report.metadata["effective_input"]).expect("finite request"),
    ));
    html.push_str(
        "</pre></details><details><summary>Native metrics and diagnostics</summary><pre>",
    );
    html.push_str(&escape(
        &serde_json::to_string_pretty(
            &json!({"metrics": report.output.metrics, "diagnostics": report.diagnostics}),
        )
        .expect("finite output"),
    ));
    html.push_str("</pre></details></main></body></html>");
    html
}

fn plot(time: &[f64], names: &[&str], columns: &[&[f64]], unit: &str) -> String {
    if time.is_empty() {
        return "<p>No samples</p>".into();
    }
    let colors = ["#20734f", "#b4395b", "#166a9b", "#a16910"];
    let low = columns
        .iter()
        .flat_map(|values| values.iter())
        .copied()
        .fold(0.0_f64, f64::min);
    let high = columns
        .iter()
        .flat_map(|values| values.iter())
        .copied()
        .fold(0.0_f64, f64::max);
    let span = (high - low).max(1e-12);
    let xspan = (time[time.len() - 1] - time[0]).max(f64::MIN_POSITIVE);
    let mut svg = format!(
        "<div class=\"plot\"><svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 1000 280\" role=\"img\" aria-label=\"Signal in {unit} versus time in ps\"><title>Signal in {unit} versus time in ps</title>"
    );
    for tick in 0..=4 {
        let fraction = tick as f64 / 4.0;
        let y = 234.0 - fraction * 210.0;
        let x = 100.0 + fraction * 875.0;
        svg.push_str(&format!("<path d=\"M100 {y}H975\" stroke=\"#e1e8e4\"/><text x=\"88\" y=\"{}\" text-anchor=\"end\" fill=\"#55625d\" font-size=\"12\">{:.3e}</text><text x=\"{x}\" y=\"255\" text-anchor=\"middle\" fill=\"#55625d\" font-size=\"12\">{:.2}</text>", y+4.0, low+fraction*span, (time[0]+fraction*xspan)*1e12));
    }
    svg.push_str(&format!("<text x=\"12\" y=\"16\" font-size=\"12\">{unit}</text><text x=\"530\" y=\"272\" text-anchor=\"middle\" font-size=\"12\">Time (ps)</text>"));
    for (index, values) in columns.iter().enumerate() {
        svg.push_str(&format!("<polyline data-series=\"{}\" fill=\"none\" stroke=\"{}\" stroke-width=\"1.6\" stroke-dasharray=\"{}\" points=\"", escape(names[index]), colors[index % colors.len()], if index < 2 { "none" } else { "5 3" }));
        for (t, value) in time.iter().zip(values.iter()) {
            svg.push_str(&format!(
                "{:.3},{:.3} ",
                100.0 + (t - time[0]) / xspan * 875.0,
                234.0 - (value - low) / span * 210.0
            ));
        }
        svg.push_str("\"/>");
    }
    svg.push_str("</svg></div><div class=\"legend\">");
    for (index, name) in names.iter().enumerate() {
        svg.push_str(&format!(
            "<span><i style=\"background:{}\"></i>{}</span>",
            colors[index % colors.len()],
            escape(name)
        ));
    }
    svg.push_str("</div>");
    svg
}
