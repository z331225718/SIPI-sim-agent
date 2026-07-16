from __future__ import annotations

from dataclasses import dataclass
import re

from agent_spice.hspice.audit import audit_deck
from agent_spice.hspice.manifest import CompatReport
from agent_spice.hspice.measure import normalize_outputs


@dataclass(frozen=True)
class ConversionResult:
    deck_text: str
    report: CompatReport


def _has_post_option(line: str) -> bool:
    parts = line.strip().split()
    if not parts or parts[0].lower() != ".option":
        return False

    for token in parts[1:]:
        option = token.lower()
        if option == "post" or option.startswith("post="):
            return True
    return False


_CURRENT_PWL_REPEAT = re.compile(
    r"(?ims)(^I\S+[^\n]*?\bpwl\s*\()(.*?)(\+\s*R\s*=\s*([0-9.eE+-]+)\s*(fs|ps|ns|us|ms|s)\s*\))"
    r"(?:\s+M\s*=\s*([^\s]+))?"
)
_PWL_POINT = re.compile(r"([0-9.eE+-]+)\s*(fs|ps|ns|us|ms|s)\s+([0-9.eE+-]+)", re.IGNORECASE)
_TIME_SCALE = {"fs": 1e-15, "ps": 1e-12, "ns": 1e-9, "us": 1e-6, "ms": 1e-3, "s": 1.0}


def _seconds(value: str, unit: str) -> float:
    return float(value) * _TIME_SCALE[unit.lower()]


def _rewrite_current_pwl_repeats_for_ngspice(text: str, report: CompatReport) -> str:
    """Translate HSPICE/Cadence current PWL ``R=`` into an ngspice B source.

    ngspice implements PWL repeat for voltage sources only.  The behavioral
    source wraps time over the same repeat window, retaining the original PWL
    samples and the Cadence/HSPICE semantics of repeating from ``R`` to Tstop.
    """

    def replace(match: re.Match[str]) -> str:
        repeat_start = _seconds(match.group(4), match.group(5))
        points = [
            (_seconds(time, unit), value)
            for time, unit, value in _PWL_POINT.findall(match.group(2))
        ]
        if not points or not any(abs(time - repeat_start) <= 1e-18 for time, _ in points):
            report.add_unsupported(match.group(0).splitlines()[0], "current_pwl_repeat_point_not_found")
            return match.group(0)
        repeat_end = points[-1][0]
        if repeat_end <= repeat_start:
            report.add_unsupported(match.group(0).splitlines()[0], "invalid_current_pwl_repeat_window")
            return match.group(0)

        period = repeat_end - repeat_start
        source = re.sub(r"^I", "B", match.group(1), flags=re.IGNORECASE)
        multiplicity = match.group(6)
        multiplier = "" if multiplicity is None else f"({multiplicity}) * "
        source = re.sub(r"\bpwl\s*\($", f"I = {multiplier}pwl(", source, flags=re.IGNORECASE)
        to_ps = lambda seconds: f"{seconds / 1e-12:g}ps"
        wrapped_time = (
            f"(time <= {to_ps(repeat_start)} ? time : {to_ps(repeat_start)} + "
            f"(time - {to_ps(repeat_start)}) - {to_ps(period)} * "
            f"floor((time - {to_ps(repeat_start)}) / {to_ps(period)}))"
        )
        lines = [source + wrapped_time + ","]
        for index in range(0, len(points), 4):
            tokens = [f"{to_ps(time)}, {value}" for time, value in points[index : index + 4]]
            lines.append("+ " + ", ".join(tokens) + ("," if index + 4 < len(points) else ""))
        lines.append("+ )")
        converted = "\n".join(lines)
        report.add_action(
            "rewrite_current_pwl_repeat",
            f"{match.group(1).strip()}... R={match.group(4)}{match.group(5)}",
            f"behavioral current PWL: repeat {to_ps(repeat_start)} to {to_ps(repeat_end)}"
            + ("; preserves M=" + multiplicity if multiplicity is not None else ""),
        )
        return converted

    return _CURRENT_PWL_REPEAT.sub(replace, text)


def _compatibility_report(text: str, backend: str) -> CompatReport:
    report = CompatReport(backend=backend)
    audit = audit_deck(text)
    outputs = normalize_outputs(text)
    report.set_audit(audit.directive_counts, audit.includes, audit.libraries, audit.unsupported_directives)
    report.set_outputs(outputs.probes, outputs.measures)
    for directive in audit.unsupported_directives:
        report.add_unsupported(directive, "unsupported_directive")
    return report


def accept_hspice_deck(text: str, backend: str = "native") -> ConversionResult:
    """Accept native HSPICE syntax without rewriting the deck."""

    report = _compatibility_report(text, backend)
    report.finalize_summary()
    return ConversionResult(deck_text=text, report=report)


def convert_hspice_deck(text: str, backend: str) -> ConversionResult:
    report = _compatibility_report(text, backend)
    source_text = _rewrite_current_pwl_repeats_for_ngspice(text, report) if backend == "ngspice" else text
    output: list[str] = []
    for raw in source_text.splitlines():
        stripped = raw.strip()
        lower = stripped.lower()
        if lower.startswith(".inc "):
            converted = ".include " + stripped.split(maxsplit=1)[1]
            output.append(converted)
            report.add_action("rewrite", stripped, converted)
            continue
        if lower.startswith(".probe "):
            converted = ".print " + stripped.split(maxsplit=1)[1]
            output.append(converted)
            report.add_action("rewrite", stripped, converted)
            continue
        if _has_post_option(stripped):
            report.add_action("drop_option", stripped, "")
            continue
        output.append(raw)
    report.finalize_summary()
    return ConversionResult(deck_text="\n".join(output).strip() + "\n", report=report)
