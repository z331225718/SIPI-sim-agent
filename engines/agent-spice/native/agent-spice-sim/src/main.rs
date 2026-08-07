mod compatibility;
mod error;
mod expression;
mod logging;
mod netlist;
mod output;
mod result;
mod rfm;
mod simulator;
mod sparse;

use std::collections::{BTreeSet, HashMap};
use std::env;
use std::fs::File;
use std::io::{BufWriter, Write};
use std::path::PathBuf;
use std::time::Instant;

use faer::c64;

use error::{Error, Result};

#[derive(Clone)]
struct RcBranch {
    positive: String,
    negative: String,
    value: f64,
    is_capacitor: bool,
}

/// A two-terminal linear RC CPM.  It deliberately supports only passive R/C
/// elements; nonlinear/current-source parts of a CPM belong in the waveform,
/// not its small-signal load.
#[derive(Clone)]
struct RcShunt {
    port: usize,
    positive_terminal: String,
    negative_terminal: String,
    branches: Vec<RcBranch>,
    source: PathBuf,
}

impl RcShunt {
    fn parse(port: usize, source: PathBuf) -> Result<Self> {
        let text = std::fs::read_to_string(&source)?;
        let mut records = Vec::<String>::new();
        for raw in text.lines() {
            let line = raw.split(';').next().unwrap_or("").trim();
            if line.is_empty() || line.starts_with('*') {
                continue;
            }
            if let Some(continuation) = line.strip_prefix('+') {
                let previous = records.last_mut().ok_or_else(|| {
                    Error::Parse(format!("{}: orphan SPICE continuation", source.display()))
                })?;
                previous.push(' ');
                previous.push_str(continuation.trim());
            } else {
                records.push(line.to_string());
            }
        }
        let subckts = records
            .iter()
            .filter(|line| line.to_ascii_lowercase().starts_with(".subckt"))
            .collect::<Vec<_>>();
        if subckts.len() != 1 {
            return Err(Error::Parse(format!(
                "{}: RC load must contain exactly one .SUBCKT (use a small wrapper deck for vendor includes)",
                source.display()
            )));
        }
        let subckt = subckts[0];
        let terminals = subckt.split_whitespace().collect::<Vec<_>>();
        if terminals.len() < 4 {
            return Err(Error::Parse(format!(
                "{}: RC load .SUBCKT needs two terminals",
                source.display()
            )));
        }
        let positive_terminal = terminals[2].to_string();
        let negative_terminal = terminals[3].to_string();
        let mut branches = Vec::new();
        for line in records {
            if line.starts_with('.') {
                continue;
            }
            let fields = line.split_whitespace().collect::<Vec<_>>();
            if fields.len() < 4 {
                return Err(Error::Parse(format!(
                    "{}: malformed RC load element '{line}'",
                    source.display()
                )));
            }
            let first = fields[0]
                .as_bytes()
                .first()
                .copied()
                .unwrap_or_default()
                .to_ascii_lowercase();
            let is_capacitor = match first {
                b'r' => false,
                b'c' => true,
                _ => {
                    return Err(Error::Parse(format!(
                        "{}: RC load supports only R/C elements, found '{line}'",
                        source.display()
                    )));
                }
            };
            let value = spice_number(fields[3]).ok_or_else(|| {
                Error::Parse(format!(
                    "{}: invalid RC load value '{}'",
                    source.display(),
                    fields[3]
                ))
            })?;
            if !value.is_finite() || value <= 0.0 {
                return Err(Error::Parse(format!(
                    "{}: RC load value must be positive",
                    source.display()
                )));
            }
            branches.push(RcBranch {
                positive: fields[1].to_string(),
                negative: fields[2].to_string(),
                value,
                is_capacitor,
            });
        }
        if branches.is_empty() {
            return Err(Error::Parse(format!(
                "{}: RC load contains no R/C elements",
                source.display()
            )));
        }
        Ok(Self {
            port,
            positive_terminal,
            negative_terminal,
            branches,
            source,
        })
    }

