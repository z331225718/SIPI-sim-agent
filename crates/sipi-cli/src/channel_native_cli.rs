//! Local PB-02 integration. Numerical work and compatibility artifacts belong
//! to the existing direct crate; this boundary adds argv, CSV and presentation.

use std::{
    fs::{self, File, OpenOptions},
    io::{self, BufWriter, Read, Write},
    path::Path,
};

use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use sipi_pybert_direct::{
    DirectRunError, DirectRunReport, PHYSICAL_CHANNEL_POLICY_V1, SimulationInputV1,
    TOUCHSTONE_CHANNEL_POLICY_V1, run_channel_physical_json, run_channel_touchstone_network_json,
    run_sim_native_json,
};

pub(crate) const RECEIPT_SCHEMA: &str = "sipi.channel.native-receipt.v1";
const TEMPLATE: &[u8] = include_bytes!("../../../examples/channel-native/metallic-line.json");
const TEMPLATE_TOUCHSTONE: &[u8] =
    include_bytes!("../../../examples/channel-native/touchstone-network.json");
const MAX_REQUEST_BYTES: u64 = 16 * 1024 * 1024;
const MAX_CSV_BYTES: usize = 256 * 1024 * 1024;
const MAX_REPORT_BYTES: usize = 256 * 1024 * 1024;
const REPORT_SCRIPT: &str = include_str!("channel_report.js");
const WAVEFORMS: &[&str] = &[
    "tx_waveform_v",
    "channel_output_v",
    "rx_input_v",
    "rx_output_v",
];
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum ChannelPolicyMode {
    Compat,
    PhysicalVoltage,
    TouchstoneNetwork,
}


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
                "sipi channel init REQUEST.json --template TEMPLATE",
                "sipi channel simulate REQUEST.json --output-dir NEW_DIRECTORY",
                "sipi channel simulate REQUEST.json --output-dir NEW_DIRECTORY --channel-policy physical-voltage-v1",
                "sipi channel simulate REQUEST.json --output-dir NEW_DIRECTORY --channel-policy touchstone-network-v1",
                "sipi channel sweep REQUEST.json --output-dir NEW_DIRECTORY",
                "sipi channel sweep REQUEST.json --output-dir NEW_DIRECTORY --channel-policy touchstone-network-v1"
            ],
            "input_schema": "pybert.simulation.v1",
            "input_units": "SI; impulseResponseVoltsPerSecond is converted by the owning core",
            "backend": "in_process_sipi_pybert_direct",
            "workflow": "PB-02 sim-native",
            "channel_policies": {
                "default": "pb-02-compat",
                "physical-voltage-v1": "explicit metallic-line load voltage; retained time origin; finite-band kernel, not ADS Transient acceptance",
                "touchstone-network-v1": "typed Touchstone/cascade S-parameter network workflow with port mapping, diagnostics, loaded transfer function, and single final FD-to-TD"
            },
            "maximum_request_bytes": MAX_REQUEST_BYTES,
            "maximum_csv_bytes_per_file": MAX_CSV_BYTES,
            "maximum_report_bytes": MAX_REPORT_BYTES,
            "output_policy": "new_directory_only; receipt.json is written last; failures retain partial output",
            "artifacts": ["request.json", "meta.json", "arrays.npz", "waveforms.csv", "channel-impulse.csv", "report.html", "channel-report.js", "receipt.json"],
            "scope": "local_candidate; not external ADS parity or release acceptance",
            "kernel_command": "sipi channel run --stdin remains the separate matched-S21 kernel contract"
        }),
        ("init", [request]) if !request.starts_with('-') => {
            init_request(request, "metallic-line-prbs9", TEMPLATE)?
        }
        ("init", [request, option, template])
            if !request.starts_with('-') && option == "--template" =>
        {
            match template.as_str() {
                "touchstone-network" | "network-cascade" => {
                    init_request(request, "touchstone-network-prbs9", TEMPLATE_TOUCHSTONE)?
                }
                "metallic-line" => init_request(request, "metallic-line-prbs9", TEMPLATE)?,
                _ => return Err(Failure::InvalidInput),
            }
        }
        ("simulate", [request, option, output])
            if !request.starts_with('-')
                && option == "--output-dir"
                && !output.starts_with('-') =>
        {
            simulate(Path::new(request), Path::new(output), ChannelPolicyMode::Compat)?
        }
        ("simulate", [request, option, output, policy_option, policy])
            if !request.starts_with('-')
                && option == "--output-dir"
                && !output.starts_with('-')
                && policy_option == "--channel-policy" =>
        {
            let mode = match policy.as_str() {
                PHYSICAL_CHANNEL_POLICY_V1 => ChannelPolicyMode::PhysicalVoltage,
                TOUCHSTONE_CHANNEL_POLICY_V1 => ChannelPolicyMode::TouchstoneNetwork,
                _ => return Err(Failure::Usage),
            };
            simulate(Path::new(request), Path::new(output), mode)?
        }
        ("sweep", [request, option, output])
            if !request.starts_with('-')
                && option == "--output-dir"
                && !output.starts_with('-') =>
        {
            sweep(Path::new(request), Path::new(output), ChannelPolicyMode::Compat)?
        }
        ("sweep", [request, option, output, policy_option, policy])
            if !request.starts_with('-')
                && option == "--output-dir"
                && !output.starts_with('-')
                && policy_option == "--channel-policy" =>
        {
            let mode = match policy.as_str() {
                PHYSICAL_CHANNEL_POLICY_V1 => ChannelPolicyMode::PhysicalVoltage,
                TOUCHSTONE_CHANNEL_POLICY_V1 => ChannelPolicyMode::TouchstoneNetwork,
                _ => return Err(Failure::Usage),
            };
            sweep(Path::new(request), Path::new(output), mode)?
        }
        _ => return Err(Failure::Usage),
    };
    serde_json::to_string(&result).map_err(|_| Failure::Io)
}

