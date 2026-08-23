use std::path::PathBuf;
use std::process::ExitCode;

use sipi_agent_spice_direct::{RunHspiceRequest, run_hspice};

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
            "usage: sipi-agent-spice-run-hspice DECK --backend native|ngspice|xyce|xyce-xdm --output-root DIR [--execute]"
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
    let mut backend = None;
    let mut output_root = None;
    let mut execute = false;
    let mut native_engine = None;
    let mut rfm = None;
    let mut rfm_subckt = "rfm_direct".to_owned();
    let mut dotnet = "dotnet".to_owned();
    let mut index = 1;
    while index < args.len() {
        let option = &args[index];
        let result = match option.as_str() {
            "--backend" => take(&args, &mut index, option).map(|value| backend = Some(value)),
            "--output-root" => take(&args, &mut index, option)
                .map(|value| output_root = Some(PathBuf::from(value))),
            "--native-engine" => take(&args, &mut index, option)
                .map(|value| native_engine = Some(PathBuf::from(value))),
            "--rfm" => {
                take(&args, &mut index, option).map(|value| rfm = Some(PathBuf::from(value)))
            }
            "--rfm-subckt" => take(&args, &mut index, option).map(|value| rfm_subckt = value),
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
    let backend = match backend {
        Some(value) => value,
        None => {
            eprintln!("--backend is required and is never defaulted");
            return ExitCode::from(2);
        }
    };
    let output_root = match output_root {
        Some(value) => value,
        None => {
            eprintln!("--output-root is required");
            return ExitCode::from(2);
        }
    };
    let mut request = match RunHspiceRequest::new(&backend, output_root, execute) {
        Ok(value) => value,
        Err(error) => {
            eprintln!("run-hspice argument error: {error}");
            return ExitCode::from(2);
        }
    };
    if let Some(path) = native_engine {
        request = request.with_native_engine(path);
    }
    if let Some(path) = rfm {
        request = request.with_rfm(path, rfm_subckt);
    }
    request = request.with_dotnet(dotnet);
    match run_hspice(deck, request) {
        Ok(result) => {
            println!(
                "{{\"status\":\"{}\",\"case_count\":{},\"output_root\":\"{}\"}}",
                result.status.as_str(),
                result.case_count,
                result.output_root.display()
            );
            if result.status == sipi_agent_spice_direct::PreparationStatus::Blocked {
                ExitCode::from(1)
            } else {
                ExitCode::SUCCESS
            }
        }
        Err(error) => {
            eprintln!("run-hspice failed: {error}");
            ExitCode::from(2)
        }
    }
}
