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

use error::{Error, Result};

fn main() {
    if let Err(error) = run() {
        eprintln!("agent-spice-sim: {error}");
        std::process::exit(1);
    }
}

fn run() -> Result<()> {
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
    if waveform_csv.is_some() && output_json.is_none() {
        return Err(Error::Usage("--waveform-csv requires --output-json".into()));
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

    let rfm = rfm_path
        .as_deref()
        .map(rfm::RfmModel::parse_file)
        .transpose()?;
    let binding = rfm
        .as_ref()
        .map(|model| (rfm_subcircuit.as_str(), model.nports));
    let deck = netlist::Deck::parse_file(&deck, binding)?;
    let result = simulator::run(&deck, rfm.as_ref())?;
    if let Some(output_json) = output_json {
        output::write_json(&result, &output_json)?;
        let waveform_rows = waveform_csv
            .as_deref()
            .map(|path| output::write_waveform(&result, path))
            .transpose()?
            .unwrap_or(0);
        println!(r#"{{"ok":true,"waveformRows":{waveform_rows}}}"#);
    } else {
        println!("{}", serde_json::to_string(&result)?);
    }
    Ok(())
}

fn usage() -> String {
    "agent-spice-sim <deck> [--rfm <model.rfm>] [--rfm-subckt <name>] \
     [--output-json <result.json>] [--waveform-csv <waveform.csv>] \
     [--audit-json <compatibility.json>]"
        .into()
}