fn init_request(request: &str, template_name: &str, template_bytes: &[u8]) -> Result<Value, Failure> {
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(request)?;
    file.write_all(template_bytes)?;
    file.sync_all()?;
    Ok(json!({
        "schema": "sipi.channel.native-init.v1",
        "input_schema": "pybert.simulation.v1",
        "template": template_name,
        "sha256": format!("{:x}", Sha256::digest(template_bytes)),
        "acceptance": false
    }))
}

fn simulate(request: &Path, output: &Path, mode: ChannelPolicyMode) -> Result<Value, Failure> {
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
    let report = match mode {
        ChannelPolicyMode::Compat => run_sim_native_json(&bytes, request, output)?,
        ChannelPolicyMode::PhysicalVoltage => run_channel_physical_json(&bytes, request, output)?,
        ChannelPolicyMode::TouchstoneNetwork => {
            run_channel_touchstone_network_json(&bytes, request, output)?
        }
    };
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
    write_csv(
        &output.join("waveforms.csv"),
        "time_s",
        time,
        WAVEFORMS,
        &waveforms,
    )?;
    let impulse = array(&report, "channel_impulse_v_per_v")?;
    let impulse_time = (0..impulse.len())
        .map(|index| index as f64 * report.input.timebase.sample_interval.0)
        .collect::<Vec<_>>();
    write_csv(
        &output.join("channel-impulse.csv"),
        "time_s",
        &impulse_time,
        &["channel_impulse_v_per_v"],
        &[impulse],
    )?;
    if mode == ChannelPolicyMode::PhysicalVoltage {
        let frequency = array(&report, "physical_channel_frequency_hz")?;
        let names = [
            "physical_channel_voltage_re",
            "physical_channel_voltage_im",
            "physical_channel_windowed_re",
            "physical_channel_windowed_im",
        ];
        let columns = names
            .iter()
            .map(|name| array(&report, name))
            .collect::<Result<Vec<_>, _>>()?;
        if columns.iter().any(|values| values.len() != frequency.len()) {
            return Err(Failure::Io);
        }
        write_csv(
            &output.join("frequency-response.csv"),
            "frequency_hz",
            frequency,
            &names,
            &columns,
        )?;
    } else if mode == ChannelPolicyMode::TouchstoneNetwork {
        let frequency = array(&report, "touchstone_frequency_hz")?;
        let names = [
            "touchstone_s11_re",
            "touchstone_s11_im",
            "touchstone_s21_re",
            "touchstone_s21_im",
            "touchstone_s12_re",
            "touchstone_s12_im",
            "touchstone_s22_re",
            "touchstone_s22_im",
            "touchstone_loaded_h_re",
            "touchstone_loaded_h_im",
            "touchstone_windowed_h_re",
            "touchstone_windowed_h_im",
        ];
        let columns = names
            .iter()
            .map(|name| array(&report, name))
            .collect::<Result<Vec<_>, _>>()?;
        if columns.iter().any(|values| values.len() != frequency.len()) {
            return Err(Failure::Io);
        }
        write_csv(
            &output.join("frequency-response.csv"),
            "frequency_hz",
            frequency,
            &names,
            &columns,
        )?;

        // Intermediate cascade stage node transmission if multi-stage
        let mut node_names = Vec::new();
        for key in report.output.arrays.keys() {
            if key.starts_with("touchstone_stage_") {
                node_names.push(key.as_str());
            }
        }
        node_names.sort();
        if !node_names.is_empty() {
            let node_columns = node_names
                .iter()
                .map(|name| array(&report, name))
                .collect::<Result<Vec<_>, _>>()?;
            write_csv(
                &output.join("cascade-nodes.csv"),
                "frequency_hz",
                frequency,
                &node_names,
                &node_columns,
            )?;
        }
    }
    // Export eye and jitter metrics if present
    let has_eye_or_jitter = report
        .output
        .metrics
        .keys()
        .any(|k| k.starts_with("eye_") || k.starts_with("jitter_") || k.starts_with("bathtub_") || k.starts_with("pam4_") || k.starts_with("crosstalk_"));
    if has_eye_or_jitter {
        let path = output.join("eye-metrics.csv");
        let mut writer = BufWriter::new(OpenOptions::new().write(true).create_new(true).open(&path)?);
        writer.write_all(b"metric,value,unit\n")?;
        let mut keys = report
            .output
            .metrics
            .keys()
            .filter(|k| k.starts_with("eye_") || k.starts_with("jitter_") || k.starts_with("bathtub_") || k.starts_with("pam4_") || k.starts_with("crosstalk_"))
            .cloned()
            .collect::<Vec<_>>();
        keys.sort();
        for k in keys {
            let val = report.output.metrics.get(&k).copied().unwrap_or(0.0);
            let unit = if k.ends_with("_v") {
                "V"
            } else if k.ends_with("_ps") {
                "ps"
            } else if k.ends_with("_s") {
                "s"
            } else if k.ends_with("_db") {
                "dB"
            } else if k.ends_with("_count") {
                "count"
            } else {
                ""
            };
            writeln!(writer, "{k},{val},{unit}").map_err(|_| Failure::Io)?;
        }
        writer.flush()?;
        writer.get_ref().sync_all()?;
    }

    // Export bathtub curve if present
    let bathtub_array = report
        .output
        .arrays
        .get("bathtub_chnl_ber")
        .or_else(|| report.output.arrays.get("bathtub_ber"))
        .or_else(|| report.output.arrays.get("bathtub_dfe_ber"));
    let bin_centers = report
        .output
        .arrays
        .get("jitter_chnl_bin_centers_s")
        .or_else(|| report.output.arrays.get("jitter_bin_centers_s"))
        .or_else(|| report.output.arrays.get("jitter_dfe_bin_centers_s"));

    let bathtub_info = if let (Some(ber), Some(centers)) = (bathtub_array, bin_centers) {
        if !ber.is_empty() && ber.len() == centers.len() {
            let path = output.join("bathtub.csv");
            let mut writer = BufWriter::new(OpenOptions::new().write(true).create_new(true).open(&path)?);
            writer.write_all(b"time_s,time_ui,bathtub_ber\n")?;
            let data_rate = report.input.timebase.data_rate.0;
            for (&t, &b) in centers.iter().zip(ber) {
                let ui = t * data_rate;
                writeln!(writer, "{t},{ui},{b}").map_err(|_| Failure::Io)?;
            }
            writer.flush()?;
            writer.get_ref().sync_all()?;
            Some((centers.as_slice(), ber.as_slice()))
        } else {
            None
        }
    } else {
        None
    };

    // Export statistical eye contours if present
    let has_eye_contours = report.output.arrays.contains_key("eye_contour_0_x_ui");
    if has_eye_contours {
        let path = output.join("eye-contours.csv");
        let mut writer = BufWriter::new(OpenOptions::new().write(true).create_new(true).open(&path)?);
        writer.write_all(b"contour_index,x_ui,y_v\n")?;
        let count = report.output.metrics.get("eye_contour_count").copied().unwrap_or(0.0) as usize;
        for c_idx in 0..count {
            if let (Some(x_vals), Some(y_vals)) = (
                report.output.arrays.get(&format!("eye_contour_{c_idx}_x_ui")),
                report.output.arrays.get(&format!("eye_contour_{c_idx}_y_v")),
            ) {
                for (&x, &y) in x_vals.iter().zip(y_vals) {
                    writeln!(writer, "{c_idx},{x},{y}").map_err(|_| Failure::Io)?;
                }
            }
        }
        writer.flush()?;
        writer.get_ref().sync_all()?;
    }
    // Export DFE adaptation and events if DFE was enabled
    if let (Some(weights_flat), Some(clock_times)) = (
        report.output.arrays.get("dfe_tap_weights_v"),
        report.output.arrays.get("dfe_clock_times_s"),
    ) {
        let n_taps = report.input.rx.dfe_taps as usize;
        if n_taps > 0 && !clock_times.is_empty() {
            let path = output.join("dfe-adaptation.csv");
            let mut writer = BufWriter::new(OpenOptions::new().write(true).create_new(true).open(&path)?);
            let mut header = String::from("clock_index,time_s");
            for t in 0..n_taps {
                header.push_str(&format!(",tap_{t}_weight"));
            }
            header.push('\n');
            writer.write_all(header.as_bytes())?;
            for (clock_idx, &t) in clock_times.iter().enumerate() {
                let mut row = format!("{clock_idx},{t}");
                let offset = clock_idx * n_taps;
                for t_idx in 0..n_taps {
                    let w = weights_flat.get(offset + t_idx).copied().unwrap_or(0.0);
                    row.push_str(&format!(",{w}"));
                }
                row.push('\n');
                writer.write_all(row.as_bytes())?;
            }
            writer.flush()?;
            writer.get_ref().sync_all()?;
        }
    }

    if let (Some(slicer_inputs), Some(clock_times)) = (
        report.output.arrays.get("dfe_slicer_inputs_v"),
        report.output.arrays.get("dfe_clock_times_s"),
    ) {
        if !slicer_inputs.is_empty() {
            let path = output.join("dfe-events.csv");
            let mut writer = BufWriter::new(OpenOptions::new().write(true).create_new(true).open(&path)?);
            writer.write_all(b"clock_index,time_s,slicer_input_v,decision,error_v,update_enabled,bank_updated\n")?;
            let decisions = report.output.arrays.get("dfe_decisions");
            let errors = report.output.arrays.get("dfe_errors_v");
            let updates = report.output.arrays.get("dfe_update_enabled");
            let banks = report.output.arrays.get("dfe_bank_updated");

            for (idx, &v_in) in slicer_inputs.iter().enumerate() {
                let t = clock_times.get(idx).copied().unwrap_or(0.0);
                let dec = decisions.and_then(|d| d.get(idx).copied()).unwrap_or(0.0);
                let err = errors.and_then(|e| e.get(idx).copied()).unwrap_or(0.0);
                let upd = updates.and_then(|u| u.get(idx).copied()).unwrap_or(0.0);
                let bnk = banks.and_then(|b| b.get(idx).copied()).unwrap_or(0.0);
                writeln!(writer, "{idx},{t},{v_in},{dec},{err},{upd},{bnk}").map_err(|_| Failure::Io)?;
            }
            writer.flush()?;
            writer.get_ref().sync_all()?;
        }
    }


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
        bathtub_info,
        preview_samples,
    );
    write_report(
        &output.join("report.html"),
        &html,
        time,
        &waveforms,
        &impulse_time,
        impulse,
        bathtub_info,
    )?;
    write_new(&output.join("channel-report.js"), REPORT_SCRIPT.as_bytes())?;

    let mut artifacts = serde_json::Map::new();
    let mut artifact_names = vec![
        "request.json",
        "meta.json",
        "arrays.npz",
        "waveforms.csv",
        "channel-impulse.csv",
        "report.html",
        "channel-report.js",
    ];
    if mode == ChannelPolicyMode::PhysicalVoltage || mode == ChannelPolicyMode::TouchstoneNetwork {
        artifact_names.push("frequency-response.csv");
        if output.join("cascade-nodes.csv").is_file() {
            artifact_names.push("cascade-nodes.csv");
        }
    }
    if output.join("eye-metrics.csv").is_file() {
        artifact_names.push("eye-metrics.csv");
    }
    if output.join("bathtub.csv").is_file() {
        artifact_names.push("bathtub.csv");
    }
    if output.join("eye-contours.csv").is_file() {
        artifact_names.push("eye-contours.csv");
    }
    if output.join("dfe-adaptation.csv").is_file() {
        artifact_names.push("dfe-adaptation.csv");
    }
    if output.join("dfe-events.csv").is_file() {
        artifact_names.push("dfe-events.csv");
    }
    for name in artifact_names {
        artifacts.insert(name.into(), file_identity(&output.join(name))?);
    }
    let receipt = json!({
        "schema": RECEIPT_SCHEMA,
        "status": "complete",
        "workflow": match mode {
            ChannelPolicyMode::PhysicalVoltage => "physical-voltage-v1 with existing native link stages",
            ChannelPolicyMode::TouchstoneNetwork => "touchstone-network-v1 with existing native link stages",
            ChannelPolicyMode::Compat => "PB-02 sim-native",
        },
        "channel_policy": match mode {
            ChannelPolicyMode::PhysicalVoltage => PHYSICAL_CHANNEL_POLICY_V1,
            ChannelPolicyMode::TouchstoneNetwork => TOUCHSTONE_CHANNEL_POLICY_V1,
            ChannelPolicyMode::Compat => "pb-02-compat",
        },
        "backend": "in_process_sipi_pybert_direct",
        "upstream_commit": "5bf6d7ea0ace261891aaeb611ffc1c267e160afe",
        "executable": file_identity(&std::env::current_exe()?)?,
        "waveform_samples": time.len(),
        "channel_impulse_samples": impulse.len(),
        "native_array_count": report.output.arrays.len(),
        "preview_samples": preview_samples,
        "report_data_policy": "all_waveform_and_impulse_samples_embedded; original_f64; at_most_4096_contiguous_samples_per_view; no_decimation",
        "csv_policy": "all_samples_original_grid_roundtrip_f64_no_alignment_or_scaling",
        "compatibility_metadata": match mode {
            ChannelPolicyMode::PhysicalVoltage => "meta.json uses sipi.channel.physical-result.v1; physical_channel diagnostics declare the voltage and finite-band time contract",
            ChannelPolicyMode::TouchstoneNetwork => "meta.json uses sipi.channel.touchstone-result.v1; touchstone_network diagnostics declare grid coverage, passivity, reciprocity, causality, and termination contracts",
            ChannelPolicyMode::Compat => "meta.json preserves the PB-02 upstream schema and engine labels; executable identifies this SIPI run",
        },
        "artifacts": artifacts,
        "acceptance": false,
        "scope": "local_candidate_not_full_upstream_parity_or_ads_acceptance_or_release"
    });
    let receipt_bytes = serde_json::to_vec_pretty(&receipt).map_err(|_| Failure::Io)?;
    write_new(&output.join("receipt.json"), &receipt_bytes)?;
    Ok(receipt)
}