    fn admittance(&self, s: c64) -> Result<c64> {
        let mut names = BTreeSet::new();
        for branch in &self.branches {
            if branch.positive != self.negative_terminal {
                names.insert(branch.positive.clone());
            }
            if branch.negative != self.negative_terminal {
                names.insert(branch.negative.clone());
            }
        }
        let mut nodes = vec![self.positive_terminal.clone()];
        nodes.extend(
            names
                .into_iter()
                .filter(|node| node != &self.positive_terminal),
        );
        let indices = nodes
            .iter()
            .enumerate()
            .map(|(index, node)| (node.as_str(), index))
            .collect::<HashMap<_, _>>();
        let positive = *indices
            .get(self.positive_terminal.as_str())
            .ok_or_else(|| {
                Error::Parse(format!(
                    "{}: positive terminal is disconnected",
                    self.source.display()
                ))
            })?;
        if positive != 0 {
            return Err(Error::Parse(format!(
                "{}: RC load terminal ordering failed",
                self.source.display()
            )));
        }
        let size = nodes.len();
        let mut matrix = vec![c64::new(0.0, 0.0); size * size];
        for branch in &self.branches {
            let admittance = if branch.is_capacitor {
                s * branch.value
            } else {
                c64::new(1.0 / branch.value, 0.0)
            };
            let positive = indices.get(branch.positive.as_str()).copied();
            let negative = indices.get(branch.negative.as_str()).copied();
            if let Some(index) = positive {
                matrix[index * size + index] += admittance;
            }
            if let Some(index) = negative {
                matrix[index * size + index] += admittance;
            }
            if let (Some(row), Some(column)) = (positive, negative) {
                matrix[row * size + column] -= admittance;
                matrix[column * size + row] -= admittance;
            }
        }
        if size == 1 {
            return Ok(matrix[0]);
        }
        let internal_size = size - 1;
        let mut internal = Vec::with_capacity(internal_size * internal_size);
        for row in 0..internal_size {
            for column in 0..internal_size {
                internal.push(matrix[(row + 1) * size + column + 1]);
            }
        }
        let inverse = rfm::invert_complex(&internal, internal_size)?;
        let mut correction = c64::new(0.0, 0.0);
        for left in 0..internal_size {
            for right in 0..internal_size {
                correction += matrix[left + 1]
                    * inverse[left * internal_size + right]
                    * matrix[(right + 1) * size];
            }
        }
        Ok(matrix[0] - correction)
    }
}

#[derive(Clone)]
struct ResponseLoads {
    shorted_ports: Vec<usize>,
    conductance: Vec<f64>,
    rc_shunts: Vec<RcShunt>,
}

impl ResponseLoads {
    fn empty(nports: usize) -> Self {
        Self {
            shorted_ports: Vec::new(),
            conductance: vec![0.0; nports],
            rc_shunts: Vec::new(),
        }
    }

    fn admittances(&self, s: c64) -> Result<Vec<c64>> {
        let mut result = self
            .conductance
            .iter()
            .map(|value| c64::new(*value, 0.0))
            .collect::<Vec<_>>();
        for shunt in &self.rc_shunts {
            result[shunt.port] += shunt.admittance(s)?;
        }
        Ok(result)
    }
}

fn log_rfm_storage(name: &str, model: &rfm::RfmModel) {
    let stats = model.storage_stats();
    let compression = stats.legacy_dense_state_scalars as f64 / stats.state_scalars.max(1) as f64;
    let history = if stats.dense_history_bytes == 0 {
        "sparse".to_string()
    } else {
        format!(
            "dense/{:.1} MiB",
            stats.dense_history_bytes as f64 / (1024.0 * 1024.0)
        )
    };
    logging::line(format_args!(
        "[agent-spice-sim] RFM {name}: ports={} unique-poles={} modes={} state-scalars={} terms={} state-compression={compression:.1}x history={history} legacy-history={:.1} MiB",
        model.nports,
        stats.unique_poles,
        stats.dynamic_modes,
        stats.state_scalars,
        stats.response_terms,
        stats.legacy_dense_history_bytes as f64 / (1024.0 * 1024.0),
    ));
}

