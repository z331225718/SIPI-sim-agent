use std::path::PathBuf;
use std::process::ExitCode;

use sipi_agent_spice_direct::as03_fit_yparam::{FitYparamOptions, FitYparamRequest, fit_yparam};
use sipi_agent_spice_direct::fit_sparam::PassivityPolicy;

fn take(args: &[String], index: &mut usize, option: &str) -> Result<String, String> {
    *index += 1;
    args.get(*index)
        .cloned()
        .ok_or_else(|| format!("{option} requires a value"))
}

fn main() -> ExitCode {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    if args.iter().any(|value| value == "--help" || value == "-h") {
        println!("usage: sipi-agent-spice-fit-yparam TOUCHSTONE [options]");
        return ExitCode::SUCCESS;
    }
    let input = match args.first().filter(|value| !value.starts_with('-')) {
        Some(value) => PathBuf::from(value),
        None => {
            eprintln!("touchstone is required");
            return ExitCode::from(2);
        }
    };
    let mut options = FitYparamOptions::default();
    let mut index = 1;
    while index < args.len() {
        let option = &args[index];
        let result = match option.as_str() {
            "--output" => take(&args, &mut index, option)
                .map(|value| options.output = Some(PathBuf::from(value))),
            "--derived-s-touchstone" => take(&args, &mut index, option)
                .map(|value| options.derived_s_touchstone = Some(PathBuf::from(value))),
            "--html-report" => take(&args, &mut index, option)
                .map(|value| options.html_report = Some(PathBuf::from(value))),
            "--report" => take(&args, &mut index, option)
                .map(|value| options.report = Some(PathBuf::from(value))),
            "--log" => take(&args, &mut index, option)
                .map(|value| options.log = Some(PathBuf::from(value))),
            "--subckt-name" => {
                take(&args, &mut index, option).map(|value| options.subckt_name = value)
            }
            "--n-poles-real" => take(&args, &mut index, option)
                .and_then(|value| {
                    value
                        .parse()
                        .map_err(|_| "invalid real pole count".to_owned())
                })
                .map(|value| options.n_poles_real = value),
            "--n-poles-cmplx" => take(&args, &mut index, option)
                .and_then(|value| {
                    value
                        .parse()
                        .map_err(|_| "invalid complex pole count".to_owned())
                })
                .map(|value| options.n_poles_cmplx = value),
            "--max-order" => take(&args, &mut index, option)
                .and_then(|value| value.parse().map_err(|_| "invalid max order".to_owned()))
                .map(|value| options.max_order = value),
            "--order-step" => take(&args, &mut index, option)
                .and_then(|value| value.parse().map_err(|_| "invalid order step".to_owned()))
                .map(|value| options.order_step = value),
            "--pole-spacing" => {
                take(&args, &mut index, option).map(|value| options.pole_spacing = value)
            }
            "--fit-iterations" => take(&args, &mut index, option)
                .and_then(|value| {
                    value
                        .parse()
                        .map_err(|_| "invalid fit iterations".to_owned())
                })
                .map(|value| options.fit_iterations = value),
            "--no-fit-proportional" => {
                options.fit_proportional = false;
                Ok(())
            }
            "--max-y-rms-siemens" => take(&args, &mut index, option)
                .and_then(|value| value.parse().map_err(|_| "invalid Y RMS target".to_owned()))
                .map(|value| options.max_y_rms_siemens = Some(value)),
            "--passivity" => take(&args, &mut index, option)
                .and_then(|value| PassivityPolicy::parse(&value).map_err(|error| error.to_string()))
                .map(|value| options.passivity = value),
            "--passivity-epsilon" => take(&args, &mut index, option)
                .and_then(|value| {
                    value
                        .parse()
                        .map_err(|_| "invalid passivity epsilon".to_owned())
                })
                .map(|value| options.passivity_epsilon = value),
            "--conversion-condition-limit" => take(&args, &mut index, option)
                .and_then(|value| {
                    value
                        .parse()
                        .map_err(|_| "invalid conversion condition limit".to_owned())
                })
                .map(|value| options.conversion_condition_limit = value),
            "--exact-s-rfm" => take(&args, &mut index, option)
                .map(|value| options.exact_s_rfm = Some(PathBuf::from(value))),
            "--exact-s-touchstone" => take(&args, &mut index, option)
                .map(|value| options.exact_s_touchstone = Some(PathBuf::from(value))),
            "--exact-s-rfm-wrapper" => take(&args, &mut index, option)
                .map(|value| options.exact_s_rfm_wrapper = Some(PathBuf::from(value))),
            other => Err(format!("unsupported option '{other}'")),
        };
        if let Err(error) = result {
            eprintln!("argument error: {error}");
            return ExitCode::from(2);
        }
        index += 1;
    }
    let request = match FitYparamRequest::new(input, options) {
        Ok(value) => value,
        Err(error) => {
            eprintln!("fit-yparam argument error: {error}");
            return ExitCode::from(2);
        }
    };
    match fit_yparam(&request) {
        Ok(result) => {
            println!(
                "{{\"target_met\":{},\"selected_order\":{},\"y_rms_siemens\":{:.17e}}}",
                result.target_met, result.selected_order, result.y_rms_siemens
            );
            if result.target_met {
                ExitCode::SUCCESS
            } else {
                ExitCode::from(1)
            }
        }
        Err(error) => {
            eprintln!("fit-yparam failed: {error}");
            ExitCode::from(2)
        }
    }
}
