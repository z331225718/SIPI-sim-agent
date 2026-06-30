from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class HspiceCase:
    name: str
    text: str


def _case_suffix(header: str, index: int) -> str:
    parts = header.split(maxsplit=1)
    if len(parts) == 1:
        return f"alter_{index:03d}"
    label = re.sub(r"[^a-zA-Z0-9_]+", "_", parts[1].strip()).strip("_").lower()
    return f"alter_{index:03d}_{label}" if label else f"alter_{index:03d}"


def _case_text(lines: list[str], end_line: str | None) -> str:
    body = "\n".join(lines).strip()
    if end_line is not None:
        body = f"{body}\n{end_line}" if body else end_line
    return f"{body}\n" if body else "\n"


def split_alter_cases(text: str, stem: str) -> list[HspiceCase]:
    lines = text.splitlines()
    base: list[str] = []
    alters: list[tuple[str, list[str]]] = []
    current_header: str | None = None
    current_lines: list[str] = []
    end_line: str | None = None
    for line in lines:
        stripped = line.strip()
        if stripped.lower() == ".end":
            end_line = stripped
            continue
        if line.strip().lower().startswith(".alter"):
            if current_header is not None:
                alters.append((current_header, current_lines))
            current_header = stripped
            current_lines = []
            continue
        if current_header is None:
            base.append(line)
        else:
            current_lines.append(line)
    if current_header is not None:
        alters.append((current_header, current_lines))

    base_text = _case_text(base, end_line)
    cases = [HspiceCase(name=f"{stem}__base", text=base_text)]
    for index, (header, body) in enumerate(alters, start=1):
        suffix = _case_suffix(header, index)
        case_text = _case_text([*base, *body], end_line)
        cases.append(HspiceCase(name=f"{stem}__{suffix}", text=case_text))
    return cases
