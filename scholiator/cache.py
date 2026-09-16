"""Persistent raw-Wikibase entity cache."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .citation import is_qid


class CacheError(RuntimeError):
    """Raised for malformed or inaccessible cache data."""


class EntityCache:
    """Store one canonical Wikibase entity per JSON file plus alias metadata."""

    def __init__(self, root: Path):
        self.root = root
        self.entities_dir = root / "entities"
        self.aliases_path = root / "aliases.json"

    def _ensure(self) -> None:
        self.entities_dir.mkdir(parents=True, exist_ok=True)

    def _entity_path(self, qid: str) -> Path:
        if not is_qid(qid):
            raise CacheError(f"Invalid QID: {qid}")
        return self.entities_dir / f"{qid}.json"

    def _read_aliases(self) -> dict[str, str]:
        if not self.aliases_path.exists():
            return {}
        try:
            data = json.loads(self.aliases_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CacheError(f"Malformed cache alias metadata: {exc}") from exc
        if not isinstance(data, dict):
            raise CacheError("Malformed cache alias metadata")
        return {str(k): str(v) for k, v in data.items() if is_qid(str(k)) and is_qid(str(v))}

    @staticmethod
    def _atomic_json(path: Path, data: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, sort_keys=True, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def write_entity(self, entity: dict) -> str:
        qid = str(entity.get("id", ""))
        if not is_qid(qid):
            raise CacheError("Entity does not contain a valid canonical QID")
        self._ensure()
        self._atomic_json(self._entity_path(qid), entity)
        return qid

    def set_alias(self, alias: str, canonical: str) -> None:
        if not is_qid(alias) or not is_qid(canonical):
            raise CacheError("Invalid alias mapping")
        if alias == canonical:
            return
        self._ensure()
        aliases = self._read_aliases()
        aliases[alias] = canonical
        self._atomic_json(self.aliases_path, aliases)

    def resolve(self, qid: str) -> str:
        if not is_qid(qid):
            raise CacheError(f"Invalid QID: {qid}")
        aliases = self._read_aliases()
        seen: set[str] = set()
        current = qid
        while current in aliases:
            if current in seen:
                raise CacheError("Alias cycle in cache metadata")
            seen.add(current)
            current = aliases[current]
        return current

    def get(self, qid: str) -> dict | None:
        canonical = self.resolve(qid)
        path = self._entity_path(canonical)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CacheError(f"Malformed cache entity {canonical}: {exc}") from exc
        if not isinstance(data, dict) or data.get("id") != canonical:
            raise CacheError(f"Malformed cache entity {canonical}")
        return data

    def remove(self, qid: str) -> None:
        aliases = self._read_aliases()
        if qid in aliases:
            # Removing a redirect/alias invalidates that lookup only.  The
            # canonical entity may still be required by citations using its
            # canonical QID or by other aliases.
            del aliases[qid]
            if aliases:
                self._atomic_json(self.aliases_path, aliases)
            elif self.aliases_path.exists():
                self.aliases_path.unlink()
            return

        canonical = qid
        path = self._entity_path(canonical)
        if path.exists():
            path.unlink()
        changed = False
        for alias, target in list(aliases.items()):
            if target == canonical:
                del aliases[alias]
                changed = True
        if changed:
            if aliases:
                self._atomic_json(self.aliases_path, aliases)
            elif self.aliases_path.exists():
                self.aliases_path.unlink()

    def clear(self) -> None:
        if self.entities_dir.exists():
            for path in self.entities_dir.glob("*.json"):
                path.unlink()
        if self.aliases_path.exists():
            self.aliases_path.unlink()
