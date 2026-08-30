"""Classify MATLAB oracle failures without changing oracle behavior.

The MATLAB wrapper writes ``failure.json`` before it rethrows an MException.
That file is evidence of an oracle-level failure, unlike a Python Engine exit
without the file, which can only be reported as a transport failure.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


MAX_FAILURE_BYTES = 128 * 1024
ANTI_CAUSAL_MESSAGE = "Anti-causal response found. Finer frequency step is required for this channel"
ANTI_CAUSAL_FRAME = re.compile(r"\bcom_ieee8023_480\s*\(line\s+6339\)")
DOMAIN_CATALOG = "agent-com-r480-5272ffe-v1"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _strict_json(payload: bytes) -> Any:
    return json.loads(payload, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def _failure(path: Path) -> dict[str, str] | None:
    if not path.is_file() or path.stat().st_size > MAX_FAILURE_BYTES:
        return None
    try:
        value = _strict_json(path.read_bytes())
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or set(value) != {"identifier", "message", "report"}:
        return None
    if not all(isinstance(value[key], str) for key in value):
        return None
    return value


def classify_matlab_failure(returncode: int, timed_out: bool, output_dir: Path) -> dict[str, str]:
    """Return only fixed labels and digests; never serialize oracle paths/text."""
    if timed_out:
        return {"kind": "worker_timeout"}
    failure = _failure(output_dir / "failure.json")
    if failure is None:
        return {"kind": "runtime_transport_failed"}

    result = {
        "kind": "oracle_source_exception",
        "failure_identifier_sha256": _sha256(failure["identifier"]),
        "failure_message_sha256": _sha256(failure["message"]),
        "failure_report_sha256": _sha256(failure["report"]),
    }
    if failure["message"] == ANTI_CAUSAL_MESSAGE and ANTI_CAUSAL_FRAME.search(failure["report"]):
        result["kind"] = "oracle_domain_rejected"
        result["domain_catalog"] = DOMAIN_CATALOG
    return result
