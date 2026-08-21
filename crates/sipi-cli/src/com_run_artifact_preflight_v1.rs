//! Bounded lexical preflight for the public specified COM artifact request.
//!
//! This runs before serde deserialization and before opening the caller pulse
//! root. The parser remains the authority for semantic validation; this
//! scanner only bounds the JSON container and string surface.

use sipi_com::COM_RUN_ARTIFACT_REQUEST_MAX_BYTES_V1;

pub const COM_RUN_ARTIFACT_PREFLIGHT_MAX_CONTAINERS_V1: usize = 256;
pub const COM_RUN_ARTIFACT_PREFLIGHT_MAX_CONTAINER_ITEMS_V1: usize = 256;
pub const COM_RUN_ARTIFACT_PREFLIGHT_MAX_STRING_BYTES_V1: usize = 4096;
pub const COM_RUN_ARTIFACT_PREFLIGHT_MAX_NESTING_V1: usize = 32;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ComRunArtifactPreflightErrorV1 {
    RequestTooLarge,
    InvalidJson,
    ContainerBudgetExceeded,
    StringBudgetExceeded,
    NestingBudgetExceeded,
}

pub fn preflight_com_run_artifact_request_v1(
    input: &[u8],
) -> Result<(), ComRunArtifactPreflightErrorV1> {
    if input.is_empty() || input.len() > COM_RUN_ARTIFACT_REQUEST_MAX_BYTES_V1 {
        return Err(ComRunArtifactPreflightErrorV1::RequestTooLarge);
    }
    let mut scanner = Scanner {
        input,
        position: 0,
        containers: 0,
    };
    scanner.value(0)?;
    scanner.whitespace();
    if scanner.position != input.len() {
        return Err(ComRunArtifactPreflightErrorV1::InvalidJson);
    }
    Ok(())
}

struct Scanner<'a> {
    input: &'a [u8],
    position: usize,
    containers: usize,
}

