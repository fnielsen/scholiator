"""Renderer-independent bibliography data structures."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Name:
    """A bibliography name.

    Structured names keep given and family components separate. Literal names
    are retained when Wikidata does not provide reliable structure.
    """

    given: str | None = None
    family: str | None = None
    literal: str | None = None
    is_organization: bool = False

    def __post_init__(self) -> None:
        if self.literal is None and self.given is None and self.family is None:
            raise ValueError("Name must contain structured or literal data")


@dataclass(frozen=True)
class BibliographicRecord:
    """Canonical, renderer-independent bibliographic data."""

    citation_key: str
    canonical_qid: str
    entry_type: str
    title: str
    authors: tuple[Name, ...] = ()
    editors: tuple[Name, ...] = ()
    date: str | None = None
    year: str | None = None
    container_title: str | None = None
    publisher: str | None = None
    volume: str | None = None
    number: str | None = None
    pages: str | None = None
    doi: str | None = None
    isbn: str | None = None
    url: str | None = None
    language: str | None = None
    metadata: dict[str, str] = field(default_factory=dict, compare=False)
