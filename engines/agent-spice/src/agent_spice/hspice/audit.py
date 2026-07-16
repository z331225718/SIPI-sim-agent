from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import shlex


SUPPORTED_DIRECTIVES = {
    ".ac",
    ".alter",
    ".dc",
    ".endl",
    ".end",
    ".ends",
    ".global",
    ".inc",
    ".include",
    ".lib",
    ".measure",
    ".meas",
    ".op",
    ".option",
    ".param",
    ".print",
    ".probe",
    ".subckt",
    ".temp",
    ".tran",
}


@dataclass(frozen=True)
class AuditReport:
    directive_counts: dict[str, int]
    includes: list[str]
    libraries: list[tuple[str, str | None]]
    unsupported_directives: list[str]


def _strip_hspice_comment(line: str) -> str:
    quote: str | None = None
    for index, character in enumerate(line):
        if character in {"'", '"'} and quote is None:
            quote = character
        elif character == quote:
            quote = None
        elif character == "$" and quote is None:
            return line[:index]
    return line


def _logical_lines(text: str) -> list[str]:
    lines: list[str] = []
    current = ""
    for raw in text.splitlines():
        stripped = _strip_hspice_comment(raw).strip()
        if not stripped or stripped.startswith("*"):
            continue
        if stripped.startswith("+"):
            current = f"{current} {stripped[1:].strip()}"
            continue
        if current:
            lines.append(current)
        current = stripped
    if current:
        lines.append(current)
    return lines


def _tokens(line: str) -> list[str]:
    return shlex.split(line, comments=False, posix=False)


def _clean_path(token: str) -> str:
    return token.strip("\"'")


def audit_deck(text: str) -> AuditReport:
    counts: Counter[str] = Counter()
    includes: list[str] = []
    libraries: list[tuple[str, str | None]] = []
    unsupported: list[str] = []
    for line in _logical_lines(text):
        if not line.startswith("."):
            continue
        tokens = _tokens(line)
        directive = tokens[0].lower()
        counts[directive] += 1
        if directive in {".include", ".inc"} and len(tokens) >= 2:
            includes.append(_clean_path(tokens[1]))
        if directive == ".lib" and len(tokens) >= 2:
            section = _clean_path(tokens[2]) if len(tokens) >= 3 else None
            libraries.append((_clean_path(tokens[1]), section))
        if directive not in SUPPORTED_DIRECTIVES:
            unsupported.append(directive)
    return AuditReport(
        directive_counts=dict(counts),
        includes=includes,
        libraries=libraries,
        unsupported_directives=unsupported,
    )
