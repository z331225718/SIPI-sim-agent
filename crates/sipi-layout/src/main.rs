#![forbid(unsafe_code)]

use std::{env, path::Path, process};

use sipi_layout::{REPORT_SCHEMA, verify_stage, write_report_outside_stage};

fn main() {
    let arguments = env::args().skip(1).collect::<Vec<_>>();
    let (stage, policy, report) = match arguments.as_slice() {
        [stage_flag, stage, policy_flag, policy, report_flag, report]
            if stage_flag == "--stage"
                && policy_flag == "--policy"
                && report_flag == "--report" =>
        {
            (stage, policy, Some(report))
        }
        [stage_flag, stage, policy_flag, policy]
            if stage_flag == "--stage" && policy_flag == "--policy" =>
        {
            (stage, policy, None)
        }
        _ => {
            println!(
                "{{\"schema\":\"{REPORT_SCHEMA}\",\"status\":\"rejected\",\"reason\":\"usage\"}}"
            );
            process::exit(2);
        }
    };
    let policy_bytes = match std::fs::read(policy) {
        Ok(bytes) => bytes,
        Err(_) => {
            println!(
                "{{\"schema\":\"{REPORT_SCHEMA}\",\"status\":\"rejected\",\"reason\":\"policy_unavailable\"}}"
            );
            process::exit(2);
        }
    };
    let result = verify_stage(Path::new(stage), &policy_bytes);
    match result {
        Ok(layout) => {
            if let Some(report) = report
                && write_report_outside_stage(Path::new(stage), Path::new(report), &layout).is_err()
            {
                println!(
                    "{{\"schema\":\"{REPORT_SCHEMA}\",\"status\":\"rejected\",\"reason\":\"report_unavailable\"}}"
                );
                process::exit(2);
            }
            println!(
                "{}",
                serde_json::to_string(&layout).expect("layout report serializes")
            );
        }
        Err(error) => {
            println!(
                "{{\"schema\":\"{REPORT_SCHEMA}\",\"status\":\"rejected\",\"reason\":\"{}\"}}",
                error.code().as_str()
            );
            process::exit(2);
        }
    }
}
