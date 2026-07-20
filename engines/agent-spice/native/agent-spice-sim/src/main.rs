mod compatibility;
mod error;
mod expression;
mod netlist;
mod output;
mod result;
mod rfm;
mod simulator;
mod sparse;

use std::env;
use std::fs::File;
use std::io::BufWriter;
use std::path::PathBuf;
use std::time::Instant;

use error::{Error, Result};

fn log_rfm_storage(name: &str, model: &rfm::RfmModel) {
    let stats = model.storage_stats();
    let compression = stats.legacy_dense_state_scalars as f64 / stats.state_scalars.max(1) as f64;
    let history = if stats.dense_history_bytes == 0 {
        "sparse".to_string()
    } else {
        format!(
            "dense/{:.1} MiB",
            stats.dense_history_bytes as f64 / (1024.0 * 1024.0)
        )
    };
    eprintln!(
        "[agent-spice-sim] RFM {name}: ports={} unique-poles={} modes={} state-scalars={} terms={} state-compression={compression:.1}x history={history} legacy-history={:.1} MiB",
        model.nports,
        stats.unique_poles,
        stats.dynamic_modes,
        stats.state_scalars,
        stats.response_terms,
        stats.legacy_dense_history_bytes as f64 / (1024.0 * 1024.0),
    );
}

fn main() {
    if let Err(error) = run() {
        eprintln!("agent-spice-sim: {error}");
        std::process::exit(1);
    }
}

fn run() -> Result<()> {
    let started = Instant::now();
    let mut arguments = env::args_os().skip(1);
    let deck = arguments
        .next()
        .map(PathBuf::from)
        .ok_or_else(|| Error::Usage(usage()))?;
    let mut rfm_path = None;
    let mut rfm_subcircuit = "rfm_direct".to_string();
    let mut output_json = None;
    let mut waveform_csv = None;
    let mut audit_json = None;
    while let Some(argument) = arguments.next() {
        if argument == "--rfm" {
            rfm_path = Some(PathBuf::from(
                arguments.next().ok_or_else(|| Error::Usage(usage()))?,
            ));
        } else if argument == "--rfm-subckt" {
            rfm_subcircuit = arguments
                .next()
                .ok_or_else(|| Error::Usage(usage()))?
                .into_string()
                .map_err(|_| Error::Usage("RFM subcircuit name must be valid Unicode".into()))?;
        } else if argument == "--output-json" {
            output_json = Some(PathBuf::from(
                arguments.next().ok_or_else(|| Error::Usage(usage()))?,
            ));
        } else if argument == "--waveform-csv" {
            waveform_csv = Some(PathBuf::from(
                arguments.next().ok_or_else(|| Error::Usage(usage()))?,
            ));
        } else if argument == "--audit-json" {
            audit_json = Some(PathBuf::from(
                arguments.next().ok_or_else(|| Error::Usage(usage()))?,
            ));
        } else {
            return Err(Error::Usage(usage()));
        }
    }
    if !deck.is_file() {
        return Err(Error::InvalidDeck(format!(
            "deck does not exist: {}",
            deck.display()
        )));
    }
    if rfm_path.as_ref().is_some_and(|path| !path.is_file()) {
        return Err(Error::InvalidDeck(format!(
            "RFM model does not exist: {}",
            rfm_path.as_ref().expect("RFM path was checked").display()
        )));
    }
    if let Some(audit_json) = audit_json {
        if output_json.is_some() || waveform_csv.is_some() {
            return Err(Error::Usage(
                "--audit-json cannot be combined with simulation outputs".into(),
            ));
        }
        let report = compatibility::audit_file(&deck)?;
        let writer = BufWriter::new(File::create(audit_json)?);
        serde_json::to_writer_pretty(writer, &report)?;
        println!(
            "{}",
            serde_json::json!({
                "ok": true,
                "compatible": report.issue_count() == 0,
                "issues": report.issue_count(),
                "scannedFiles": report.scanned_file_count(),
            })
        );
        return Ok(());
    }

    eprintln!("[agent-spice-sim] loading deck: {}", deck.display());
    let load_started = Instant::now();
    let rfm = rfm_path
        .as_deref()
        .map(rfm::RfmModel::parse_file)
        .transpose()?;
    let binding = rfm
        .as_ref()
        .map(|model| (rfm_subcircuit.as_str(), model.nports));
    let deck = netlist::Deck::parse_file(&deck, binding)?;
    if let Some(model) = rfm.as_ref() {
        log_rfm_storage("<command-line>", model);
    }
    let mut model_names: Vec<_> = deck.rfm_models.keys().collect();
    model_names.sort();
    for name in model_names {
        log_rfm_storage(name, &deck.rfm_models[name]);
    }
    eprintln!(
        "[agent-spice-sim] parsed: {} element(s), {} node(s), {} analysis job(s) in {:.3}s",
        deck.elements.len(),
        deck.nodes.len(),
        deck.analyses.len(),
        load_started.elapsed().as_secs_f64()
    );
    if let Some(path) = waveform_csv.as_deref() {
        eprintln!(
            "[agent-spice-sim] streaming waveform CSV: {}",
            path.display()
        );
    }
    let mut observer = output::RuntimeObserver::new(waveform_csv.as_deref(), &deck.analyses)?;
    let retain_points =
        output_json.is_some() || waveform_csv.is_none() || !deck.measurements.is_empty();
    if waveform_csv.is_some() && !retain_points {
        eprintln!("[agent-spice-sim] streaming mode: full waveform points are not retained");
    }
    let result = simulator::run_with_observer(&deck, rfm.as_ref(), &mut observer, retain_points)?;
    let waveform_rows = observer.finish()?;
    if let Some(output_json) = output_json.as_deref() {
        let json_started = Instant::now();
        output::write_json(&result, output_json)?;
        eprintln!(
            "[agent-spice-sim] wrote final JSON: {} in {:.3}s",
            output_json.display(),
            json_started.elapsed().as_secs_f64()
        );
        println!(r#"{{"ok":true,"waveformRows":{waveform_rows}}}"#);
    } else if waveform_csv.is_some() {
        println!(
            "{}",
            serde_json::json!({
                "ok": true,
                "waveformRows": waveform_rows,
                "measurements": result.measurements,
                "statistics": result.statistics,
            })
        );
    } else {
        println!("{}", serde_json::to_string(&result)?);
    }
    eprintln!(
        "[agent-spice-sim] simulation completed in {:.3}s",
        started.elapsed().as_secs_f64()
    );
    Ok(())
}

fn usage() -> String {
    "agent-spice-sim <deck> [--rfm <model.rfm>] [--rfm-subckt <name>] \
     [--output-json <result.json>] [--waveform-csv <waveform.csv>] \
     [--audit-json <compatibility.json>]"
        .into()
}