fn sweep(request: &Path, output: &Path, _mode: ChannelPolicyMode) -> Result<Value, Failure> {
    let file = File::open(request)?;
    if !file.metadata()?.is_file() {
        return Err(Failure::InvalidInput);
    }
    let mut bytes = Vec::new();
    file.take(MAX_REQUEST_BYTES + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > MAX_REQUEST_BYTES {
        return Err(Failure::InvalidInput);
    }

    let input: SimulationInputV1 =
        serde_json::from_slice(&bytes).map_err(|_| Failure::InvalidInput)?;
    input.validate().map_err(|_| Failure::InvalidInput)?;

    let raw: Value = serde_json::from_slice(&bytes).map_err(|_| Failure::InvalidInput)?;
    let sweep_cfg: sipi_pybert_direct::EqSweepConfigV1 = raw
        .get("sweep")
        .and_then(|v| serde_json::from_value(v.clone()).ok())
        .unwrap_or_default();
    let base_dir = request.parent().unwrap_or_else(|| Path::new("."));
    let mut sim_input = input.clone();
    if matches!(_mode, ChannelPolicyMode::TouchstoneNetwork) || matches!(input.channel, sipi_pybert_direct::ChannelInputV1::Touchstone(_)) {
        let resp = sipi_pybert_direct::resolve_touchstone_channel_response(&bytes, base_dir)
            .map_err(|_| Failure::InvalidInput)?;
        sim_input.channel = sipi_pybert_direct::ChannelInputV1::ImpulseResponse(resp);
    }

    let report = sipi_pybert_direct::run_eq_sweep(&sim_input, &sweep_cfg)
        .map_err(|_| Failure::InvalidInput)?;
    if let Some(parent) = output.parent().filter(|path| !path.as_os_str().is_empty()) {
        fs::create_dir_all(parent)?;
    }
    fs::create_dir(output)?;
    write_new(&output.join("request.json"), &bytes)?;

    let csv_content = sipi_pybert_direct::sweep_results_to_csv(&report.candidates);
    write_new(&output.join("sweep-results.csv"), csv_content.as_bytes())?;

    let meta = json!({
        "schema": "sipi.channel.sweep-result.v1",
        "totalCandidates": report.total_candidates,
        "validCandidates": report.valid_candidates,
        "optimalCandidateId": report.optimal_candidate_id,
        "optimalCtleBoostDb": report.optimal_ctle_boost_db,
        "optimalTxFfeWeights": report.optimal_tx_ffe_weights,
        "optimalEyeHeightV": report.optimal_eye_height_v,
        "optimalEyeWidthPs": report.optimal_eye_width_ps,
    });
    write_new(&output.join("meta.json"), &serde_json::to_vec_pretty(&meta).map_err(|_| Failure::Io)?)?;

    let receipt = json!({
        "schema": RECEIPT_SCHEMA,
        "command": "channel sweep",
        "status": "complete",
        "acceptance": false,
        "total_candidates": report.total_candidates,
        "valid_candidates": report.valid_candidates,
        "optimal_ctle_boost_db": report.optimal_ctle_boost_db,
        "optimal_tx_ffe_weights": report.optimal_tx_ffe_weights,
        "optimal_eye_height_v": report.optimal_eye_height_v,
        "optimal_eye_width_ps": report.optimal_eye_width_ps,
        "artifacts": {
            "request.json": file_identity(&output.join("request.json"))?,
            "sweep-results.csv": file_identity(&output.join("sweep-results.csv"))?,
            "meta.json": file_identity(&output.join("meta.json"))?
        }
    });
    write_new(&output.join("receipt.json"), &serde_json::to_vec_pretty(&receipt).map_err(|_| Failure::Io)?)?;

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

struct LimitedWriter<W> {
    inner: W,
    remaining: usize,
}

impl<W: Write> Write for LimitedWriter<W> {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        if bytes.len() > self.remaining {
            return Err(io::Error::other("report byte budget exceeded"));
        }
        let written = self.inner.write(bytes)?;
        self.remaining -= written;
        Ok(written)
    }

    fn flush(&mut self) -> io::Result<()> {
        self.inner.flush()
    }
}

fn write_report(
    path: &Path,
    html: &str,
    time: &[f64],
    waves: &[&[f64]],
    impulse_time: &[f64],
    impulse: &[f64],
    bathtub_info: Option<(&[f64], &[f64])>,
) -> Result<(), Failure> {
    let mut writer = LimitedWriter {
        inner: BufWriter::new(OpenOptions::new().write(true).create_new(true).open(path)?),
        remaining: MAX_REPORT_BYTES,
    };
    writer.write_all(html.as_bytes())?;
    // Stream borrowed numeric arrays, rather than cloning the full simulation
    // into a JSON Value or a second large HTML string. No caller text enters JS.
    writer.write_all(b"<script type=\"application/json\" id=\"channel-data\">{")?;
    let impulse_cols = [impulse];
    let b_ber_col = bathtub_info.map(|(_, b)| [b]);
    let mut datasets: Vec<(&str, &[f64], &[&[f64]])> = vec![
        ("waveform", time, waves),
        ("impulse", impulse_time, &impulse_cols),
    ];
    if let (Some((b_time, _)), Some(b_cols)) = (bathtub_info, &b_ber_col) {
        datasets.push(("bathtub", b_time, b_cols));
    }
    for (index, (name, axis, columns)) in datasets.into_iter().enumerate() {
        if index != 0 {
            writer.write_all(b",")?;
        }
        write!(writer, "\"{name}\":{{\"time\":")?;
        serde_json::to_writer(&mut writer, axis).map_err(|_| Failure::Io)?;
        writer.write_all(b",\"columns\":")?;
        serde_json::to_writer(&mut writer, columns).map_err(|_| Failure::Io)?;
        writer.write_all(b"}")?;
    }
    writer
        .write_all(b"}</script><script src=\"channel-report.js\" defer></script></body></html>")?;
    writer.flush()?;
    writer.inner.get_ref().sync_all()?;
    Ok(())
}

fn write_csv(
    path: &Path,
    axis_name: &str,
    time: &[f64],
    names: &[&str],
    columns: &[&[f64]],
) -> Result<(), Failure> {
    let mut writer = BufWriter::new(OpenOptions::new().write(true).create_new(true).open(path)?);
    let header = format!("{axis_name},{}\n", names.join(","));
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
    bathtub_info: Option<(&[f64], &[f64])>,
    preview: usize,
) -> String {
    let mut html = String::from(
        r#"<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
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
.controls{display:grid;grid-template-columns:repeat(3,minmax(0,180px));gap:12px;margin:12px 0}.controls[hidden],.readout[hidden]{display:none}
.controls label{display:grid;gap:6px;color:#55625d}input{font:inherit;accent-color:#206e55}input[type=number]{width:100%;min-width:0;border:1px solid #aebdb5;border-radius:4px;padding:7px;color:#202723;background:#fff}
.position{grid-column:1/-1;width:100%;margin:0;min-height:28px}.legend label{display:flex;align-items:center;gap:6px;min-width:0;overflow-wrap:anywhere}.legend label input{flex:none;margin:0}
.readout{border-collapse:collapse;width:100%;max-width:680px;margin-top:14px;font:12px Consolas,monospace;table-layout:fixed}.readout th,.readout td{padding:6px 8px;border-bottom:1px solid #e1e8e4;text-align:left;overflow-wrap:anywhere}.readout th{width:47%;font-weight:400;color:#55625d}
.range-status{display:block;min-height:24px;color:#55625d;font:12px Consolas,monospace}.interactive .plot{overflow:hidden}.interactive .plot svg{min-width:0;height:300px;touch-action:pan-y}
input:focus-visible,summary:focus-visible,a:focus-visible{outline:2px solid #166a9b;outline-offset:3px}
details{margin-top:24px}summary{cursor:pointer;font-weight:600}pre{background:#f3f6f5;padding:16px;max-height:420px;overflow:auto;line-height:1.5}
@media(max-width:600px){header,main{padding:18px}.summary{grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}h1{font-size:23px}.controls label{grid-template-rows:32px auto}.readout{font-size:11px}}
</style></head><body><header><h1>SIPI Channel</h1><p class="status">Local Rust candidate / acceptance: false</p>"#,
    );
    html.push_str(&format!("<p>{}</p>", escape(&report.output.run_id)));
    if report.diagnostics["physical_channel"].is_object() {
        html.push_str("<p>Physical load voltage / absolute impulse origin / finite-band kernel</p><p class=\"muted\">Continuous-time causality and ADS finite-edge Transient parity are not certified.</p><a href=\"frequency-response.csv\">Physical frequency response CSV</a>");
    }
    html.push_str(r#"<nav aria-label="Artifacts"><a href="waveforms.csv">Waveforms CSV</a><a href="channel-impulse.csv">Impulse CSV</a><a href="arrays.npz">Native arrays</a><a href="meta.json">Native metadata</a><a href="request.json">Request</a><a href="receipt.json">Run receipt</a>"#);
    if report.output.metrics.keys().any(|k| k.starts_with("eye_") || k.starts_with("jitter_") || k.starts_with("bathtub_") || k.starts_with("pam4_")) {
        html.push_str("<a href=\"eye-metrics.csv\">Eye metrics CSV</a>");
    }
    if bathtub_info.is_some() {
        html.push_str("<a href=\"bathtub.csv\">Bathtub CSV</a>");
    }
    if report.output.arrays.contains_key("eye_contour_0_x_ui") {
        html.push_str("<a href=\"eye-contours.csv\">Eye contours CSV</a>");
    }
    if report.output.arrays.contains_key("dfe_tap_weights_v") {
        html.push_str("<a href=\"dfe-adaptation.csv\">DFE adaptation CSV</a>");
    }
    if report.output.arrays.contains_key("dfe_slicer_inputs_v") {
        html.push_str("<a href=\"dfe-events.csv\">DFE events CSV</a>");
    }
    html.push_str("</nav></header><main>");
    html.push_str(&format!("<dl class=\"summary\"><div><dt>Samples</dt><dd>{}</dd></div><div><dt>Sample interval</dt><dd>{:.6} ps</dd></div><div><dt>Data rate</dt><dd>{:.3} GHz</dd></div><div><dt>Native arrays</dt><dd>{}</dd></div>", time.len(), report.input.timebase.sample_interval.0 * 1e12, report.input.timebase.data_rate.0 * 1e-9, report.output.arrays.len()));
    if let Some(&height) = report.output.metrics.get("eye_height_v") {
        html.push_str(&format!("<div><dt>Eye height</dt><dd>{:.2} mV</dd></div>", height * 1e3));
    }
    if let Some(&width) = report.output.metrics.get("eye_width_ps") {
        html.push_str(&format!("<div><dt>Eye width</dt><dd>{:.2} ps</dd></div>", width));
    }
    if let Some(&rj) = report.output.metrics.get("jitter_chnl_dual_dirac_random_s").or_else(|| report.output.metrics.get("jitter_dual_dirac_random_s")) {
        html.push_str(&format!("<div><dt>Random jitter (RJ)</dt><dd>{:.3} ps</dd></div>", rj * 1e12));
    }
    if let Some(&dj) = report.output.metrics.get("jitter_chnl_dual_dirac_periodic_s").or_else(|| report.output.metrics.get("jitter_dual_dirac_periodic_s")) {
        html.push_str(&format!("<div><dt>Deterministic jitter (DJ)</dt><dd>{:.3} ps</dd></div>", dj * 1e12));
    }
    if let Some(&rlm) = report.output.metrics.get("pam4_rlm") {
        html.push_str("<div><dt>Modulation</dt><dd>PAM4</dd></div>");
        html.push_str(&format!("<div><dt>PAM4 RLM</dt><dd>{:.4}</dd></div>", rlm));
        if let Some(&worst_h) = report.output.metrics.get("pam4_eye_height_worst_v") {
            html.push_str(&format!("<div><dt>Worst eye height</dt><dd>{:.2} mV</dd></div>", worst_h * 1e3));
        }
        if let Some(&worst_w) = report.output.metrics.get("pam4_eye_width_worst_ps") {
            html.push_str(&format!("<div><dt>Worst eye width</dt><dd>{:.2} ps</dd></div>", worst_w));
        }
        if let (Some(&ser), Some(&ber)) = (report.output.metrics.get("pam4_ser"), report.output.metrics.get("pam4_ber")) {
            html.push_str(&format!("<div><dt>PAM4 SER / BER</dt><dd>{:.2e} / {:.2e}</dd></div>", ser, ber));
        }
    }
    if let Some(&xtalk_rms) = report.output.metrics.get("crosstalk_rms_v") {
        html.push_str(&format!("<div><dt>Crosstalk RMS</dt><dd>{:.2} mV</dd></div>", xtalk_rms * 1e3));
        if let Some(&xtalk_p2p) = report.output.metrics.get("crosstalk_peak_to_peak_v") {
            html.push_str(&format!("<div><dt>Crosstalk P-P</dt><dd>{:.2} mV</dd></div>", xtalk_p2p * 1e3));
        }
        if let Some(&scr) = report.output.metrics.get("crosstalk_scr_db") {
            html.push_str(&format!("<div><dt>SCR</dt><dd>{:.2} dB</dd></div>", scr));
        }
    }
    html.push_str(&format!("<section data-view=\"waveform\" aria-label=\"Stage waveforms\"><h2>Stage waveforms</h2><output class=\"range-status\">Samples 0..{} of {}</output>", preview.saturating_sub(1), time.len()));
    html.push_str(&report_controls("waveform", time.len(), preview));
    let preview_waves = waves
        .iter()
        .map(|values| &values[..preview])
        .collect::<Vec<_>>();
    html.push_str(&plot(&time[..preview], WAVEFORMS, &preview_waves, "V"));
    html.push_str("</section><section data-view=\"impulse\" aria-label=\"Channel discrete impulse\"><h2>Channel discrete impulse</h2>");
    let impulse_preview = impulse.len().min(4096);
    html.push_str(&format!(
        "<output class=\"range-status\">Samples 0..{} of {}</output>",
        impulse_preview.saturating_sub(1),
        impulse.len()
    ));
    html.push_str(&report_controls("impulse", impulse.len(), impulse_preview));
    html.push_str(&plot(
        &impulse_time[..impulse_preview],
        &["channel_impulse_v_per_v"],
        &[&impulse[..impulse_preview]],
        "V/V",
    ));
    html.push_str("</section>");
    if let Some((b_time, b_ber)) = bathtub_info {
        let b_preview = b_time.len().min(4096);
        html.push_str(&format!(
            "<section data-view=\"bathtub\" aria-label=\"BER Bathtub curve\"><h2>BER Bathtub curve</h2><output class=\"range-status\">Samples 0..{} of {}</output>",
            b_preview.saturating_sub(1),
            b_time.len()
        ));
        html.push_str(&report_controls("bathtub", b_time.len(), b_preview));
        html.push_str(&plot(
            &b_time[..b_preview],
            &["bathtub_ber"],
            &[&b_ber[..b_preview]],
            "BER",
        ));
        html.push_str("</section>");
    }
    html.push_str("<details><summary>Effective request</summary><pre>");
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
    html.push_str("</pre></details></main>");
    html
}

fn report_controls(name: &str, length: usize, window: usize) -> String {
    let last = length.saturating_sub(1);
    let maximum_window = length.clamp(1, 4096);
    format!(
        "<div class=\"controls\" hidden><label>Start sample<input data-control=\"start\" type=\"number\" min=\"0\" max=\"{last}\" step=\"1\" value=\"0\"></label><label>Window samples<input data-control=\"count\" type=\"number\" min=\"1\" max=\"{maximum_window}\" step=\"1\" value=\"{window}\"></label><label>Cursor sample<input data-control=\"cursor\" type=\"number\" min=\"0\" max=\"{last}\" step=\"1\" value=\"0\"></label><input class=\"position\" data-control=\"position\" aria-label=\"{name} window position\" type=\"range\" min=\"0\" max=\"{last}\" step=\"1\" value=\"0\"></div><table class=\"readout\" aria-label=\"{name} original sample\" hidden><tbody></tbody></table>"
    )
}

#[cfg(test)]
mod report_tests {
    use super::*;

    #[test]
    fn report_budget_is_enforced_before_writing_excess_bytes() {
        let mut writer = LimitedWriter {
            inner: Vec::new(),
            remaining: 4,
        };
        writer.write_all(b"123").unwrap();
        assert!(writer.write_all(b"45").is_err());
        assert_eq!(writer.inner, b"123");
        writer.write_all(b"4").unwrap();
        assert!(writer.write_all(b"5").is_err());
        assert_eq!(writer.inner, b"1234");
    }
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