impl Scanner<'_> {
    fn value(&mut self, depth: usize) -> Result<(), ComRunArtifactPreflightErrorV1> {
        self.whitespace();
        match self.input.get(self.position).copied() {
            Some(b'{') => self.object(depth),
            Some(b'[') => self.array(depth),
            Some(b'"') => self.string(),
            Some(b't') => self.literal(b"true"),
            Some(b'f') => self.literal(b"false"),
            Some(b'n') => self.literal(b"null"),
            Some(b'-' | b'0'..=b'9') => self.number(),
            _ => Err(ComRunArtifactPreflightErrorV1::InvalidJson),
        }
    }

    fn object(&mut self, depth: usize) -> Result<(), ComRunArtifactPreflightErrorV1> {
        self.container(depth)?;
        self.position += 1;
        self.whitespace();
        if self.take(b'}') {
            return Ok(());
        }
        self.members(b'}', true, depth)
    }

    fn array(&mut self, depth: usize) -> Result<(), ComRunArtifactPreflightErrorV1> {
        self.container(depth)?;
        self.position += 1;
        self.whitespace();
        if self.take(b']') {
            return Ok(());
        }
        self.members(b']', false, depth)
    }

    fn members(
        &mut self,
        closing: u8,
        object: bool,
        depth: usize,
    ) -> Result<(), ComRunArtifactPreflightErrorV1> {
        let mut count = 0;
        loop {
            count += 1;
            if count > COM_RUN_ARTIFACT_PREFLIGHT_MAX_CONTAINER_ITEMS_V1 {
                return Err(ComRunArtifactPreflightErrorV1::ContainerBudgetExceeded);
            }
            if object {
                self.string()?;
                self.whitespace();
                if !self.take(b':') {
                    return Err(ComRunArtifactPreflightErrorV1::InvalidJson);
                }
            }
            self.value(depth + 1)?;
            self.whitespace();
            if self.take(closing) {
                return Ok(());
            }
            if !self.take(b',') {
                return Err(ComRunArtifactPreflightErrorV1::InvalidJson);
            }
            self.whitespace();
        }
    }

    fn container(&mut self, depth: usize) -> Result<(), ComRunArtifactPreflightErrorV1> {
        if depth >= COM_RUN_ARTIFACT_PREFLIGHT_MAX_NESTING_V1 {
            return Err(ComRunArtifactPreflightErrorV1::NestingBudgetExceeded);
        }
        self.containers += 1;
        if self.containers > COM_RUN_ARTIFACT_PREFLIGHT_MAX_CONTAINERS_V1 {
            return Err(ComRunArtifactPreflightErrorV1::ContainerBudgetExceeded);
        }
        Ok(())
    }

    fn string(&mut self) -> Result<(), ComRunArtifactPreflightErrorV1> {
        if !self.take(b'"') {
            return Err(ComRunArtifactPreflightErrorV1::InvalidJson);
        }
        let start = self.position;
        while let Some(byte) = self.input.get(self.position).copied() {
            match byte {
                b'"' => {
                    if self.position - start > COM_RUN_ARTIFACT_PREFLIGHT_MAX_STRING_BYTES_V1 {
                        return Err(ComRunArtifactPreflightErrorV1::StringBudgetExceeded);
                    }
                    self.position += 1;
                    return Ok(());
                }
                b'\\' => {
                    self.position += 1;
                    match self.input.get(self.position).copied() {
                        Some(b'"' | b'\\' | b'/' | b'b' | b'f' | b'n' | b'r' | b't') => {
                            self.position += 1;
                        }
                        Some(b'u') => {
                            self.position += 1;
                            for _ in 0..4 {
                                if !self
                                    .input
                                    .get(self.position)
                                    .is_some_and(|value| value.is_ascii_hexdigit())
                                {
                                    return Err(ComRunArtifactPreflightErrorV1::InvalidJson);
                                }
                                self.position += 1;
                            }
                        }
                        _ => return Err(ComRunArtifactPreflightErrorV1::InvalidJson),
                    }
                }
                0..=0x1f => return Err(ComRunArtifactPreflightErrorV1::InvalidJson),
                _ => self.position += 1,
            }
            if self.position - start > COM_RUN_ARTIFACT_PREFLIGHT_MAX_STRING_BYTES_V1 {
                return Err(ComRunArtifactPreflightErrorV1::StringBudgetExceeded);
            }
        }
        Err(ComRunArtifactPreflightErrorV1::InvalidJson)
    }

    fn literal(&mut self, expected: &[u8]) -> Result<(), ComRunArtifactPreflightErrorV1> {
        let end = self.position + expected.len();
        if self.input.get(self.position..end) == Some(expected) {
            self.position = end;
            Ok(())
        } else {
            Err(ComRunArtifactPreflightErrorV1::InvalidJson)
        }
    }

    fn number(&mut self) -> Result<(), ComRunArtifactPreflightErrorV1> {
        let start = self.position;
        self.take(b'-');
        if self.take(b'0') {
            if self
                .input
                .get(self.position)
                .is_some_and(|value| value.is_ascii_digit())
            {
                return Err(ComRunArtifactPreflightErrorV1::InvalidJson);
            }
        } else if !self.consume_digits() {
            return Err(ComRunArtifactPreflightErrorV1::InvalidJson);
        }
        if self.take(b'.') && !self.consume_digits() {
            return Err(ComRunArtifactPreflightErrorV1::InvalidJson);
        }
        if self.take(b'e') || self.take(b'E') {
            self.take(b'+');
            self.take(b'-');
            if !self.consume_digits() {
                return Err(ComRunArtifactPreflightErrorV1::InvalidJson);
            }
        }
        if self.position == start
            || self.input.get(self.position).is_some_and(|value| {
                !matches!(value, b' ' | b'\n' | b'\r' | b'\t' | b',' | b']' | b'}')
            })
        {
            return Err(ComRunArtifactPreflightErrorV1::InvalidJson);
        }
        Ok(())
    }

    fn consume_digits(&mut self) -> bool {
        let start = self.position;
        while self
            .input
            .get(self.position)
            .is_some_and(|value| value.is_ascii_digit())
        {
            self.position += 1;
        }
        self.position != start
    }

    fn whitespace(&mut self) {
        while self
            .input
            .get(self.position)
            .is_some_and(|value| matches!(value, b' ' | b'\n' | b'\r' | b'\t'))
        {
            self.position += 1;
        }
    }

    fn take(&mut self, expected: u8) -> bool {
        if self.input.get(self.position) == Some(&expected) {
            self.position += 1;
            true
        } else {
            false
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_bounded_nested_request_shape() {
        preflight_com_run_artifact_request_v1(
            br#"{"schema":"sipi.com.run-artifact-request.v1","params":{"A_v":0.5},"defaults":{},"consumed_keys":["A_v"],"unconsumed_keys":[],"request_id":"r","pulse_artifact_id":"p","pulse_manifest_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","artifact_root":"out","artifact_id":"result"}"#,
        )
        .expect("bounded request");
    }

    #[test]
    fn rejects_oversized_request_before_deserialization() {
        let input = vec![b' '; COM_RUN_ARTIFACT_REQUEST_MAX_BYTES_V1 + 1];
        assert_eq!(
            preflight_com_run_artifact_request_v1(&input),
            Err(ComRunArtifactPreflightErrorV1::RequestTooLarge)
        );
    }

    #[test]
    fn rejects_long_string_and_container_budget() {
        let long = format!(
            "\"{}\"",
            "x".repeat(COM_RUN_ARTIFACT_PREFLIGHT_MAX_STRING_BYTES_V1 + 1)
        );
        assert_eq!(
            preflight_com_run_artifact_request_v1(long.as_bytes()),
            Err(ComRunArtifactPreflightErrorV1::StringBudgetExceeded)
        );
        let nested = format!(
            "[{}]",
            (0..=COM_RUN_ARTIFACT_PREFLIGHT_MAX_CONTAINER_ITEMS_V1)
                .map(|_| "[]")
                .collect::<Vec<_>>()
                .join(",")
        );
        assert!(matches!(
            preflight_com_run_artifact_request_v1(nested.as_bytes()),
            Err(ComRunArtifactPreflightErrorV1::ContainerBudgetExceeded
                | ComRunArtifactPreflightErrorV1::NestingBudgetExceeded)
        ));
    }
}
