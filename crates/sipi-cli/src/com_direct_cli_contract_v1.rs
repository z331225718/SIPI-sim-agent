//! Preparation-only bounded argv contract for the future R4.80 COM route.
//!
//! This module deliberately has no dispatcher registration.  It freezes the
//! caller-owned argument surface before the route is enabled on an immutable
//! product candidate; `com run` remains unavailable in this preparation stage.

use std::path::PathBuf;

pub(crate) const COM_R480_ARGV_SCHEMA_V1: &str = "sipi.com.r480.argv.v1";
pub(crate) const COM_R480_CLI_RECEIPT_SCHEMA_V1: &str = "sipi.com.r480-cli-receipt.v1";
pub(crate) const MAX_COM_R480_PATH_BYTES_V1: usize = 4_096;
pub(crate) const MAX_COM_R480_CROSSTALK_CHANNELS_V1: usize = 64;

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct ComR480ArgvRequestV1 {
    pub config: PathBuf,
    pub thru: PathBuf,
    pub fext: Vec<PathBuf>,
    pub next: Vec<PathBuf>,
    pub calibration_noise: Option<PathBuf>,
    pub output_dir: PathBuf,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum ComR480ArgvErrorV1 {
    MissingRequired,
    MissingValue,
    DuplicateSingleton,
    UnknownOption,
    UnsafePath,
    TooManyCrosstalkChannels,
}

impl ComR480ArgvErrorV1 {
    pub(crate) const fn diagnostic_code(self) -> &'static str {
        match self {
            Self::MissingRequired
            | Self::MissingValue
            | Self::DuplicateSingleton
            | Self::UnknownOption => "usage",
            Self::UnsafePath | Self::TooManyCrosstalkChannels => "invalid_input",
        }
    }
}

/// Parse only the arguments after `sipi com run`.
///
/// Profile, reader, fix IDs, overrides, overwrite, legacy output, stdin, and
/// URLs are intentionally absent from this contract.  Filesystem custody is
/// performed later by the direct-port execution boundary, immediately before
/// it reads or creates anything.
pub(crate) fn parse_com_r480_argv_v1(
    arguments: &[String],
) -> Result<ComR480ArgvRequestV1, ComR480ArgvErrorV1> {
    let mut config = None;
    let mut thru = None;
    let mut output_dir = None;
    let mut calibration_noise = None;
    let mut fext = Vec::new();
    let mut next = Vec::new();
    let mut index = 0usize;

    while index < arguments.len() {
        let option = arguments[index].as_str();
        let value = arguments
            .get(index + 1)
            .ok_or(ComR480ArgvErrorV1::MissingValue)?;
        if !option.starts_with("--") || value.starts_with("--") {
            return Err(ComR480ArgvErrorV1::MissingValue);
        }
        let path = parse_local_path_v1(value)?;
        match option {
            "--config" => set_singleton_v1(&mut config, path)?,
            "--thru" => set_singleton_v1(&mut thru, path)?,
            "--output-dir" => set_singleton_v1(&mut output_dir, path)?,
            "--calibration-noise" => set_singleton_v1(&mut calibration_noise, path)?,
            "--fext" => fext.push(path),
            "--next" => next.push(path),
            _ => return Err(ComR480ArgvErrorV1::UnknownOption),
        }
        if fext.len().saturating_add(next.len()) > MAX_COM_R480_CROSSTALK_CHANNELS_V1 {
            return Err(ComR480ArgvErrorV1::TooManyCrosstalkChannels);
        }
        index += 2;
    }

    Ok(ComR480ArgvRequestV1 {
        config: config.ok_or(ComR480ArgvErrorV1::MissingRequired)?,
        thru: thru.ok_or(ComR480ArgvErrorV1::MissingRequired)?,
        fext,
        next,
        calibration_noise,
        output_dir: output_dir.ok_or(ComR480ArgvErrorV1::MissingRequired)?,
    })
}

