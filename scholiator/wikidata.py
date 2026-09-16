"""Wikidata Action API access and cache-backed entity resolution."""

from __future__ import annotations

import gzip
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from . import __version__
from .cache import EntityCache
from .citation import is_qid

API_URL = "https://www.wikidata.org/w/api.php"
PROJECT_URL = "https://github.com/WDscholia/scholia"
DEFAULT_USER_AGENT = f"Scholiator/{__version__} ({PROJECT_URL}; bibliography generator)"


class WikidataError(RuntimeError):
    """Raised when Wikidata data cannot be fetched safely."""


@dataclass(frozen=True)
class FetchResult:
    entities: dict[str, dict]
    aliases: dict[str, str]
    missing: set[str]


class WikidataClient:
    """Small standard-library client for ``wbgetentities``."""

    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: float = 20.0,
        max_retries: int = 3,
        batch_size: int = 50,
    ) -> None:
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_retries = max_retries
        self.batch_size = min(max(batch_size, 1), 50)

    def _request_json(self, params: dict[str, str]) -> dict:
        query = urllib.parse.urlencode(params)
        request = urllib.request.Request(
            f"{API_URL}?{query}",
            headers={
                "User-Agent": self.user_agent,
                "Accept-Encoding": "gzip",
                "Accept": "application/json",
            },
        )
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = response.read()
                    if response.headers.get("Content-Encoding", "").lower() == "gzip":
                        payload = gzip.decompress(payload)
                    data = json.loads(payload.decode("utf-8"))
                    if isinstance(data, dict) and data.get("error", {}).get("code") == "maxlag":
                        if attempt >= self.max_retries:
                            raise WikidataError("Wikidata maxlag persisted after retries")
                        time.sleep(min(2**attempt, 8))
                        continue
                    if not isinstance(data, dict):
                        raise WikidataError("Unexpected Wikidata response")
                    return data
            except urllib.error.HTTPError as exc:
                transient = exc.code == 429 or 500 <= exc.code <= 504
                if not transient or attempt >= self.max_retries:
                    raise WikidataError(f"Wikidata HTTP error {exc.code}") from exc
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                try:
                    delay = float(retry_after) if retry_after is not None else float(2**attempt)
                except ValueError:
                    delay = float(2**attempt)
                time.sleep(min(max(delay, 0.0), 60.0))
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                if attempt >= self.max_retries:
                    raise WikidataError(f"Wikidata request failed: {exc}") from exc
                time.sleep(min(2**attempt, 8))
        raise WikidataError("Wikidata request failed")

    def fetch(self, qids: list[str]) -> FetchResult:
        ordered: list[str] = []
        seen: set[str] = set()
        for qid in qids:
            if not is_qid(qid):
                raise WikidataError(f"Invalid QID: {qid}")
            if qid not in seen:
                seen.add(qid)
                ordered.append(qid)

        all_entities: dict[str, dict] = {}
        all_aliases: dict[str, str] = {}
        missing: set[str] = set()
        for offset in range(0, len(ordered), self.batch_size):
            batch = ordered[offset : offset + self.batch_size]
            data = self._request_json(
                {
                    "action": "wbgetentities",
                    "ids": "|".join(batch),
                    "props": "info|labels|claims",
                    "redirects": "yes",
                    "maxlag": "5",
                    "format": "json",
                }
            )
            redirects = data.get("redirects", [])
            if isinstance(redirects, list):
                for item in redirects:
                    if isinstance(item, dict):
                        source, target = item.get("from"), item.get("to")
                        if isinstance(source, str) and isinstance(target, str) and is_qid(source) and is_qid(target):
                            all_aliases[source] = target

            entities = data.get("entities", {})
            if not isinstance(entities, dict):
                raise WikidataError("Malformed Wikidata entities response")
            for key, entity in entities.items():
                if not isinstance(entity, dict):
                    continue
                qid = str(entity.get("id", key))
                if "missing" in entity:
                    if is_qid(qid):
                        missing.add(qid)
                    continue
                if not is_qid(qid):
                    raise WikidataError("Malformed Wikidata entity identifier")
                entity["id"] = qid
                all_entities[qid] = entity

            for requested in batch:
                canonical = all_aliases.get(requested, requested)
                if canonical not in all_entities and requested not in all_entities:
                    missing.add(requested)

        return FetchResult(all_entities, all_aliases, missing)


class EntityRepository:
    """Resolve entities from cache and Wikidata with offline/refresh semantics."""

    def __init__(self, cache: EntityCache, client: WikidataClient | None = None) -> None:
        self.cache = cache
        self.client = client or WikidataClient()

    def get_many(
        self,
        qids: list[str],
        *,
        offline: bool = False,
        refresh: bool = False,
    ) -> dict[str, dict]:
        result: dict[str, dict] = {}
        needed: list[str] = []
        for qid in qids:
            if not is_qid(qid):
                raise WikidataError(f"Invalid QID: {qid}")
            if not refresh:
                entity = self.cache.get(qid)
                if entity is not None:
                    result[qid] = entity
                    result[entity["id"]] = entity
                    continue
            needed.append(qid)

        if needed:
            if offline:
                raise WikidataError(
                    "Required entities are absent from cache in offline mode: " + ", ".join(needed)
                )
            fetched = self.client.fetch(needed)
            if fetched.missing:
                raise WikidataError("Wikidata items not found: " + ", ".join(sorted(fetched.missing)))
            for entity in fetched.entities.values():
                self.cache.write_entity(entity)
                result[entity["id"]] = entity
            for alias, canonical in fetched.aliases.items():
                self.cache.set_alias(alias, canonical)
            for qid in needed:
                entity = self.cache.get(qid)
                if entity is None:
                    raise WikidataError(f"No entity returned for {qid}")
                result[qid] = entity
                result[entity["id"]] = entity
        return result
