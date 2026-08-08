use std::collections::{BTreeMap, BTreeSet, HashSet};
use std::fs;
use std::path::{Path, PathBuf};

use serde::Serialize;

use crate::error::Result;

const SUPPORTED_DIRECTIVES: &[&str] = &[
    ".ac", ".dc", ".elif", ".else", ".elseif", ".end", ".endif", ".endl", ".ends", ".global",
    ".if", ".inc", ".include", ".lib", ".meas", ".measure", ".op", ".option", ".options", ".param",
    ".model", ".print", ".probe", ".subckt", ".temp", ".tran",
];

const SUPPORTED_ELEMENTS: &[u8] = b"RCLVIEGFHXS";

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CompatibilityIssue {
    path: String,
    line: usize,
    statement: String,
    reason: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CompatibilityReport {
    schema_version: usize,
    deck: String,
    compatible: bool,
    scanned_files: Vec<String>,
    statement_counts: BTreeMap<String, usize>,
    issues: Vec<CompatibilityIssue>,
}

impl CompatibilityReport {
    pub fn schema_version(&self) -> usize {
        self.schema_version
    }
    pub fn deck(&self) -> &str {
        &self.deck
    }
    pub fn is_compatible(&self) -> bool {
        self.compatible
    }
    pub fn scanned_files(&self) -> &[String] {
        &self.scanned_files
    }
    pub fn statement_counts(&self) -> &BTreeMap<String, usize> {
        &self.statement_counts
    }
    pub fn issues(&self) -> &[CompatibilityIssue] {
        &self.issues
    }
    pub fn issue_count(&self) -> usize {
        self.issues.len()
    }
    pub fn scanned_file_count(&self) -> usize {
        self.scanned_files.len()
    }
}

impl CompatibilityIssue {
    pub fn path(&self) -> &str {
        &self.path
    }
    pub fn line(&self) -> usize {
        self.line
    }
    pub fn statement(&self) -> &str {
        &self.statement
    }
    pub fn reason(&self) -> &str {
        &self.reason
    }
}

pub fn audit_file(path: &Path) -> Result<CompatibilityReport> {
    let path = path.canonicalize()?;
    let mut scanner = Scanner {
        deck: path.display().to_string(),
        ..Scanner::default()
    };
    scanner.scan_file(&path, None, true)?;
    Ok(scanner.finish())
}

#[derive(Default)]
struct Scanner {
    deck: String,
    scanned_files: BTreeSet<String>,
    statement_counts: BTreeMap<String, usize>,
    issues: Vec<CompatibilityIssue>,
    active: HashSet<PathBuf>,
}

impl Scanner {
    fn finish(self) -> CompatibilityReport {
        CompatibilityReport {
            schema_version: 1,
            deck: self.deck,
            compatible: self.issues.is_empty(),
            scanned_files: self.scanned_files.into_iter().collect(),
            statement_counts: self.statement_counts,
            issues: self.issues,
        }
    }

    fn scan_file(&mut self, path: &Path, section: Option<&str>, root: bool) -> Result<()> {
        let path = path.canonicalize()?;
        if !self.active.insert(path.clone()) {
            self.add_issue(&path, 0, "", "recursive_dependency");
            return Ok(());
        }
        self.scanned_files.insert(path.display().to_string());
        let text = fs::read_to_string(&path)?;
        let mut lines = logical_lines(&text);
        if let Some(section) = section {
            lines = self.library_section(&path, lines, section);
        }
        for (index, (line_number, line)) in lines.into_iter().enumerate() {
            if root && index == 0 {
                continue;
            }
            self.scan_statement(&path, line_number, &line)?;
        }
        self.active.remove(&path);
        Ok(())
    }

    fn library_section(
        &mut self,
        path: &Path,
        lines: Vec<(usize, String)>,
        section: &str,
    ) -> Vec<(usize, String)> {
        let mut selected = Vec::new();
        let mut inside = false;
        let mut found = false;
        for (line_number, line) in lines {
            let tokens = tokenize(&line);
            let head = tokens.first().map(|token| token.to_ascii_lowercase());
            if head.as_deref() == Some(".lib") && tokens.len() == 2 {
                inside = tokens[1].eq_ignore_ascii_case(section);
                found |= inside;
                continue;
            }
            if head.as_deref() == Some(".endl") {
                if inside {
                    break;
                }
                continue;
            }
            if inside {
                selected.push((line_number, line));
            }
        }
        if !found {
            self.add_issue(
                path,
                0,
                &format!(".lib {} {section}", path.display()),
                "library_section_not_found",
            );
        }
        selected
    }

    fn scan_statement(&mut self, path: &Path, line_number: usize, line: &str) -> Result<()> {
        let tokens = tokenize(line);
        let Some(head) = tokens.first() else {
            return Ok(());
        };
        if head.starts_with('.') {
            let directive = head.to_ascii_lowercase();
            self.increment(&directive);
            if !SUPPORTED_DIRECTIVES.contains(&directive.as_str()) {
                self.add_issue(path, line_number, line, "unsupported_directive");
                return Ok(());
            }
            if directive == ".model" && (tokens.len() < 3 || !tokens[2].eq_ignore_ascii_case("s")) {
                self.add_issue(path, line_number, line, "unsupported_model");
            } else if matches!(directive.as_str(), ".inc" | ".include") {
                self.scan_dependency(path, line_number, line, tokens.get(1), None)?;
            } else if directive == ".lib" && tokens.len() >= 3 {
                self.scan_dependency(
                    path,
                    line_number,
                    line,
                    tokens.get(1),
                    tokens.get(2).map(String::as_str),
                )?;
            }
            return Ok(());
        }

        let kind = head.as_bytes()[0].to_ascii_uppercase();
        self.increment(&format!("element:{}", kind as char));
        if !SUPPORTED_ELEMENTS.contains(&kind) {
            self.add_issue(path, line_number, line, "unsupported_element");
        } else if matches!(kind, b'V' | b'I') {
            self.scan_source(path, line_number, line, tokens.get(3..).unwrap_or_default());
        }
        Ok(())
    }

    fn scan_dependency(
        &mut self,
        source: &Path,
        line_number: usize,
        statement: &str,
        reference: Option<&String>,
        section: Option<&str>,
    ) -> Result<()> {
        let Some(reference) = reference else {
            self.add_issue(source, line_number, statement, "dependency_path_missing");
            return Ok(());
        };
        let reference = reference.trim_matches(|character| character == '\'' || character == '"');
        let path = source
            .parent()
            .unwrap_or_else(|| Path::new("."))
            .join(reference);
        if !path.is_file() {
            self.add_issue(source, line_number, statement, "dependency_not_found");
            return Ok(());
        }
        self.scan_file(&path, section, false)
    }

    fn scan_source(&mut self, path: &Path, line_number: usize, line: &str, tokens: &[String]) {
        if tokens.is_empty() {
            self.add_issue(path, line_number, line, "source_value_missing");
            return;
        }
        let lowered: Vec<_> = tokens
            .iter()
            .map(|token| token.to_ascii_lowercase())
            .collect();
        if lowered.iter().any(|token| {
            token.contains('(') && !token.starts_with("pulse(") && !token.starts_with("pwl(")
        }) {
            self.add_issue(path, line_number, line, "unsupported_source_function");
            return;
        }
        if let Some(pwl_index) = lowered.iter().position(|token| token == "pwl") {
            let options = &tokens[pwl_index + 1..];
            let has_file = tokens.iter().any(|token| {
                token.eq_ignore_ascii_case("pwlfile")
                    || token
                        .split_once('=')
                        .is_some_and(|(name, _)| name.eq_ignore_ascii_case("pwlfile"))
            });
            if !has_file {
                self.add_issue(path, line_number, line, "unsupported_source_syntax");
                return;
            }
            for token in options {
                if let Some((name, _)) = token.split_once('=')
                    && !matches!(
                        name.to_ascii_lowercase().as_str(),
                        "pwlfile" | "m" | "td" | "r"
                    )
                {
                    self.add_issue(path, line_number, line, "unsupported_source_option");
                    break;
                }
            }
        }
    }

    fn increment(&mut self, statement: &str) {
        *self
            .statement_counts
            .entry(statement.to_string())
            .or_default() += 1;
    }

    fn add_issue(&mut self, path: &Path, line: usize, statement: &str, reason: &str) {
        self.issues.push(CompatibilityIssue {
            path: path.display().to_string(),
            line,
            statement: statement.to_string(),
            reason: reason.to_string(),
        });
    }
}

fn strip_hspice_comment(line: &str) -> &str {
    let mut quote = None;
    for (index, character) in line.char_indices() {
        match character {
            '\'' | '"' if quote.is_none() => quote = Some(character),
            value if quote == Some(value) => quote = None,
            '$' if quote.is_none() => return &line[..index],
            _ => {}
        }
    }
    line
}

fn logical_lines(text: &str) -> Vec<(usize, String)> {
    let mut lines: Vec<(usize, String)> = Vec::new();
    for (physical_index, raw) in text.lines().enumerate() {
        let trimmed = strip_hspice_comment(raw).trim();
        if trimmed.is_empty() || trimmed.starts_with('*') {
            continue;
        }
        if let Some(continuation) = trimmed.strip_prefix('+') {
            if let Some((_, previous)) = lines.last_mut() {
                previous.push(' ');
                previous.push_str(continuation.trim());
            }
        } else {
            lines.push((physical_index + 1, trimmed.to_string()));
        }
    }
    lines
}

fn tokenize(line: &str) -> Vec<String> {
    let mut tokens = Vec::new();
    let mut current = String::new();
    let mut depth = 0usize;
    let mut quote = None;
    for character in line.chars() {
        match character {
            '\'' | '"' if quote.is_none() => {
                quote = Some(character);
                current.push(character);
            }
            value if quote == Some(value) => {
                quote = None;
                current.push(value);
            }
            '(' | '{' if quote.is_none() => {
                depth += 1;
                current.push(character);
            }
            ')' | '}' if quote.is_none() => {
                depth = depth.saturating_sub(1);
                current.push(character);
            }
            value if value.is_whitespace() && depth == 0 && quote.is_none() => {
                if !current.is_empty() {
                    tokens.push(std::mem::take(&mut current));
                }
            }
            _ => current.push(character),
        }
    }
    if !current.is_empty() {
        tokens.push(current);
    }
    tokens
}
