use std::path::PathBuf;
use std::process::ExitCode;

use sipi_agent_spice_direct::as02_fit_sparam_cascade::{
    FitSparamCascadeOptions, FitSparamCascadeRequest, fit_sparam_cascade,
};
use sipi_agent_spice_direct::fit_sparam::PriorityBand;

fn value(args: &[String], index: &mut usize, option: &str) -> Result<String, String> {
    *index += 1;
    args.get(*index)
        .cloned()
        .ok_or_else(|| format!("{option} requires a value"))
}

fn band(text: &str) -> Result<PriorityBand, String> {
    let values = text
        .split(':')
        .map(|value| {
            value
                .parse::<f64>()
                .map_err(|_| "invalid priority band".to_owned())
        })
        .collect::<Result<Vec<_>, _>>()?;
    if values.len() < 3 || values.len() > 4 {
        return Err("priority band must be F_MIN:F_MAX:RMS[:WEIGHT]".to_owned());
    }
    PriorityBand::new(
        values[0],
        values[1],
        values[2],
        values.get(3).copied().unwrap_or(1.0),
    )
    .map_err(|error| error.to_string())
}

fn main() -> ExitCode {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    if args.iter().any(|value| value == "--help" || value == "-h") {
        println!("usage: sipi-agent-spice-fit-sparam-cascade MANIFEST --output-root DIR [options]");
        return ExitCode::SUCCESS;
    }
    let manifest = match args.first().filter(|value| !value.starts_with('-')) {
        Some(value) => PathBuf::from(value),
        None => {
            eprintln!("manifest is required");
            return ExitCode::from(2);
        }
    };
    let mut options = FitSparamCascadeOptions::default();
    let mut index = 1;
    while index < args.len() {
        let option = &args[index];
        let result = match option.as_str() {
            "--output-root" => value(&args, &mut index, option)
                .map(|value| options.output_root = PathBuf::from(value)),
            "--report" => value(&args, &mut index, option)
                .map(|value| options.report = Some(PathBuf::from(value))),
            "--rms-target" => value(&args, &mut index, option)
                .and_then(|value| value.parse().map_err(|_| "invalid rms target".to_owned()))
                .map(|value| options.rms_target = Some(value)),
            "--max-order" => value(&args, &mut index, option)
                .and_then(|value| value.parse().map_err(|_| "invalid max order".to_owned()))
                .map(|value| options.max_order = value),
            "--min-order" => value(&args, &mut index, option)
                .and_then(|value| value.parse().map_err(|_| "invalid min order".to_owned()))
                .map(|value| options.min_order = value),
            "--max-order-step" => value(&args, &mut index, option)
                .and_then(|value| value.parse().map_err(|_| "invalid order step".to_owned()))
                .map(|value| options.max_order_step = value),
            "--passivity-epsilon" => value(&args, &mut index, option)
                .and_then(|value| {
                    value
                        .parse()
                        .map_err(|_| "invalid passivity epsilon".to_owned())
                })
                .map(|value| options.passivity_epsilon = value),
            "--cascade-passivity-epsilon" => value(&args, &mut index, option)
                .and_then(|value| {
                    value
                        .parse()
                        .map_err(|_| "invalid cascade passivity epsilon".to_owned())
                })
                .map(|value| options.cascade_passivity_epsilon = value),
            "--cascade-rms-target" => value(&args, &mut index, option)
                .and_then(|value| {
                    value
                        .parse()
                        .map_err(|_| "invalid cascade rms target".to_owned())
                })
                .map(|value| options.cascade_rms_target = Some(value)),
            "--cascade-samples" => value(&args, &mut index, option)
                .and_then(|value| {
                    value
                        .parse()
                        .map_err(|_| "invalid cascade samples".to_owned())
                })
                .map(|value| options.cascade_samples = value),
            "--reference-impedance" => value(&args, &mut index, option)
                .and_then(|value| {
                    value
                        .parse()
                        .map_err(|_| "invalid reference impedance".to_owned())
                })
                .map(|value| options.reference_impedance = value),
            "--adjustment-iterations" => value(&args, &mut index, option)
                .and_then(|value| {
                    value
                        .parse()
                        .map_err(|_| "invalid adjustment iterations".to_owned())
                })
                .map(|value| options.adjustment_iterations = value),
            "--minimum-scale" => value(&args, &mut index, option)
                .and_then(|value| {
                    value
                        .parse()
                        .map_err(|_| "invalid minimum scale".to_owned())
                })
                .map(|value| options.minimum_scale = value),
            "--outside-band-weight" => value(&args, &mut index, option)
                .and_then(|value| {
                    value
                        .parse()
                        .map_err(|_| "invalid outside-band weight".to_owned())
                })
                .map(|value| options.outside_band_weight = value),
            "--gate-full-band-rms" => {
                options.gate_full_band_rms = true;
                Ok(())
            }
            "--priority-band-fit-only" => {
                options.priority_band_fit_only = true;
                Ok(())
            }
            "--cascade-refit-max-iterations" => value(&args, &mut index, option)
                .and_then(|value| {
                    value
                        .parse()
                        .map_err(|_| "invalid cascade refit iterations".to_owned())
                })
                .map(|value| options.cascade_refit_max_iterations = value),
            "--priority-band" => value(&args, &mut index, option)
                .and_then(|value| band(&value))
                .map(|value| options.priority_bands.push(value)),
            other => Err(format!("unsupported option '{other}'")),
        };
        if let Err(error) = result {
            eprintln!("argument error: {error}");
            return ExitCode::from(2);
        }
        index += 1;
    }
    let request = match FitSparamCascadeRequest::new(manifest, options) {
        Ok(value) => value,
        Err(error) => {
            eprintln!("fit-sparam-cascade argument error: {error}");
            return ExitCode::from(2);
        }
    };
    match fit_sparam_cascade(&request) {
        Ok(result) => {
            println!(
                "{{\"status\":\"{}\",\"report\":\"{}\"}}",
                result.status,
                result.report.display()
            );
            if result.status == "PASS" {
                ExitCode::SUCCESS
            } else {
                ExitCode::from(1)
            }
        }
        Err(error) => {
            eprintln!("fit-sparam-cascade failed: {error}");
            ExitCode::from(2)
        }
    }
}