fn set_singleton_v1(slot: &mut Option<PathBuf>, value: PathBuf) -> Result<(), ComR480ArgvErrorV1> {
    if slot.replace(value).is_some() {
        return Err(ComR480ArgvErrorV1::DuplicateSingleton);
    }
    Ok(())
}

fn parse_local_path_v1(value: &str) -> Result<PathBuf, ComR480ArgvErrorV1> {
    if value.is_empty()
        || value.len() > MAX_COM_R480_PATH_BYTES_V1
        || value.contains('\0')
        || value.contains("://")
    {
        return Err(ComR480ArgvErrorV1::UnsafePath);
    }
    Ok(PathBuf::from(value))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn args(values: &[&str]) -> Vec<String> {
        values.iter().map(|value| (*value).to_owned()).collect()
    }

    #[test]
    fn bounded_contract_accepts_only_fixed_r480_file_surface() {
        let request = parse_com_r480_argv_v1(&args(&[
            "--config",
            "config.xlsx",
            "--thru",
            "thru.s4p",
            "--fext",
            "fext-0.s4p",
            "--next",
            "next-0.s4p",
            "--calibration-noise",
            "noise.json",
            "--output-dir",
            "new-output",
        ]))
        .expect("bounded argv request");
        assert_eq!(request.config, PathBuf::from("config.xlsx"));
        assert_eq!(request.thru, PathBuf::from("thru.s4p"));
        assert_eq!(request.fext, vec![PathBuf::from("fext-0.s4p")]);
        assert_eq!(request.next, vec![PathBuf::from("next-0.s4p")]);
        assert_eq!(request.calibration_noise, Some(PathBuf::from("noise.json")));
        assert_eq!(request.output_dir, PathBuf::from("new-output"));
        assert_eq!(COM_R480_ARGV_SCHEMA_V1, "sipi.com.r480.argv.v1");
        assert_eq!(
            COM_R480_CLI_RECEIPT_SCHEMA_V1,
            "sipi.com.r480-cli-receipt.v1"
        );
    }

    #[test]
    fn singleton_and_unknown_options_fail_closed() {
        for values in [
            args(&[
                "--config",
                "a.xlsx",
                "--config",
                "b.xlsx",
                "--thru",
                "thru.s4p",
                "--output-dir",
                "out",
            ]),
            args(&[
                "--config",
                "a.xlsx",
                "--thru",
                "thru.s4p",
                "--output-dir",
                "out",
                "--override",
                "X=1",
            ]),
            args(&["--config", "a.xlsx", "--thru", "thru.s4p", "--output-dir"]),
        ] {
            assert!(parse_com_r480_argv_v1(&values).is_err());
        }
    }

    #[test]
    fn remote_paths_and_excess_channels_are_rejected() {
        let remote = args(&[
            "--config",
            "https://example.invalid/config.xlsx",
            "--thru",
            "thru.s4p",
            "--output-dir",
            "out",
        ]);
        assert_eq!(
            parse_com_r480_argv_v1(&remote),
            Err(ComR480ArgvErrorV1::UnsafePath)
        );

        let mut values = args(&[
            "--config",
            "config.xlsx",
            "--thru",
            "thru.s4p",
            "--output-dir",
            "out",
        ]);
        for index in 0..=MAX_COM_R480_CROSSTALK_CHANNELS_V1 {
            values.extend(args(&["--fext", &format!("fext-{index}.s4p")]));
        }
        assert_eq!(
            parse_com_r480_argv_v1(&values),
            Err(ComR480ArgvErrorV1::TooManyCrosstalkChannels)
        );
    }

    #[test]
    fn errors_map_to_machine_diagnostics() {
        assert_eq!(ComR480ArgvErrorV1::UnknownOption.diagnostic_code(), "usage");
        assert_eq!(
            ComR480ArgvErrorV1::UnsafePath.diagnostic_code(),
            "invalid_input"
        );
    }
}
