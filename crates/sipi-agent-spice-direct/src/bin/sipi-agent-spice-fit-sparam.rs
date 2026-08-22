use std::path::PathBuf;
use std::process::ExitCode;

use sipi_agent_spice_direct::fit_sparam::{
    FitSparamOptions, FitSparamRequest, PassivityPolicy, PriorityBand, fit_sparam,
};

fn take_value(args: &[String], index: &mut usize, option: &str) -> Result<String, String> {
    *index += 1;
    args.get(*index)
        .cloned()
        .ok_or_else(|| format!("{option} requires a value"))
}

fn parse_priority_band(value: &str) -> Result<PriorityBand, String> {
    let parts = value.split(':').collect::<Vec<_>>();
    if !(3..=4).contains(&parts.len()) {
        return Err("priority band must be F_MIN:F_MAX:RMS[:WEIGHT]".to_owned());
    }
    let f_min = parts[0]
        .parse::<f64>()
        .map_err(|_| "invalid priority F_MIN".to_owned())?;
    let f_max = parts[1]
        .parse::<f64>()
        .map_err(|_| "invalid priority F_MAX".to_owned())?;
    let target = parts[2]
        .parse::<f64>()
        .map_err(|_| "invalid priority RMS target".to_owned())?;
    let weight = parts.get(3).map_or(Ok(1.0), |value| {
        value
            .parse::<f64>()
            .map_err(|_| "invalid priority weight".to_owned())
    })?;
    PriorityBand::new(f_min, f_max, target, weight).map_err(|error| error.to_string())
}

fn unsupported_option(option: &str) -> String {
    format!("{option} is not implemented by the bounded Rust fit route")
}

fn parse_args(args: &[String]) -> Result<FitSparamRequest, String> {
    let mut options = FitSparamOptions::default();
    let mut touchstone = None;
    let mut index = if args.first().is_some_and(|value| value == "fit-sparam") {
        1
    } else {
        0
    };
    while index < args.len() {
        let option = &args[index];
        if !option.starts_with('-') {
            if touchstone.is_some() {
                return Err("fit-sparam accepts one Touchstone positional argument".to_owned());
            }
            touchstone = Some(PathBuf::from(option));
            index += 1;
            continue;
        }
        match option.as_str() {
            "--output"
            | "--html-report"
            | "--rfm"
            | "--rfm-wrapper"
            | "--report-top-rms"
            | "--outside-band-weight"
            | "--quality-profile"
            | "--fail-on-quality"
            | "--allow-quality-warnings"
            | "--subckt-name"
            | "--tuning-profile"
            | "--fit-iterations"
            | "--hf-complex-pairs"
            | "--hf-pair-damping"
            | "--hf-pair-start-fraction"
            | "--passivity-max-iterations"
            | "--passivity-samples"
            | "--passivity-active-variables" => return Err(unsupported_option(option)),
            "--report" => {
                options.report = Some(PathBuf::from(take_value(args, &mut index, option)?))
            }
            "--fitted-touchstone" => {
                options.fitted_touchstone =
                    Some(PathBuf::from(take_value(args, &mut index, option)?))
            }
            "--log" => options.log = Some(PathBuf::from(take_value(args, &mut index, option)?)),
            "--rms-target" => {
                options.rms_target = Some(
                    take_value(args, &mut index, option)?
                        .parse::<f64>()
                        .map_err(|_| "invalid RMS target".to_owned())?,
                )
            }
            "--priority-band" => options
                .priority_bands
                .push(parse_priority_band(&take_value(args, &mut index, option)?)?),
            "--passivity" => {
                options.passivity = Some(
                    PassivityPolicy::parse(&take_value(args, &mut index, option)?)
                        .map_err(|error| error.to_string())?,
                )
            }
            "--enforce-passivity" => options.legacy_passivity.enforce = true,
            "--check-passivity" => options.legacy_passivity.check = true,
            "--skip-passivity-check" => options.legacy_passivity.skip_check = true,
            "--skip-passivity-enforce" => options.legacy_passivity.skip_enforce = true,
            "--max-order" => {
                options.max_order = Some(
                    take_value(args, &mut index, option)?
                        .parse::<usize>()
                        .map_err(|_| "invalid max order".to_owned())?,
                )
            }
            "--min-order" => {
                options.min_order = take_value(args, &mut index, option)?
                    .parse::<usize>()
                    .map_err(|_| "invalid min order".to_owned())?
            }
            "--max-order-step" => {
                options.max_order_step = take_value(args, &mut index, option)?
                    .parse::<usize>()
                    .map_err(|_| "invalid max order step".to_owned())?
            }
            "--pole-spacing" => {
                let value = take_value(args, &mut index, option)?;
                if value == "resonance" {
                    return Err(unsupported_option("--pole-spacing resonance"));
                }
                options.pole_spacing = value;
            }
            other => return Err(format!("unsupported fit-sparam option '{other}'")),
        }
        index += 1;
    }
    let touchstone =
        touchstone.ok_or_else(|| "fit-sparam requires a Touchstone path".to_owned())?;
    FitSparamRequest::new(touchstone, options).map_err(|error| error.to_string())
}

fn main() -> ExitCode {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    if args.iter().any(|value| value == "--help" || value == "-h") {
        println!("usage: sipi-agent-spice-fit-sparam fit-sparam TOUCHSTONE [options]");
        return ExitCode::SUCCESS;
    }
    let request = match parse_args(&args) {
        Ok(value) => value,
        Err(error) => {
            eprintln!("fit-sparam argument error: {error}");
            return ExitCode::from(2);
        }
    };
    match fit_sparam(&request) {
        Ok(result) => {
            println!(
                "{{\"target_met\":{},\"selected_order\":{},\"rms_error\":{:.17e},\"passivity\":\"{:?}\"}}",
                result.target_met, result.selected_order, result.rms_error, result.passivity
            );
            if result.target_met {
                ExitCode::SUCCESS
            } else {
                ExitCode::from(1)
            }
        }
        Err(error) => {
            eprintln!("fit-sparam failed: {error}");
            ExitCode::from(2)
        }
    }
}
