use std::path::PathBuf;
use std::process::ExitCode;

use serde_json::json;
use sipi_agent_spice_direct::NgspiceCustody;
use sipi_agent_spice_direct::as06_run_rfm::{
    RfmNgspiceCustody, RunRfmRequest, run_rfm, run_rfm_with_ngspice_custody,
};

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
            "usage: sipi-agent-spice-run-rfm DECK --rfm FILE --backend native|ngspice --output-root DIR [--execute] [--native-engine PATH] [--ngspice PATH --ngspice-sha256 SHA256 --code-model PATH --code-model-sha256 SHA256] [--dotnet PATH]"
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
    let mut ngspice_sha256 = None;
    let mut code_model_sha256 = None;
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
            "--ngspice-sha256" => {
                take(&args, &mut index, option).map(|value| ngspice_sha256 = Some(value))
            }
            "--code-model-sha256" => {
                take(&args, &mut index, option).map(|value| code_model_sha256 = Some(value))
            }
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
    let result = match (
        execute,
        ngspice_sha256,
        code_model_sha256,
        request.code_model.as_ref(),
    ) {
        (true, Some(solver_sha), Some(model_sha), Some(_)) => run_rfm_with_ngspice_custody(
            &request,
            &RfmNgspiceCustody::new(
                NgspiceCustody::new(request.ngspice.clone(), solver_sha),
                model_sha,
            ),
        ),
        _ => run_rfm(&request),
    };
    match result {
        Ok(result) => {
            let payload = json!({
                "status": result.status,
                "response_samples": result.response_samples,
                "report": result.report,
            });
            match serde_json::to_string(&payload) {
                Ok(text) => println!("{text}"),
                Err(error) => {
                    eprintln!("run-rfm result serialization failed: {error}");
                    return ExitCode::from(2);
                }
            }
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
