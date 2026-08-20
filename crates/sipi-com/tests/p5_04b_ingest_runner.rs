//! External-only ingest cross-check runner (P5-04b).
//!
//! Reads one authorized S4P with the product four-port parser, applies
//! the file-to-internal port order and mixed-mode transform, and reports
//! the sdd21 value at the target frequency plus a hash of the full
//! series. Ignored by default; external-custody tooling.

use std::path::PathBuf;

use sha2::{Digest, Sha256};
use sipi_channel::FourPortS;
use sipi_com::{apply_internal_port_order_v1, sdd21_v1, FourPortSMatrixV1};
use sipi_touchstone::{
    selected_four_port_v1::{parse_selected_four_port_hz_s_ri_50_v2, ParsedSelectedFourPortV1},
    TouchstoneParseLimitsV1,
};
use sipi_types::Complex64;

fn cm(real: f64, imaginary: f64) -> Complex64 {
    Complex64::try_new(real, imaginary).expect("complex")
}

fn to_matrix(four: FourPortS) -> FourPortSMatrixV1 {
    let mut matrix = [[cm(0.0, 0.0); 4]; 4];
    for output in 0..4 {
        for incident in 0..4 {
            matrix[output][incident] = four.at(output, incident).expect("port");
        }
    }
    matrix
}

fn main() {
    let mut s4p = None;
    let mut target_hz = 2.656e10;
    let mut report = None;
    let mut args = std::env::args().skip(1);
    while let Some(argument) = args.next() {
        let mut value = || args.next().expect("argument value");
        match argument.as_str() {
            "--s4p" => s4p = Some(PathBuf::from(value())),
            "--target-hz" => target_hz = value().parse().expect("target"),
            "--report" => report = Some(PathBuf::from(value())),
            other => panic!("unknown argument: {other}"),
        }
    }
    let Some(s4p) = s4p else {
        println!("usage: p5_04b_ingest_runner --s4p <path> [--target-hz <hz>] [--report <path>]");
        return;
    };
    let bytes = std::fs::read(&s4p).expect("read");
    let limits = TouchstoneParseLimitsV1::new(
        std::num::NonZeroUsize::new(16 * 1024 * 1024).expect("limit"),
        std::num::NonZeroUsize::new(16 * 1024).expect("limit"),
        std::num::NonZeroUsize::new(16384).expect("limit"),
    );
    let parsed: ParsedSelectedFourPortV1 =
        parse_selected_four_port_hz_s_ri_50_v2(&bytes, limits).expect("parse");
    let mut series_hash = Sha256::new();
    let mut target = None;
    for row in parsed.rows() {
        let frequency = row.frequency_hz();
        let sdd21 = sdd21_v1(&apply_internal_port_order_v1(&to_matrix(row.matrix())));
        series_hash.update(sdd21.real().to_le_bytes());
        series_hash.update(sdd21.imaginary().to_le_bytes());
        if (frequency - target_hz).abs() < 1e-6 {
            let magnitude_db = 20.0 * (sdd21.real().hypot(sdd21.imaginary())).log10();
            target = Some(serde_json::json!({
                "frequency_hz": frequency,
                "real": sdd21.real(),
                "imag": sdd21.imaginary(),
                "magnitude_db": magnitude_db,
            }));
        }
    }
    let digest = format!("{:x}", series_hash.finalize());
    let report_json = serde_json::json!({
        "rows": parsed.rows().len(),
        "series_sha256": digest,
        "target": target,
    });
    if let Some(path) = report {
        std::fs::write(path, serde_json::to_string_pretty(&report_json).expect("json"))
            .expect("write");
    } else {
        println!("{}", serde_json::to_string_pretty(&report_json).expect("json"));
    }
}
