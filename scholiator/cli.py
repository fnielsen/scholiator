"""Command-line entry point for Scholiator."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

from . import __version__
from . import biblatex, bibtex
from .cache import CacheError, EntityCache
from .citation import CitationError, extract_citations, is_qid, resolve_input
from .config import Config, load_config
from .escaping import EscapingError
from .normalize import (
    NormalizationError,
    collect_name_part_qids,
    collect_related_qids,
    normalize_work,
)
from .wikidata import EntityRepository, WikidataClient, WikidataError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scholiator",
        description="Generate BibTeX/biblatex data for Wikidata QID citations.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", type=Path, help="INI configuration file")
    parser.add_argument("--format", choices=("bibtex", "biblatex"), dest="format")
    parser.add_argument("--offline", action="store_true", help="never contact Wikidata")
    parser.add_argument("--refresh", action="store_true", help="refresh required cached entities")
    parser.add_argument("-o", "--output", type=Path, help="output .bib file")
    parser.add_argument("target", nargs="?", help="document basename, .aux/.bcf file, or 'cache'")
    parser.add_argument("rest", nargs="*", help=argparse.SUPPRESS)
    return parser


def _atomic_text(path: Path, text: str, *, encoding: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _cache_command(args: argparse.Namespace, config: Config) -> int:
    if not args.rest:
        print("error: cache requires refresh, remove, or clear", file=sys.stderr)
        return 2
    action = args.rest[0]
    cache = EntityCache(config.cache_dir)
    if action == "clear":
        if len(args.rest) != 1:
            print("error: cache clear takes no QID", file=sys.stderr)
            return 2
        cache.clear()
        return 0
    if action not in {"refresh", "remove"} or len(args.rest) != 2:
        print("error: use 'cache refresh QID', 'cache remove QID', or 'cache clear'", file=sys.stderr)
        return 2
    qid = args.rest[1]
    if not is_qid(qid):
        print(f"error: invalid QID: {qid}", file=sys.stderr)
        return 2
    if action == "remove":
        cache.remove(qid)
        return 0
    repo = EntityRepository(cache, WikidataClient())
    repo.get_many([qid], refresh=True)
    return 0


def _merge_lookup(destination: dict[str, dict], source: dict[str, dict]) -> None:
    destination.update(source)
    for entity in source.values():
        if isinstance(entity, dict) and isinstance(entity.get("id"), str):
            destination[entity["id"]] = entity


def run_generation(args: argparse.Namespace, config: Config) -> int:
    if args.target is None:
        print("error: missing document basename or citation input file", file=sys.stderr)
        return 2
    input_path, default_output = resolve_input(Path(args.target))
    output_path = args.output or default_output
    qids = extract_citations(input_path)

    cache = EntityCache(config.cache_dir)
    repo = EntityRepository(cache, WikidataClient())
    lookup: dict[str, dict] = {}
    works = repo.get_many(qids, offline=args.offline, refresh=args.refresh)
    _merge_lookup(lookup, works)

    unique_works = {entity["id"]: entity for key, entity in works.items() if key in qids}.values()
    related_qids = collect_related_qids(unique_works)
    if related_qids:
        related = repo.get_many(related_qids, offline=args.offline, refresh=args.refresh)
        _merge_lookup(lookup, related)
        name_part_qids = collect_name_part_qids(
            {entity["id"]: entity for entity in related.values()}.values()
        )
        if name_part_qids:
            name_parts = repo.get_many(name_part_qids, offline=args.offline, refresh=args.refresh)
            _merge_lookup(lookup, name_parts)

    fmt = args.format or config.format
    rendered_entries: list[str] = []
    for qid in qids:
        work = works[qid]
        normalized = normalize_work(
            qid,
            work,
            lookup,
            label_languages=config.label_languages,
            title_languages=config.title_languages,
        )
        for warning in normalized.warnings:
            print(f"warning: {qid}: {warning}", file=sys.stderr)
        if fmt == "bibtex":
            rendered_entries.append(bibtex.render(normalized.record))
        else:
            rendered_entries.append(biblatex.render(normalized.record))

    text = "\n".join(entry.rstrip() for entry in rendered_entries)
    if text:
        text += "\n"
    encoding = "ascii" if fmt == "bibtex" else "utf-8"
    _atomic_text(output_path, text, encoding=encoding)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        if args.target == "cache":
            return _cache_command(args, config)
        if args.rest:
            print("error: unexpected positional arguments", file=sys.stderr)
            return 2
        return run_generation(args, config)
    except (CitationError, CacheError, WikidataError, NormalizationError, EscapingError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
