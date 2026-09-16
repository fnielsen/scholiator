"""Configuration loading for Scholiator."""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    format: str = "bibtex"
    label_languages: tuple[str, ...] = ("en", "mul")
    title_languages: tuple[str, ...] = ("en", "mul")
    cache_dir: Path | None = None


def default_cache_dir() -> Path:
    """Return the platform-appropriate default cache directory."""
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg) / "scholiator"
    return Path.home() / ".cache" / "scholiator"


def default_config_path() -> Path:
    """Return the default INI configuration path."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "scholiator" / "config.ini"
    return Path.home() / ".config" / "scholiator" / "config.ini"


def _languages(value: str, default: tuple[str, ...]) -> tuple[str, ...]:
    result = tuple(part.strip() for part in value.split(",") if part.strip())
    return result or default


def load_config(path: Path | None = None) -> Config:
    """Load configuration, returning defaults when no file exists."""
    path = path or default_config_path()
    parser = configparser.ConfigParser()
    if path.exists():
        parser.read(path, encoding="utf-8")

    section = parser["scholiator"] if parser.has_section("scholiator") else {}
    fmt = str(section.get("format", "bibtex")).strip().lower()
    if fmt not in {"bibtex", "biblatex"}:
        raise ValueError(f"Unsupported configured format: {fmt}")

    label_languages = _languages(
        str(section.get("label_languages", "en,mul")), ("en", "mul")
    )
    title_languages = _languages(
        str(section.get("title_languages", "en,mul")), ("en", "mul")
    )
    configured_cache = str(section.get("cache_dir", "")).strip()
    cache_dir = Path(configured_cache).expanduser() if configured_cache else default_cache_dir()
    return Config(
        format=fmt,
        label_languages=label_languages,
        title_languages=title_languages,
        cache_dir=cache_dir,
    )
