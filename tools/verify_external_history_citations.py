"""Enforce hash-only external-history citations in P7 publication documents."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs" / "baselines" / "external-history-citations.v1.yaml"
REGISTER = ROOT / "clean-room-register.v1.yaml"
SCHEMA = "sipi.external-history-citations.v1"
MARKER = re.compile(r"history-ref:([a-z0-9][a-z0-9-]*)@([0-9a-f]{40})")
FORBIDDEN = ("file://", "external/", "engines/", "..", "\\\\", "c:/", "c:\\\\")


class CitationError(RuntimeError):
    pass


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CitationError("registry_invalid") from error
    if not isinstance(value, dict):
        raise CitationError("registry_invalid")
    return value


def safe_doc(path: str) -> bool:
    candidate = Path(path)
    return not candidate.is_absolute() and candidate.is_relative_to(Path("docs/baselines")) and ".." not in candidate.parts and candidate.suffix == ".md"


def material_kind(material_id: str) -> str | None:
    text = REGISTER.read_text(encoding="utf-8")
    match = re.search(rf"^  - id: {re.escape(material_id)}\r?$\n    kind: ([a-z_]+)", text, re.MULTILINE)
    return match.group(1) if match else None


def validate(document: dict[str, Any], root: Path) -> None:
    expected = {"schema", "publication_scope", "promotion_status", "non_claims", "release_docs", "entries"}
    if set(document) != expected or document["schema"] != SCHEMA:
        raise CitationError("registry_schema_invalid")
    if document["publication_scope"] != "p7_release_publication_docs_only" or document["promotion_status"] != "blocked":
        raise CitationError("registry_promotion_invalid")
    if not isinstance(document["non_claims"], list) or "not_a_history_mirror" not in document["non_claims"]:
        raise CitationError("registry_nonclaim_invalid")
    docs = document["release_docs"]
    if not isinstance(docs, list) or not docs or len(docs) != len(set(docs)) or any(not isinstance(path, str) or not safe_doc(path) or not (root / path).is_file() for path in docs):
        raise CitationError("release_docs_invalid")
    entries = document["entries"]
    if not isinstance(entries, list) or not entries:
        raise CitationError("entries_invalid")
    ids: set[str] = set(); markers: set[tuple[str, str]] = set()
    fields = {"id", "repository_alias", "canonical_origin", "object_format", "object_hash", "role", "evidence_ref", "use", "material_ref", "product_material_status"}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != fields:
            raise CitationError("entry_schema_invalid")
        entry_id = entry["id"]
        if not isinstance(entry_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", entry_id) or entry_id in ids:
            raise CitationError("entry_id_invalid")
        ids.add(entry_id)
        if (entry["object_format"], entry["use"], entry["product_material_status"]) != ("sha1", "hash_reference_only", "prohibited"):
            raise CitationError("entry_policy_invalid")
        if entry["role"] not in {"oracle", "provenance", "license_evidence"} or not re.fullmatch(r"[0-9a-f]{40}", entry["object_hash"]):
            raise CitationError("entry_identity_invalid")
        if not isinstance(entry["canonical_origin"], str) or not entry["canonical_origin"].startswith("https://"):
            raise CitationError("entry_origin_invalid")
        if entry["evidence_ref"] not in docs or material_kind(entry["material_ref"]) not in {"oracle_fixture", "pybert_source", "non_mit_source", "mit_source"}:
            raise CitationError("entry_material_invalid")
        markers.add((entry_id, entry["object_hash"]))
    observed: set[tuple[str, str]] = set()
    for path in docs:
        text = (root / path).read_text(encoding="utf-8")
        lowered = text.lower()
        if any(token in lowered for token in FORBIDDEN):
            raise CitationError("release_doc_unsafe_reference")
        observed.update(MARKER.findall(text))
    if observed != markers:
        raise CitationError("citation_marker_mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    arguments = parser.parse_args()
    try:
        validate(load(arguments.registry), ROOT)
        print(json.dumps({"schema": SCHEMA, "valid": True, "promotion_status": "blocked"}, sort_keys=True))
        return 0
    except CitationError as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