fn log_pwl_storage(deck: &netlist::Deck) {
    let mut sources = 0usize;
    let mut points = 0usize;
    let mut hard_breakpoints = 0usize;
    let mut repeating = 0usize;
    for element in &deck.elements {
        let source = match element {
            netlist::Element::Voltage { source, .. } | netlist::Element::Current { source, .. } => {
                source
            }
            _ => continue,
        };
        if let Some(netlist::Waveform::Pwl {
            points: source_points,
            hard_breakpoints: source_breakpoints,
            repeat_from,
        }) = &source.waveform
        {
            sources += 1;
            points += source_points.len();
            hard_breakpoints += source_breakpoints.len();
            repeating += usize::from(repeat_from.is_some());
        }
    }
    if sources > 0 {
        logging::line(format_args!(
            "[agent-spice-sim] PWL sources={sources} points={points} hard-breakpoints={hard_breakpoints} repeating={repeating} lookup=binary"
        ));
    }
}

fn main() {
    if let Err(error) = run() {
        logging::line(format_args!("agent-spice-sim: {error}"));
        eprintln!("agent-spice-sim: {error}");
        std::process::exit(1);
    }
}

fn run() -> Result<()> {
    let started = Instant::now();
    let mut arguments = env::args_os().skip(1);
    let first = arguments.next().ok_or_else(|| Error::Usage(usage()))?;
    if first == "build-info" {
        return run_build_info(arguments);
    }
    if first == "rfm-response" {
        return run_rfm_response(arguments);
    }
    let deck = PathBuf::from(first);
    let mut rfm_path = None;
    let mut rfm_subcircuit = "rfm_direct".to_string();
    let mut output_json = None;
    let mut waveform_csv = None;
    let mut audit_json = None;
    let mut log_path = None;
    while let Some(argument) = arguments.next() {
        if argument == "--rfm" {
            rfm_path = Some(PathBuf::from(
                arguments.next().ok_or_else(|| Error::Usage(usage()))?,
            ));
        } else if argument == "--rfm-subckt" {
            rfm_subcircuit = arguments
                .next()
                .ok_or_else(|| Error::Usage(usage()))?
                .into_string()
                .map_err(|_| Error::Usage("RFM subcircuit name must be valid Unicode".into()))?;
        } else if argument == "--output-json" {
            output_json = Some(PathBuf::from(
                arguments.next().ok_or_else(|| Error::Usage(usage()))?,
            ));
        } else if argument == "--waveform-csv" {
            waveform_csv = Some(PathBuf::from(
                arguments.next().ok_or_else(|| Error::Usage(usage()))?,
            ));
        } else if argument == "--audit-json" {
            audit_json = Some(PathBuf::from(
                arguments.next().ok_or_else(|| Error::Usage(usage()))?,
            ));
        } else if argument == "--log" {
            log_path = Some(PathBuf::from(
                arguments.next().ok_or_else(|| Error::Usage(usage()))?,
            ));
        } else {
            return Err(Error::Usage(usage()));
        }
    }
    if !deck.is_file() {
        return Err(Error::InvalidDeck(format!(
            "deck does not exist: {}",
            deck.display()
        )));
    }
    let deck = deck.canonicalize()?;
    let deck_directory = deck.parent().ok_or_else(|| {
        Error::InvalidDeck(format!("deck has no parent directory: {}", deck.display()))
    })?;
    std::env::set_current_dir(deck_directory).map_err(|error| {
        Error::InvalidDeck(format!(
            "failed to set simulation working directory to '{}': {error}",
            deck_directory.display()
        ))
    })?;
    if rfm_path.as_ref().is_some_and(|path| !path.is_file()) {
        return Err(Error::InvalidDeck(format!(
            "RFM model does not exist: {}",
            rfm_path.as_ref().expect("RFM path was checked").display()
        )));
    }
    if let Some(audit_json) = audit_json {
        if output_json.is_some() || waveform_csv.is_some() {
            return Err(Error::Usage(
                "--audit-json cannot be combined with simulation outputs".into(),
            ));
        }
        let report = compatibility::audit_file(&deck)?;
        let writer = BufWriter::new(File::create(audit_json)?);
        serde_json::to_writer_pretty(writer, &report)?;
        println!(
            "{}",
            serde_json::json!({
                "ok": true,
                "compatible": report.issue_count() == 0,
                "issues": report.issue_count(),
                "scannedFiles": report.scanned_file_count(),
            })
        );
        return Ok(());
    }

    let log_path = log_path.unwrap_or_else(|| {
        waveform_csv.as_ref().or(output_json.as_ref()).map_or_else(
            || deck.with_extension("log"),
            |path| path.with_extension("log"),
        )
    });
    logging::initialize(&log_path)?;
    logging::line(format_args!(
        "[agent-spice-sim] log file: {}",
        log_path.display()
    ));
    logging::line(format_args!(
        "[agent-spice-sim] loading deck: {}",
        deck.display()
    ));
    logging::line(format_args!(
        "[agent-spice-sim] working directory: {}",
        deck_directory.display()
    ));
    let load_started = Instant::now();
    let rfm = rfm_path
        .as_deref()
        .map(rfm::RfmModel::parse_file)
        .transpose()?;
    let binding = rfm
        .as_ref()
        .map(|model| (rfm_subcircuit.as_str(), model.nports));
    let deck = netlist::Deck::parse_file(&deck, binding)?;
    if let Some(model) = rfm.as_ref() {
        log_rfm_storage("<command-line>", model);
    }
    let mut model_names: Vec<_> = deck.rfm_models.keys().collect();
    model_names.sort();
    for name in model_names {
        log_rfm_storage(name, &deck.rfm_models[name]);
    }
    log_pwl_storage(&deck);
    logging::line(format_args!(
        "[agent-spice-sim] parsed: {} element(s), {} node(s), {} analysis job(s) in {:.3}s",
        deck.elements.len(),
        deck.nodes.len(),
        deck.analyses.len(),
        load_started.elapsed().as_secs_f64()
    ));
    if let Some(path) = waveform_csv.as_deref() {
        logging::line(format_args!(
            "[agent-spice-sim] streaming waveform CSV: {}",
            path.display()
        ));
    }
    let mut observer = output::RuntimeObserver::new(waveform_csv.as_deref(), &deck.analyses)?;
    let retain_points =
        output_json.is_some() || waveform_csv.is_none() || !deck.measurements.is_empty();
    if waveform_csv.is_some() && !retain_points {
        logging::line(format_args!(
            "[agent-spice-sim] streaming mode: full waveform points are not retained"
        ));
    }
    let result = simulator::run_with_observer(&deck, rfm.as_ref(), &mut observer, retain_points)?;
    let waveform_rows = observer.finish()?;
    for export in &deck.lin_exports {
        let lin_started = Instant::now();
        let output = simulator::export_lin_touchstone(&deck, rfm.as_ref(), export)?;
        logging::line(format_args!(
            "[agent-spice-sim] wrote .lin Touchstone: {} in {:.3}s",
            output.display(),
            lin_started.elapsed().as_secs_f64()
        ));
        eprintln!(
            "[agent-spice-sim] LIN Touchstone exported: {}",
            output.display()
        );
    }
    if let Some(output_json) = output_json.as_deref() {
        let json_started = Instant::now();
        output::write_json(&result, output_json)?;
        logging::line(format_args!(
            "[agent-spice-sim] wrote final JSON: {} in {:.3}s",
            output_json.display(),
            json_started.elapsed().as_secs_f64()
        ));
        println!(r#"{{"ok":true,"waveformRows":{waveform_rows}}}"#);
    } else if waveform_csv.is_some() {
        println!(
            "{}",
            serde_json::json!({
                "ok": true,
                "waveformRows": waveform_rows,
                "measurements": result.measurements,
                "statistics": result.statistics,
            })
        );
    } else {
        println!("{}", serde_json::to_string(&result)?);
    }
    logging::line(format_args!(
        "[agent-spice-sim] simulation completed in {:.3}s",
        started.elapsed().as_secs_f64()
    ));
    Ok(())
}

fn build_info() -> serde_json::Value {
    let git_dirty = match env!("AGENT_SPICE_GIT_DIRTY") {
        "true" => Some(true),
        "false" => Some(false),
        _ => None,
    };
    serde_json::json!({
        "schema": "agent-spice.build-info.v1",
        "crateName": env!("CARGO_PKG_NAME"),
        "crateVersion": env!("CARGO_PKG_VERSION"),
        "gitRevision": env!("AGENT_SPICE_GIT_REVISION"),
        "gitDirty": git_dirty,
        "target": env!("AGENT_SPICE_TARGET"),
        "profile": env!("AGENT_SPICE_PROFILE"),
    })
}

fn run_build_info(mut arguments: impl Iterator<Item = std::ffi::OsString>) -> Result<()> {
    if let Some(argument) = arguments.next() {
        if argument != "--json" || arguments.next().is_some() {
            return Err(Error::Usage("agent-spice-sim build-info [--json]".into()));
        }
    }
    println!(
        "{}",
        serde_json::to_string(&build_info()).expect("build-info is serializable")
    );
    Ok(())
}

fn run_rfm_response(mut arguments: impl Iterator<Item = std::ffi::OsString>) -> Result<()> {
    let rfm_path = arguments
        .next()
        .map(PathBuf::from)
        .ok_or_else(|| Error::Usage(rfm_response_usage()))?;
    let mut fft_size = None;
    let mut dt = None;
    let mut input_ports = None;
    let mut output_ports = None;
    let mut response_bin = None;
    let mut metadata_json = None;
    let mut threads = 1usize;
    let mut shunt_resistances = Vec::new();
    let mut rc_loads = Vec::new();
    while let Some(argument) = arguments.next() {
        if argument == "--fft-size" {
            fft_size = Some(parse_positive_usize(arguments.next(), "--fft-size")?);
        } else if argument == "--dt" {
            dt = Some(parse_positive_f64(arguments.next(), "--dt")?);
        } else if argument == "--input-ports" {
            input_ports = Some(
                arguments
                    .next()
                    .ok_or_else(|| Error::Usage(rfm_response_usage()))?,
            );
        } else if argument == "--output-ports" {
            output_ports = Some(
                arguments
                    .next()
                    .ok_or_else(|| Error::Usage(rfm_response_usage()))?,
            );
        } else if argument == "--response-bin" {
            response_bin = Some(PathBuf::from(
                arguments
                    .next()
                    .ok_or_else(|| Error::Usage(rfm_response_usage()))?,
            ));
        } else if argument == "--metadata-json" {
            metadata_json = Some(PathBuf::from(
                arguments
                    .next()
                    .ok_or_else(|| Error::Usage(rfm_response_usage()))?,
            ));
        } else if argument == "--threads" {
            threads = parse_positive_usize(arguments.next(), "--threads")?;
        } else if argument == "--shunt-resistance" {
            shunt_resistances.push(
                arguments
                    .next()
                    .ok_or_else(|| Error::Usage(rfm_response_usage()))?,
            );
        } else if argument == "--rc-load" {
            rc_loads.push(
                arguments
                    .next()
                    .ok_or_else(|| Error::Usage(rfm_response_usage()))?,
            );
        } else {
            return Err(Error::Usage(rfm_response_usage()));
        }
    }
    let fft_size = fft_size.ok_or_else(|| Error::Usage(rfm_response_usage()))?;
    if fft_size < 2 {
        return Err(Error::Usage("--fft-size must be at least 2".into()));
    }
    let dt = dt.ok_or_else(|| Error::Usage(rfm_response_usage()))?;
    let response_bin = response_bin.ok_or_else(|| Error::Usage(rfm_response_usage()))?;
    let metadata_json = metadata_json.ok_or_else(|| Error::Usage(rfm_response_usage()))?;
    let model = rfm::RfmModel::parse_file(&rfm_path)?;
    let inputs = parse_ports(input_ports, model.nports)?;
    let outputs = parse_ports(output_ports, model.nports)?;
    let loads = parse_response_loads(model.nports, shunt_resistances, rc_loads)?;
    let bins = fft_size / 2 + 1;
    let values_per_bin = inputs.len() * outputs.len();
    let started = Instant::now();
    let values = evaluate_response_grid(&model, fft_size, dt, &inputs, &outputs, &loads, threads)?;
    let mut writer = BufWriter::new(File::create(&response_bin)?);
    for value in values {
        writer.write_all(&value.re.to_le_bytes())?;
        writer.write_all(&value.im.to_le_bytes())?;
    }
    writer.flush()?;
    let metadata = serde_json::json!({
        "schema": "agent-spice.rfm-response.v1",
        "rfmName": rfm_path.file_name().and_then(|name| name.to_str()).unwrap_or("unknown"),
        "producer": build_info(),
        "fftSize": fft_size,
        "dtS": dt,
        "frequencyBins": bins,
        "inputPorts": inputs.iter().map(|port| port + 1).collect::<Vec<_>>(),
        "outputPorts": outputs.iter().map(|port| port + 1).collect::<Vec<_>>(),
        "shortedPorts": loads.shorted_ports.iter().map(|port| port + 1).collect::<Vec<_>>(),
        "rcLoads": loads.rc_shunts.iter().map(|load| serde_json::json!({
            "port": load.port + 1,
            "sourceName": load
                .source
                .file_name()
                .and_then(|name| name.to_str())
                .unwrap_or("unknown"),
            "branches": load.branches.len(),
        })).collect::<Vec<_>>(),
        "layout": "frequency-major,output-major,input-major,re-im,f64-le",
        "threads": threads,
        "seconds": started.elapsed().as_secs_f64(),
    });
    serde_json::to_writer_pretty(BufWriter::new(File::create(&metadata_json)?), &metadata)?;
    println!(
        "{}",
        serde_json::json!({
            "ok": true,
            "frequencyBins": bins,
            "responseValues": bins * values_per_bin,
            "seconds": started.elapsed().as_secs_f64(),
        })
    );
    Ok(())
}

fn evaluate_response_grid(
    model: &rfm::RfmModel,
    fft_size: usize,
    dt: f64,
    inputs: &[usize],
    outputs: &[usize],
    loads: &ResponseLoads,
    threads: usize,
) -> Result<Vec<c64>> {
    let bins = fft_size / 2 + 1;
    let values_per_bin = inputs.len() * outputs.len();
    let workers = threads.min(bins).max(1);
    if workers == 1 {
        let mut values = Vec::with_capacity(bins * values_per_bin);
        for bin in 0..bins {
            let frequency = bin as f64 / (fft_size as f64 * dt);
            let s = c64::new(0.0, 2.0 * std::f64::consts::PI * frequency);
            values.extend(model.loaded_impedance_response(
                s,
                outputs,
                inputs,
                &loads.shorted_ports,
                &loads.admittances(s)?,
            )?);
        }
        return Ok(values);
    }
    let chunk = bins.div_ceil(workers);
    let mut pieces = Vec::new();
    std::thread::scope(|scope| -> Result<()> {
        let mut handles = Vec::new();
        for start in (0..bins).step_by(chunk) {
            let stop = (start + chunk).min(bins);
            handles.push(scope.spawn(move || -> Result<(usize, Vec<c64>)> {
                let mut values = Vec::with_capacity((stop - start) * values_per_bin);
                for bin in start..stop {
                    let frequency = bin as f64 / (fft_size as f64 * dt);
                    let s = c64::new(0.0, 2.0 * std::f64::consts::PI * frequency);
                    values.extend(model.loaded_impedance_response(
                        s,
                        outputs,
                        inputs,
                        &loads.shorted_ports,
                        &loads.admittances(s)?,
                    )?);
                }
                Ok((start, values))
            }));
        }
        for handle in handles {
            pieces.push(
                handle
                    .join()
                    .map_err(|_| Error::Sparse("RFM response worker panicked".into()))??,
            );
        }
        Ok(())
    })?;
    pieces.sort_by_key(|(start, _)| *start);
    Ok(pieces.into_iter().flat_map(|(_, values)| values).collect())
}

fn parse_positive_usize(value: Option<std::ffi::OsString>, name: &str) -> Result<usize> {
    let value = value.ok_or_else(|| Error::Usage(rfm_response_usage()))?;
    let parsed = value
        .to_string_lossy()
        .parse::<usize>()
        .map_err(|_| Error::Usage(format!("{name} must be a positive integer")))?;
    if parsed == 0 {
        return Err(Error::Usage(format!("{name} must be a positive integer")));
    }
    Ok(parsed)
}

fn parse_positive_f64(value: Option<std::ffi::OsString>, name: &str) -> Result<f64> {
    let value = value.ok_or_else(|| Error::Usage(rfm_response_usage()))?;
    let parsed = value
        .to_string_lossy()
        .parse::<f64>()
        .map_err(|_| Error::Usage(format!("{name} must be a positive finite number")))?;
    if !parsed.is_finite() || parsed <= 0.0 {
        return Err(Error::Usage(format!(
            "{name} must be a positive finite number"
        )));
    }
    Ok(parsed)
}

fn parse_ports(value: Option<std::ffi::OsString>, nports: usize) -> Result<Vec<usize>> {
    let Some(value) = value else {
        return Ok((0..nports).collect());
    };
    let mut ports = Vec::new();
    for token in value.to_string_lossy().split(',') {
        let port = token.trim().parse::<usize>().map_err(|_| {
            Error::Usage(
                "--input-ports/--output-ports must be comma-separated 1-based integers".into(),
            )
        })?;
        if port == 0 || port > nports || ports.contains(&(port - 1)) {
            return Err(Error::Usage(
                "response port is outside range or repeated".into(),
            ));
        }
        ports.push(port - 1);
    }
    if ports.is_empty() {
        return Err(Error::Usage("response port list cannot be empty".into()));
    }
    Ok(ports)
}

fn parse_response_loads(
    nports: usize,
    shunt_resistances: Vec<std::ffi::OsString>,
    rc_loads: Vec<std::ffi::OsString>,
) -> Result<ResponseLoads> {
    let mut loads = ResponseLoads::empty(nports);
    let mut shorted = BTreeSet::new();
    for value in shunt_resistances {
        let (port, resistance) = parse_port_value(&value.to_string_lossy(), "--shunt-resistance")?;
        let port = checked_port(port, nports)?;
        if resistance == 0.0 {
            shorted.insert(port);
        } else if resistance.is_finite() && resistance > 0.0 {
            loads.conductance[port] += 1.0 / resistance;
        } else {
            return Err(Error::Usage(
                "--shunt-resistance must have a non-negative finite resistance".into(),
            ));
        }
    }
    loads.shorted_ports = shorted.into_iter().collect();
    if loads
        .shorted_ports
        .iter()
        .any(|&port| loads.conductance[port] != 0.0)
    {
        return Err(Error::Usage(
            "a port cannot have both an ideal short and a finite shunt resistance".into(),
        ));
    }
    for value in rc_loads {
        let value = value.to_string_lossy();
        let (port, path) = value.split_once(':').ok_or_else(|| {
            Error::Usage("--rc-load must use <1-based-port>:<two-terminal-rc-subckt.inc>".into())
        })?;
        let port = checked_port(
            port.trim()
                .parse::<usize>()
                .map_err(|_| Error::Usage("--rc-load port must be a 1-based integer".into()))?,
            nports,
        )?;
        if loads.shorted_ports.contains(&port) {
            return Err(Error::Usage(
                "--rc-load cannot be applied to an ideal-shorted port".into(),
            ));
        }
        let source = PathBuf::from(path.trim());
        if !source.is_file() {
            return Err(Error::InvalidDeck(format!(
                "RC load does not exist: {}",
                source.display()
            )));
        }
        loads.rc_shunts.push(RcShunt::parse(port, source)?);
    }
    Ok(loads)
}

fn checked_port(port: usize, nports: usize) -> Result<usize> {
    if port == 0 || port > nports {
        return Err(Error::Usage(
            "response load port is outside the RFM range".into(),
        ));
    }
    Ok(port - 1)
}

fn parse_port_value(value: &str, name: &str) -> Result<(usize, f64)> {
    let (port, raw_value) = value
        .split_once(':')
        .ok_or_else(|| Error::Usage(format!("{name} must use <1-based-port>:<resistance-ohm>")))?;
    let port = port
        .trim()
        .parse::<usize>()
        .map_err(|_| Error::Usage(format!("{name} port must be a 1-based integer")))?;
    let resistance = spice_number(raw_value.trim())
        .ok_or_else(|| Error::Usage(format!("{name} resistance is invalid")))?;
    Ok((port, resistance))
}

fn spice_number(token: &str) -> Option<f64> {
    let token = token.trim().replace(['D', 'd'], "E");
    if let Ok(value) = token.parse::<f64>() {
        return Some(value);
    }
    let numeric_end = token
        .char_indices()
        .take_while(|(_, character)| {
            character.is_ascii_digit() || matches!(character, '.' | '+' | '-' | 'E' | 'e')
        })
        .map(|(index, character)| index + character.len_utf8())
        .last()?;
    let number = token[..numeric_end].parse::<f64>().ok()?;
    let suffix = token[numeric_end..].to_ascii_lowercase();
    let multiplier = if suffix.starts_with("meg") {
        1e6
    } else if suffix.starts_with('t') {
        1e12
    } else if suffix.starts_with('g') {
        1e9
    } else if suffix.starts_with('k') {
        1e3
    } else if suffix.starts_with('m') {
        1e-3
    } else if suffix.starts_with('u') {
        1e-6
    } else if suffix.starts_with('n') {
        1e-9
    } else if suffix.starts_with('p') {
        1e-12
    } else if suffix.starts_with('f') {
        1e-15
    } else {
        return None;
    };
    Some(number * multiplier)
}

fn usage() -> String {
    "agent-spice-sim build-info [--json]\n\
     agent-spice-sim <deck> [--rfm <model.rfm>] [--rfm-subckt <name>] \
     [--output-json <result.json>] [--waveform-csv <waveform.csv>] \
     [--log <simulation.log>] [--audit-json <compatibility.json>]"
        .into()
}

fn rfm_response_usage() -> String {
    "agent-spice-sim rfm-response <model.rfm> --fft-size <N> --dt <seconds> \
     --response-bin <H.bin> --metadata-json <H.json> \
     [--input-ports 1,2] [--output-ports 1,2] [--threads <count>] \
     [--shunt-resistance <port>:<ohm>]... \
     [--rc-load <port>:<two-terminal-rc-subckt.inc>]..."
        .into()
}
