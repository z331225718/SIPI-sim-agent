use std::path::PathBuf;
use std::process::ExitCode;

use sipi_agent_spice_direct::as04_tune_yparam_tran::{
    HspiceCustody, TuneYparamTranRequest, tune_yparam_tran, tune_yparam_tran_with_hspice_custody,
};

fn take(args: &[String], index: &mut usize, option: &str) -> Result<String, String> {
    *index += 1;
    args.get(*index)
        .cloned()
        .ok_or_else(|| format!("{option} requires a value"))
}
fn floats(text: &str, label: &str) -> Result<Vec<f64>, String> {
    let values = text
        .split(',')
        .map(|value| {
            value
                .trim()
                .parse::<f64>()
                .map_err(|_| format!("{label} must be comma-separated finite numbers"))
        })
        .collect::<Result<Vec<_>, _>>()?;
    if values.is_empty() {
        Err(format!("{label} must not be empty"))
    } else {
        Ok(values)
    }
}

fn main() -> ExitCode {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    if args.iter().any(|value| value == "--help" || value == "-h") {
        println!(
            "usage: sipi-agent-spice-tune-yparam-tran TOUCHSTONE INPUT_RFM DECK --output-rfm FILE [--work-dir DIR] --rfm-token TOKEN --rms-measure NAME --residual-poles CSV --band-boundaries CSV [--hspice-bin ABSOLUTE_EXE --hspice-sha256 SHA256]"
        );
        return ExitCode::SUCCESS;
    }
    if args.len() < 3 {
        eprintln!("touchstone, input RFM, and deck are required");
        return ExitCode::from(2);
    }
    let mut request = TuneYparamTranRequest {
        touchstone: PathBuf::from(&args[0]),
        input_rfm: PathBuf::from(&args[1]),
        deck: PathBuf::from(&args[2]),
        output_rfm: PathBuf::new(),
        report: None,
        work_dir: PathBuf::new(),
        rfm_token: String::new(),
        rms_measure: String::new(),
        peak_measure: None,
        residual_poles: Vec::new(),
        band_boundaries: Vec::new(),
        hspice_bin: "hspice".to_owned(),
        license_file: None,
        max_evaluations: 150,
        max_static_rms_growth: 0.003,
        max_sigma: 0.999,
    };
    let mut hspice_sha256 = None;
    let mut index = 3;
    while index < args.len() {
        let option = &args[index];
        let result = match option.as_str() {
            "--output-rfm" => take(&args, &mut index, option)
                .map(|value| request.output_rfm = PathBuf::from(value)),
            "--report" => take(&args, &mut index, option)
                .map(|value| request.report = Some(PathBuf::from(value))),
            "--work-dir" => {
                take(&args, &mut index, option).map(|value| request.work_dir = PathBuf::from(value))
            }
            "--rfm-token" => take(&args, &mut index, option).map(|value| request.rfm_token = value),
            "--rms-measure" => {
                take(&args, &mut index, option).map(|value| request.rms_measure = value)
            }
            "--peak-measure" => {
                take(&args, &mut index, option).map(|value| request.peak_measure = Some(value))
            }
            "--residual-poles" => take(&args, &mut index, option)
                .and_then(|value| floats(&value, "residual-poles"))
                .map(|value| request.residual_poles = value),
            "--band-boundaries" => take(&args, &mut index, option)
                .and_then(|value| floats(&value, "band-boundaries"))
                .map(|value| request.band_boundaries = value),
            "--hspice-bin" => {
                take(&args, &mut index, option).map(|value| request.hspice_bin = value)
            }
            "--hspice-sha256" => {
                take(&args, &mut index, option).map(|value| hspice_sha256 = Some(value))
            }
            "--license-file" => {
                take(&args, &mut index, option).map(|value| request.license_file = Some(value))
            }
            "--max-evaluations" => take(&args, &mut index, option)
                .and_then(|value| {
                    value
                        .parse()
                        .map_err(|_| "invalid max-evaluations".to_owned())
                })
                .map(|value| request.max_evaluations = value),
            "--max-static-rms-growth" => take(&args, &mut index, option)
                .and_then(|value| {
                    value
                        .parse()
                        .map_err(|_| "invalid max-static-rms-growth".to_owned())
                })
                .map(|value| request.max_static_rms_growth = value),
            "--max-sigma" => take(&args, &mut index, option)
                .and_then(|value| value.parse().map_err(|_| "invalid max-sigma".to_owned()))
                .map(|value| request.max_sigma = value),
            other => Err(format!("unsupported option '{other}'")),
        };
        if let Err(error) = result {
            eprintln!("argument error: {error}");
            return ExitCode::from(2);
        }
        index += 1;
    }
    let result = hspice_sha256.as_deref().map_or_else(
        || tune_yparam_tran(&request),
        |sha256| {
            let custody = HspiceCustody::new(request.hspice_bin.clone(), sha256);
            tune_yparam_tran_with_hspice_custody(&request, &custody)
        },
    );
    match result {
        Ok(result) => {
            println!(
                "{{\"status\":\"PASS\",\"best_tran_rms\":{:.17e},\"report\":\"{}\"}}",
                result.best_tran_rms,
                result.report.display()
            );
            ExitCode::SUCCESS
        }
        Err(error) => {
            eprintln!("tune-yparam-tran failed: {error}");
            ExitCode::from(2)
        }
    }
}
