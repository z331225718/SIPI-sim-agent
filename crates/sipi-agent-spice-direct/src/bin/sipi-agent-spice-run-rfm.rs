use std::path::PathBuf;
use std::process::ExitCode;

use sipi_agent_spice_direct::as06_run_rfm::{RunRfmRequest, run_rfm};

fn take(args: &[String], index: &mut usize, option: &str) -> Result<String, String> {
    *index += 1;
    args.get(*index)
        .cloned()
        .ok_or_else(|| format!("{option} requires a value"))
}

fn main() -> ExitCode {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    if args.iter().any(|value| value == "--help" || value == "-h") {
        println!(
            "usage: sipi-agent-spice-run-rfm DECK --rfm FILE --backend native|ngspice --output-root DIR [--execute] [--native-engine PATH] [--ngspice PATH] [--code-model PATH] [--dotnet PATH]"
        );
        return ExitCode::SUCCESS;
    }
    let deck = match args.first().filter(|value| !value.starts_with('-')) {
        Some(value) => PathBuf::from(value),
        None => {
            eprintln!("deck is required");
            return ExitCode::from(2);
        }
    };
    let mut rfm = None;
    let mut backend = None;
    let mut output_root = None;
    let mut subckt = "rfm_direct".to_owned();
    let mut code_model = None;
    let mut native_engine = None;
    let mut ngspice = "ngspice".to_owned();
    let mut dotnet = "dotnet".to_owned();
    let mut execute = false;
    let mut index = 1;
    while index < args.len() {
        let option = &args[index];
        let result = match option.as_str() {
            "--rfm" => {
                take(&args, &mut index, option).map(|value| rfm = Some(PathBuf::from(value)))
            }
            "--backend" => take(&args, &mut index, option).map(|value| backend = Some(value)),
            "--output-root" => take(&args, &mut index, option)
                .map(|value| output_root = Some(PathBuf::from(value))),
            "--subckt-name" => take(&args, &mut index, option).map(|value| subckt = value),
            "--code-model" => {
                take(&args, &mut index, option).map(|value| code_model = Some(PathBuf::from(value)))
            }
            "--native-engine" => take(&args, &mut index, option)
                .map(|value| native_engine = Some(PathBuf::from(value))),
            "--ngspice" => take(&args, &mut index, option).map(|value| ngspice = value),
            "--dotnet" => take(&args, &mut index, option).map(|value| dotnet = value),
            "--execute" => {
                execute = true;
                Ok(())
            }
            other => Err(format!("unsupported option '{other}'")),
        };
        if let Err(error) = result {
            eprintln!("argument error: {error}");
            return ExitCode::from(2);
        }
        index += 1;
    }
    let (rfm, backend, output_root) = match (rfm, backend, output_root) {
        (Some(rfm), Some(backend), Some(output_root)) => (rfm, backend, output_root),
        _ => {
            eprintln!("--rfm, --backend, and --output-root are required");
            return ExitCode::from(2);
        }
    };
    let mut request = match RunRfmRequest::new(deck, rfm, &backend, output_root) {
        Ok(value) => value,
        Err(error) => {
            eprintln!("run-rfm argument error: {error}");
            return ExitCode::from(2);
        }
    };
    request.subckt_name = subckt;
    request.code_model = code_model;
    request.native_engine = native_engine;
    request.ngspice = ngspice;
    request.dotnet = dotnet;
    request.execute = execute;
    match run_rfm(&request) {
        Ok(result) => {
            println!(
                "{{\"status\":\"{}\",\"response_samples\":{},\"report\":\"{}\"}}",
                result.status,
                result.response_samples,
                result.report.display()
            );
            if result.status == "BLOCKED" {
                ExitCode::from(1)
            } else {
                ExitCode::SUCCESS
            }
        }
        Err(error) => {
            eprintln!("run-rfm failed: {error}");
            ExitCode::from(2)
        }
    }
}
