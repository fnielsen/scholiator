"""UTF-8 biblatex/Biber renderer."""

from __future__ import annotations

from .escaping import escape_text, escape_url, validate_doi, validate_isbn
from .model import BibliographicRecord, Name

ENTRY_TYPES = {
    "article": "article",
    "inproceedings": "inproceedings",
    "book": "book",
    "incollection": "incollection",
    "doctoral_thesis": "thesis",
    "masters_thesis": "thesis",
    "bachelors_thesis": "thesis",
    "report": "report",
    "software": "software",
}


def _name(name: Name) -> str:
    if name.literal is not None:
        text = escape_text(name.literal, ascii_only=False)
        return "{{" + text + "}}" if name.is_organization else text
    family = escape_text(name.family or "", ascii_only=False)
    given = escape_text(name.given or "", ascii_only=False)
    if family and given:
        return f"{family}, {given}"
    return family or given


def render(record: BibliographicRecord) -> str:
    """Render a record as UTF-8 biblatex data intended for Biber."""
    entry_type = ENTRY_TYPES[record.entry_type]
    fields: list[tuple[str, str]] = []
    if record.authors:
        fields.append(("author", " and ".join(_name(name) for name in record.authors)))
    if record.editors:
        fields.append(("editor", " and ".join(_name(name) for name in record.editors)))
    fields.append(("title", "{" + escape_text(record.title, ascii_only=False) + "}"))
    if record.container_title:
        key = "journaltitle" if record.entry_type == "article" else "booktitle"
        fields.append((key, escape_text(record.container_title, ascii_only=False)))
    if record.publisher:
        fields.append(("publisher", escape_text(record.publisher, ascii_only=False)))
    if record.date:
        fields.append(("date", escape_text(record.date, ascii_only=False)))
    elif record.year:
        fields.append(("date", escape_text(record.year, ascii_only=False)))
    if record.volume:
        fields.append(("volume", escape_text(record.volume, ascii_only=False)))
    if record.number:
        fields.append(("number", escape_text(record.number, ascii_only=False)))
    if record.pages:
        fields.append(("pages", escape_text(record.pages, ascii_only=False)))
    if record.doi:
        fields.append(("doi", escape_url(validate_doi(record.doi), ascii_only=False)))
    if record.isbn:
        fields.append(("isbn", escape_text(validate_isbn(record.isbn), ascii_only=False)))
    if record.url:
        fields.append(("url", escape_url(record.url, ascii_only=False)))
    if record.language:
        fields.append(("language", escape_text(record.language, ascii_only=False)))
    if record.entry_type.endswith("thesis"):
        subtype = {
            "doctoral_thesis": "phdthesis",
            "masters_thesis": "mathesis",
            "bachelors_thesis": "bathesis",
        }[record.entry_type]
        fields.append(("type", subtype))
    fields.append(("wikidata", record.canonical_qid))

    lines = [f"@{entry_type}{{{record.citation_key},"]
    for index, (key, value) in enumerate(fields):
        comma = "," if index < len(fields) - 1 else ""
        lines.append(f"  {key} = {{{value}}}{comma}")
    lines.append("}")
    return "\n".join(lines) + "\n"
