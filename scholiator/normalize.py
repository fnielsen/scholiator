"""Normalize raw Wikibase entities into bibliographic records."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from .model import BibliographicRecord, Name

TYPE_BY_QID = {
    "Q13442814": "article",
    "Q191067": "article",
    "Q21481766": "incollection",
    "Q23927052": "inproceedings",
    "Q3331189": "book",
    "Q571": "book",
    "Q1980247": "incollection",
    "Q187685": "doctoral_thesis",
    "Q1907875": "masters_thesis",
    "Q798134": "bachelors_thesis",
    "Q10870555": "report",
    "Q7397": "software",
}

# These three types describe progressively more specific ways in which a
# paper-like work can be published.  Wikidata items can legitimately carry
# more than one of them (for example, both "scholarly article" and
# "chapter").  Known overlaps are resolved below rather than treated as
# arbitrary conflicts.
PAPER_LIKE_TYPES = frozenset({"article", "incollection", "inproceedings"})

RELATED_PROPERTIES = ("P50", "P98", "P123", "P1433", "P407")
NAME_PART_PROPERTIES = ("P735", "P734")


class NormalizationError(RuntimeError):
    """Raised when an entity cannot be normalized conservatively."""


@dataclass(frozen=True)
class NormalizationResult:
    record: BibliographicRecord
    warnings: tuple[str, ...] = ()


def _claims(entity: dict, pid: str) -> list[dict]:
    claims = entity.get("claims", {})
    values = claims.get(pid, []) if isinstance(claims, dict) else []
    return [value for value in values if isinstance(value, dict)]


def _nondeprecated(entity: dict, pid: str) -> list[dict]:
    return [statement for statement in _claims(entity, pid) if statement.get("rank") != "deprecated"]


def _alternative_statements(entity: dict, pid: str) -> list[dict]:
    statements = _nondeprecated(entity, pid)
    preferred = [s for s in statements if s.get("rank") == "preferred"]
    return preferred or [s for s in statements if s.get("rank", "normal") == "normal"]


def _datavalue(statement: dict):
    mainsnak = statement.get("mainsnak", {})
    if not isinstance(mainsnak, dict) or mainsnak.get("snaktype") != "value":
        return None
    datavalue = mainsnak.get("datavalue", {})
    return datavalue.get("value") if isinstance(datavalue, dict) else None


def _qid_value(statement: dict) -> str | None:
    value = _datavalue(statement)
    if isinstance(value, dict):
        qid = value.get("id")
        if isinstance(qid, str):
            return qid
    return None


def _string_value(statement: dict) -> str | None:
    value = _datavalue(statement)
    if isinstance(value, str):
        return value
    return None


def _monolingual_value(statement: dict) -> tuple[str, str] | None:
    value = _datavalue(statement)
    if isinstance(value, dict):
        text, language = value.get("text"), value.get("language")
        if isinstance(text, str) and isinstance(language, str):
            return text, language
    return None


def _label(entity: dict | None, languages: tuple[str, ...]) -> str | None:
    if not entity:
        return None
    labels = entity.get("labels", {})
    if not isinstance(labels, dict):
        return None
    for language in languages:
        value = labels.get(language)
        if isinstance(value, dict) and isinstance(value.get("value"), str):
            return value["value"]
    # Deterministic fallback: lexical language-code order.
    for language in sorted(labels):
        value = labels[language]
        if isinstance(value, dict) and isinstance(value.get("value"), str):
            return value["value"]
    return None


def collect_related_qids(entities: Iterable[dict]) -> list[str]:
    """Collect bounded linked entities needed for bibliography normalization."""
    result: list[str] = []
    seen: set[str] = set()
    for entity in entities:
        for pid in RELATED_PROPERTIES:
            for statement in _nondeprecated(entity, pid):
                qid = _qid_value(statement)
                if qid and qid not in seen:
                    seen.add(qid)
                    result.append(qid)
    return result


def collect_name_part_qids(entities: Iterable[dict]) -> list[str]:
    """Collect given/family-name entities from already fetched author/editor entities."""
    result: list[str] = []
    seen: set[str] = set()
    for entity in entities:
        for pid in NAME_PART_PROPERTIES:
            for statement in _nondeprecated(entity, pid):
                qid = _qid_value(statement)
                if qid and qid not in seen:
                    seen.add(qid)
                    result.append(qid)
    return result


def _qualifier_values(statement: dict, pid: str) -> list:
    qualifiers = statement.get("qualifiers", {})
    if not isinstance(qualifiers, dict):
        return []
    result = []
    for snak in qualifiers.get(pid, []):
        if not isinstance(snak, dict) or snak.get("snaktype") != "value":
            continue
        datavalue = snak.get("datavalue", {})
        if isinstance(datavalue, dict) and "value" in datavalue:
            result.append(datavalue["value"])
    return result


def _series_ordinal(statement: dict) -> str | None:
    values = _qualifier_values(statement, "P1545")
    if not values:
        return None
    value = values[0]
    return value if isinstance(value, str) else None


def _ordinal_key(value: str | None, fallback: int):
    if value is None:
        return (1, (), "", fallback)
    if re.fullmatch(r"\d+(?:\.\d+)*", value):
        return (0, tuple(int(x) for x in value.split(".")), "", fallback)
    return (0, (), value, fallback)


def _statement_named_as(statement: dict) -> str | None:
    for value in _qualifier_values(statement, "P1932"):
        if isinstance(value, str):
            return value
        if isinstance(value, dict) and isinstance(value.get("text"), str):
            return value["text"]
    return None


def _first_linked_label(
    entity: dict,
    pid: str,
    entity_lookup: dict[str, dict],
    languages: tuple[str, ...],
) -> str | None:
    for statement in _alternative_statements(entity, pid):
        qid = _qid_value(statement)
        if qid:
            value = _label(entity_lookup.get(qid), languages)
            if value:
                return value
    return None


def _name_from_entity(
    author_entity: dict | None,
    entity_lookup: dict[str, dict],
    languages: tuple[str, ...],
) -> Name | None:
    if author_entity is None:
        return None

    label = _label(author_entity, languages)
    given = _first_linked_label(author_entity, "P735", entity_lookup, languages)
    family = _first_linked_label(author_entity, "P734", entity_lookup, languages)

    # P735/P734 are often incomplete even when present.  Use them as
    # structure hints, but never let them discard information from the
    # person's label.  A common case is e.g. label="Finn Årup Nielsen",
    # P735="Finn", P734="Nielsen": since the known family name is a suffix
    # of the label, the full prefix is a defensible given-name component.
    if label and family:
        if label == family:
            return Name(family=family)
        suffix = " " + family
        if label.endswith(suffix):
            label_given = label[: -len(suffix)].strip()
            if label_given:
                # If Wikidata also has P735, only enrich it when the label
                # prefix is compatible with that value.  Otherwise retain the
                # complete label literally rather than inventing structure.
                if given is None or label_given == given or label_given.startswith(given + " "):
                    return Name(given=label_given, family=family)

    if given and family:
        return Name(given=given, family=family)

    # If either structured component is missing, the complete label is safer
    # than emitting a knowingly incomplete name.  BibTeX/Biber can parse an
    # ordinary natural-order personal name such as "John Michael Smith".
    if label:
        return Name(literal=label)

    if given or family:
        return Name(given=given, family=family)
    return None


def _names(
    work: dict,
    linked_pid: str,
    string_pid: str | None,
    entity_lookup: dict[str, dict],
    languages: tuple[str, ...],
) -> tuple[tuple[Name, ...], list[str]]:
    warnings: list[str] = []
    candidates: list[tuple[str | None, int, Name]] = []
    serial = 0

    linked_ordinals: set[str] = set()
    for statement in _nondeprecated(work, linked_pid):
        qid = _qid_value(statement)
        if not qid:
            continue
        ordinal = _series_ordinal(statement)
        named_as = _statement_named_as(statement)
        if named_as:
            name = Name(literal=named_as)
        else:
            name = _name_from_entity(entity_lookup.get(qid), entity_lookup, languages)
        if name is None:
            warnings.append(f"Could not determine a name for {linked_pid} entity {qid}")
            continue
        candidates.append((ordinal, serial, name))
        if ordinal is not None:
            linked_ordinals.add(ordinal)
        serial += 1

    if string_pid:
        for statement in _nondeprecated(work, string_pid):
            text = _string_value(statement)
            if not text:
                continue
            ordinal = _series_ordinal(statement)
            # A P50/P98 entity and a literal author-name statement at the same
            # explicit series ordinal describe the same author slot much more
            # reliably than string-similarity heuristics do.  Prefer the
            # linked entity (whose statement may also carry P1932) and avoid
            # emitting the author twice.
            if ordinal is not None and ordinal in linked_ordinals:
                warnings.append(
                    f"Ignoring {string_pid} value {text!r} at series ordinal {ordinal}; "
                    f"{linked_pid} has an entity author at the same ordinal"
                )
                continue
            candidates.append((ordinal, serial, Name(literal=text)))
            serial += 1

    ordinals = [ordinal for ordinal, _, _ in candidates if ordinal is not None]
    duplicates = sorted({value for value in ordinals if ordinals.count(value) > 1})
    if duplicates:
        warnings.append("Duplicate series ordinal(s): " + ", ".join(duplicates))
    if candidates and len(ordinals) != len(candidates):
        warnings.append("Incomplete series ordinals; serialization order used as fallback")

    candidates.sort(key=lambda item: _ordinal_key(item[0], item[1]))
    return tuple(item[2] for item in candidates), warnings


def _language_info(
    work: dict,
    entity_lookup: dict[str, dict],
    label_languages: tuple[str, ...],
) -> tuple[set[str], str | None]:
    codes: set[str] = set()
    label: str | None = None
    for statement in _alternative_statements(work, "P407"):
        qid = _qid_value(statement)
        if not qid:
            continue
        language_entity = entity_lookup.get(qid)
        if language_entity is None:
            continue
        if label is None:
            label = _label(language_entity, label_languages)
        for code_statement in _alternative_statements(language_entity, "P218"):
            code = _string_value(code_statement)
            if code:
                codes.add(code)
    return codes, label


def _select_title(
    work: dict,
    work_language_codes: set[str],
    title_languages: tuple[str, ...],
) -> str | None:
    statements = _alternative_statements(work, "P1476")
    titles = [value for s in statements if (value := _monolingual_value(s)) is not None]
    for text, language in titles:
        if language in work_language_codes:
            return text
    for desired in title_languages:
        for text, language in titles:
            if language == desired:
                return text
    if titles:
        return sorted(titles, key=lambda item: (item[1], item[0]))[0][0]
    return None


def _one_string(work: dict, pid: str, warnings: list[str]) -> str | None:
    values = [value for s in _alternative_statements(work, pid) if (value := _string_value(s))]
    if len(values) > 1:
        warnings.append(f"Multiple usable values for {pid}; using first")
    return values[0] if values else None


def _one_link_label(
    work: dict,
    pid: str,
    entity_lookup: dict[str, dict],
    languages: tuple[str, ...],
    warnings: list[str],
) -> str | None:
    values: list[str] = []
    for statement in _alternative_statements(work, pid):
        qid = _qid_value(statement)
        if qid:
            label = _label(entity_lookup.get(qid), languages)
            if label:
                values.append(label)
    if len(values) > 1:
        warnings.append(f"Multiple usable values for {pid}; using first")
    return values[0] if values else None


def _publication_date(work: dict, warnings: list[str]) -> tuple[str | None, str | None]:
    statements = _alternative_statements(work, "P577")
    values: list[tuple[str, int]] = []
    for statement in statements:
        value = _datavalue(statement)
        if not isinstance(value, dict):
            continue
        time_value, precision = value.get("time"), value.get("precision")
        if isinstance(time_value, str) and isinstance(precision, int):
            values.append((time_value, precision))
    if len(values) > 1:
        warnings.append("Multiple publication dates; using first")
    if not values:
        return None, None
    raw, precision = values[0]
    match = re.match(r"^[+-](\d+)-(\d{2})-(\d{2})T", raw)
    if not match:
        warnings.append("Unsupported Wikidata publication-date representation")
        return None, None
    year, month, day = match.groups()
    year = year.lstrip("0") or "0"
    if precision >= 11:
        return f"{year}-{month}-{day}", year
    if precision == 10:
        return f"{year}-{month}", year
    return year, year


def _proceedings_container_qid(work: dict, entity_lookup: dict[str, dict]) -> str | None:
    """Return a P1433 container that is explicitly conference proceedings.

    P4745 ("is proceedings from") is a strong structural signal that the
    containing work is conference proceedings.  Looking at the already-fetched
    P1433 entity avoids guessing from labels such as a title containing the
    word "Proceedings".
    """
    for statement in _alternative_statements(work, "P1433"):
        qid = _qid_value(statement)
        if not qid:
            continue
        container = entity_lookup.get(qid)
        if container is not None and _nondeprecated(container, "P4745"):
            return qid
    return None


def _type(
    work: dict,
    entity_lookup: dict[str, dict],
    warnings: list[str],
    *,
    identifier: str,
) -> str:
    """Choose the most appropriate supported bibliography type.

    Wikidata P31 values are not always mutually exclusive.  In particular,
    paper-like works may be typed both as a scholarly article and as a chapter.
    Resolve these known compatible overlaps by specificity and publication
    context.  Unrelated type conflicts remain errors rather than being settled
    by an arbitrary global priority list.
    """
    matched: list[tuple[str, str]] = []
    for statement in _alternative_statements(work, "P31"):
        qid = _qid_value(statement)
        if qid in TYPE_BY_QID:
            pair = (qid, TYPE_BY_QID[qid])
            if pair not in matched:
                matched.append(pair)

    if not matched:
        raise NormalizationError(f"{identifier}: unsupported or missing bibliographic type")

    supported = {entry_type for _, entry_type in matched}
    if len(supported) == 1:
        return next(iter(supported))

    description = ", ".join(f"{qid}={entry_type}" for qid, entry_type in matched)

    # Conference proceedings are more informative than the generic
    # article/chapter distinction.  For example, Q128801580 is both a
    # scholarly article and a chapter, while its P1433 container is explicitly
    # proceedings via P4745; its bibliography type is therefore inproceedings.
    if supported <= PAPER_LIKE_TYPES:
        proceedings_qid = _proceedings_container_qid(work, entity_lookup)
        if proceedings_qid is not None:
            warnings.append(
                f"Multiple supported bibliographic types ({description}); "
                f"selected inproceedings because P1433 container {proceedings_qid} "
                "has P4745 (is proceedings from)"
            )
            return "inproceedings"

        # Among non-proceedings paper-like values, an explicit chapter is more
        # specific than the broad scholarly-article class.  An explicit
        # conference-paper classification is similarly more specific.
        if "inproceedings" in supported:
            selected = "inproceedings"
        elif "incollection" in supported:
            selected = "incollection"
        else:
            selected = "article"
        warnings.append(
            f"Multiple supported bibliographic types ({description}); selected {selected} "
            "using paper-type specificity"
        )
        return selected

    raise NormalizationError(
        f"{identifier}: conflicting supported bibliographic types ({description}); "
        "no conservative resolution rule applies"
    )


def normalize_work(
    citation_key: str,
    work: dict,
    entity_lookup: dict[str, dict],
    *,
    label_languages: tuple[str, ...] = ("en", "mul"),
    title_languages: tuple[str, ...] = ("en", "mul"),
) -> NormalizationResult:
    """Normalize one cited work into a canonical record."""
    canonical_qid = str(work.get("id", ""))
    if not canonical_qid.startswith("Q"):
        raise NormalizationError("Work has no canonical Wikidata QID")

    warnings: list[str] = []
    language_codes, language_label = _language_info(work, entity_lookup, label_languages)
    title = _select_title(work, language_codes, title_languages)
    if not title:
        raise NormalizationError(f"No usable title for {citation_key}")

    entry_type = _type(work, entity_lookup, warnings, identifier=citation_key)
    authors, author_warnings = _names(work, "P50", "P2093", entity_lookup, label_languages)
    editors, editor_warnings = _names(work, "P98", None, entity_lookup, label_languages)
    warnings.extend(author_warnings)
    warnings.extend(editor_warnings)

    date, year = _publication_date(work, warnings)
    container = _one_link_label(work, "P1433", entity_lookup, label_languages, warnings)
    publisher = _one_link_label(work, "P123", entity_lookup, label_languages, warnings)
    volume = _one_string(work, "P478", warnings)
    number = _one_string(work, "P433", warnings)
    pages = _one_string(work, "P304", warnings)
    doi = _one_string(work, "P356", warnings)
    isbn13 = _one_string(work, "P212", warnings)
    isbn10 = _one_string(work, "P957", warnings)
    url = _one_string(work, "P953", warnings)

    return NormalizationResult(
        BibliographicRecord(
            citation_key=citation_key,
            canonical_qid=canonical_qid,
            entry_type=entry_type,
            title=title,
            authors=authors,
            editors=editors,
            date=date,
            year=year,
            container_title=container,
            publisher=publisher,
            volume=volume,
            number=number,
            pages=pages,
            doi=doi,
            isbn=isbn13 or isbn10,
            url=url,
            language=language_label,
        ),
        tuple(warnings),
    )
