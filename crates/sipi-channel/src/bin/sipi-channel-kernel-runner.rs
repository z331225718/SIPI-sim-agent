#![forbid(unsafe_code)]

//! External-comparator helper for the product-owned matched-kernel primitive.
//!
//! It accepts only a versioned binary spectrum record produced outside the
//! product and writes the resolved kernel record. It does not read Touchstone,
//! invoke an oracle, or provide a SIPI CLI route.

use std::{env, error::Error, fmt, fs, num::NonZeroUsize, path::Path};

use sipi_channel::{
    ChannelLimitsV1, MatchedTwoPortSpectrumV1, TwoPortS, resolve_matched_kernel_v1,
};
use sipi_types::{Complex64, Hertz, Ohms};

const INPUT_MAGIC: &[u8; 8] = b"SIPICHS1";
const OUTPUT_MAGIC: &[u8; 8] = b"SIPICHK1";
const MAX_ONE_SIDED_SAMPLES: usize = 4_096;
const INPUT_HEADER_BYTES: usize = 32;
const SAMPLE_BYTES: usize = 64;

#[derive(Debug)]
struct RunnerError(&'static str);

impl fmt::Display for RunnerError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.0)
    }
}
impl Error for RunnerError {}

fn read_u64(bytes: &[u8], offset: &mut usize) -> Result<u64, RunnerError> {
    let end = offset
        .checked_add(8)
        .ok_or(RunnerError("record offset overflow"))?;
    let value = bytes
        .get(*offset..end)
        .ok_or(RunnerError("truncated record"))?;
    *offset = end;
    Ok(u64::from_le_bytes(
        value
            .try_into()
            .map_err(|_| RunnerError("invalid integer field"))?,
    ))
}

fn read_f64(bytes: &[u8], offset: &mut usize) -> Result<f64, RunnerError> {
    Ok(f64::from_bits(read_u64(bytes, offset)?))
}

fn read_complex(bytes: &[u8], offset: &mut usize) -> Result<Complex64, RunnerError> {
    Complex64::try_new(read_f64(bytes, offset)?, read_f64(bytes, offset)?)
        .map_err(|_| RunnerError("non-finite complex field"))
}

fn parse_spectrum(bytes: &[u8]) -> Result<MatchedTwoPortSpectrumV1, RunnerError> {
    if bytes.get(..8) != Some(INPUT_MAGIC) {
        return Err(RunnerError("spectrum record magic mismatch"));
    }
    let mut offset = 8;
    let count = usize::try_from(read_u64(bytes, &mut offset)?)
        .map_err(|_| RunnerError("sample count is not representable"))?;
    if !(2..=MAX_ONE_SIDED_SAMPLES).contains(&count) {
        return Err(RunnerError("sample count is outside runner limits"));
    }
    let expected = INPUT_HEADER_BYTES
        .checked_add(
            count
                .checked_mul(SAMPLE_BYTES)
                .ok_or(RunnerError("record length overflow"))?,
        )
        .ok_or(RunnerError("record length overflow"))?;
    if bytes.len() != expected {
        return Err(RunnerError("spectrum record length mismatch"));
    }
    let impedance = Ohms::try_new(read_f64(bytes, &mut offset)?)
        .map_err(|_| RunnerError("non-finite impedance field"))?;
    let frequency_step = Hertz::try_new(read_f64(bytes, &mut offset)?)
        .map_err(|_| RunnerError("non-finite frequency step field"))?;
    let mut samples = Vec::with_capacity(count);
    for _ in 0..count {
        samples.push(TwoPortS {
            s11: read_complex(bytes, &mut offset)?,
            s12: read_complex(bytes, &mut offset)?,
            s21: read_complex(bytes, &mut offset)?,
            s22: read_complex(bytes, &mut offset)?,
        });
    }
    MatchedTwoPortSpectrumV1::try_new(impedance, frequency_step, samples)
        .map_err(|_| RunnerError("matched spectrum is invalid"))
}

fn encode_kernel(input: &MatchedTwoPortSpectrumV1) -> Result<Vec<u8>, RunnerError> {
    let kernel = resolve_matched_kernel_v1(
        input,
        ChannelLimitsV1::new(NonZeroUsize::new(MAX_ONE_SIDED_SAMPLES).unwrap()),
    )
    .map_err(|_| RunnerError("matched kernel resolution failed"))?;
    let count = kernel.gain().len();
    let mut record = Vec::with_capacity(
        24usize
            .checked_add(
                count
                    .checked_mul(8)
                    .ok_or(RunnerError("kernel record length overflow"))?,
            )
            .ok_or(RunnerError("kernel record length overflow"))?,
    );
    record.extend_from_slice(OUTPUT_MAGIC);
    record.extend_from_slice(&(count as u64).to_le_bytes());
    record.extend_from_slice(&kernel.sample_interval().get().to_le_bytes());
    for gain in kernel.gain() {
        record.extend_from_slice(&gain.get().to_le_bytes());
    }
    Ok(record)
}

fn run(input: &Path, output: &Path) -> Result<(), Box<dyn Error>> {
    let spectrum = parse_spectrum(&fs::read(input)?)?;
    fs::write(output, encode_kernel(&spectrum)?)?;
    Ok(())
}

fn main() -> Result<(), Box<dyn Error>> {
    let mut args = env::args_os();
    let _program = args.next();
    let input = args.next().ok_or(RunnerError("input path is required"))?;
    let output = args.next().ok_or(RunnerError("output path is required"))?;
    if args.next().is_some() {
        return Err(Box::new(RunnerError(
            "runner accepts exactly input and output paths",
        )));
    }
    run(Path::new(&input), Path::new(&output))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn record(samples: &[[f64; 8]]) -> Vec<u8> {
        let mut result = Vec::new();
        result.extend_from_slice(INPUT_MAGIC);
        result.extend_from_slice(&(samples.len() as u64).to_le_bytes());
        result.extend_from_slice(&50.0_f64.to_le_bytes());
        result.extend_from_slice(&1.0_f64.to_le_bytes());
        for sample in samples {
            for value in sample {
                result.extend_from_slice(&value.to_le_bytes());
            }
        }
        result
    }

    #[test]
    fn product_binary_record_resolves_an_identity_kernel() {
        let input = record(&[[0.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0]; 3]);
        let spectrum = parse_spectrum(&input).unwrap();
        let output = encode_kernel(&spectrum).unwrap();
        assert_eq!(&output[..8], OUTPUT_MAGIC);
        assert_eq!(u64::from_le_bytes(output[8..16].try_into().unwrap()), 4);
        assert_eq!(f64::from_le_bytes(output[24..32].try_into().unwrap()), 1.0);
    }

    #[test]
    fn malformed_binary_record_is_rejected_before_resolution() {
        assert!(parse_spectrum(b"not-a-spectrum").is_err());
        let mut input = record(&[[0.0, 0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0]; 2]);
        input.push(0);
        assert!(parse_spectrum(&input).is_err());
    }
}
