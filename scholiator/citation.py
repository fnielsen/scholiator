"""Citation discovery from LaTeX AUX and Biber BCF files."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

QID_RE = re.compile(r"^Q[1-9][0-9]*$")
_CITATION_RE = re.compile(r"^\\citation\{([^}]*)\}", re.MULTILINE)
_INPUT_RE = re.compile(r"^\\@input\{([^}]*)\}", re.MULTILINE)


class CitationError(RuntimeError):
    """Raised when citation discovery cannot safely proceed."""


def is_qid(value: str) -> bool:
    """Return whether *value* is a strict Wikidata item identifier."""
    return bool(QID_RE.fullmatch(value.strip()))


def _deduplicate(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def extract_aux(path: Path) -> list[str]:
    """Extract QIDs from an AUX file and recursively included AUX files."""
    root = path.resolve().parent
    visited: set[Path] = set()
    found: list[str] = []

    def visit(current: Path) -> None:
        resolved = current.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise CitationError(f"Refusing AUX path outside project area: {current}") from exc
        if resolved in visited:
            return
        if not resolved.is_file():
            raise CitationError(f"AUX file not found: {resolved}")
        visited.add(resolved)

        text = resolved.read_text(encoding="utf-8", errors="strict")
        for match in _CITATION_RE.finditer(text):
            for key in match.group(1).split(","):
                key = key.strip()
                if is_qid(key):
                    found.append(key)

        for match in _INPUT_RE.finditer(text):
            raw = match.group(1).strip()
            if not raw:
                continue
            included = (resolved.parent / raw).resolve()
            try:
                included.relative_to(root)
            except ValueError as exc:
                raise CitationError(f"Refusing AUX path outside project area: {raw}") from exc
            visit(included)

    visit(path)
    return _deduplicate(found)


def extract_bcf(path: Path) -> list[str]:
    """Extract QIDs from a Biber control file."""
    if not path.is_file():
        raise CitationError(f"BCF file not found: {path}")
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        raise CitationError(f"Could not parse BCF file {path}: {exc}") from exc

    found: list[str] = []
    for element in root.iter():
        local_name = element.tag.rsplit("}", 1)[-1]
        if local_name != "citekey":
            continue
        text = (element.text or "").strip()
        if is_qid(text):
            found.append(text)
    return _deduplicate(found)


def resolve_input(target: Path) -> tuple[Path, Path]:
    """Resolve a target to its citation source and default output path.

    Returns ``(input_path, output_path)``.
    """
    if target.suffix in {".aux", ".bcf"}:
        input_path = target
        base = target.with_suffix("")
    else:
        base = target
        bcf = Path(f"{target}.bcf")
        aux = Path(f"{target}.aux")
        if bcf.is_file():
            input_path = bcf
        elif aux.is_file():
            input_path = aux
        else:
            raise CitationError(f"Neither {bcf} nor {aux} exists")
    return input_path, Path(f"{base}.bib")


def extract_citations(path: Path) -> list[str]:
    """Extract QIDs according to the citation input file type."""
    if path.suffix == ".aux":
        return extract_aux(path)
    if path.suffix == ".bcf":
        return extract_bcf(path)
    raise CitationError(f"Unsupported citation input format: {path}")
