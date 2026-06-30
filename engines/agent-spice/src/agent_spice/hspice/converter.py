from __future__ import annotations

from dataclasses import dataclass

from agent_spice.hspice.manifest import CompatReport


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


def convert_hspice_deck(text: str, backend: str) -> ConversionResult:
    report = CompatReport(backend=backend)
    output: list[str] = []
    for raw in text.splitlines():
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
    return ConversionResult(deck_text="\n".join(output).strip() + "\n", report=report)
