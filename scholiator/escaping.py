"""Security-sensitive TeX/BibTeX escaping."""

from __future__ import annotations

import re
import unicodedata


class EscapingError(ValueError):
    """Raised when untrusted text cannot be represented safely."""


_SPECIAL = {
    "\\": r"\textbackslash{}",
    ">": r"\textgreater{}",
    "<": r"\textless{}",
    "{": r"\{",
    "}": r"\}",
    "%": r"\%",
    "#": r"\#",
    "$": r"\$",
    "&": r"\&",
    "_": r"\_",
    "^": r"\^{}",
    "~": r"\~{}",
}

_COMBINING = {
    "\u0300": r"\`",
    "\u0301": r"\'",
    "\u0302": r"\^",
    "\u0303": r"\~",
    "\u0304": r"\=",
    "\u0306": r"\u",
    "\u0307": r"\.",
    "\u0308": r'\"',
    "\u030a": r"\r",
    "\u030b": r"\H",
    "\u030c": r"\v",
    "\u0323": r"\d",
    "\u0327": r"\c",
    "\u0328": r"\k",
    "\u0331": r"\b",
}

_DIRECT_ASCII_TEX = {
    "Å": r"{\AA}",
    "å": r"{\aa}",
    "Æ": r"{\AE}",
    "æ": r"{\ae}",
    "Ø": r"{\O}",
    "ø": r"{\o}",
    "Œ": r"{\OE}",
    "œ": r"{\oe}",
    "ß": r"{\ss}",
    "Ł": r"{\L}",
    "ł": r"{\l}",
    "Ð": r"{\DH}",
    "ð": r"{\dh}",
    "Þ": r"{\TH}",
    "þ": r"{\th}",
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "¹": r"{\textsuperscript{1}}",
    "²": r"{\textsuperscript{2}}",
    "³": r"{\textsuperscript{3}}",
    "’": "'",
    "–": "--",
    "‐": "-",
}

_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
_ISBN_RE = re.compile(r"^[0-9Xx -]+$")


def _validate_controls(value: str) -> None:
    for char in value:
        code = ord(char)
        category = unicodedata.category(char)
        if code < 32 or code == 127 or category in {"Cc", "Cf", "Cs", "Zl", "Zp"}:
            raise EscapingError(f"Control/format character U+{code:04X} is not allowed")


def escape_doi(value: str, *, ascii_only: bool = False) -> str:
    """Validate a DOI for safe inclusion in a .bib field.

    DOI punctuation such as _, /, ., (, ), :, and ; is preserved.
    Characters that could introduce TeX syntax or break the BibTeX
    field structure are rejected rather than rewritten.
    """
    value = validate_doi(value)

    if "^^" in value:
        raise EscapingError("Unsafe TeX ^^ sequence in DOI")
        
    for char in value:
        code = ord(char)

        if code == 0 or code < 0x20 or code == 0x7F:
            raise EscapingError(
                f"Unsafe control character U+{code:04X} in DOI"
            )

        if ascii_only and code > 0x7F:
            raise EscapingError(
                f"No safe ASCII representation for U+{code:04X} {char!r} in DOI"
            )

        # Do not turn DOI punctuation such as "_" into TeX commands.
        # Reject characters capable of injecting/breaking TeX/BibTeX syntax.
        for char in "\\{}":
            if char in value:
                raise EscapingError(
                    f"Unsafe character {char!r} in DOI"
                )

    return value
        

def escape_text(value: str, *, ascii_only: bool) -> str:
    """Escape untrusted ordinary text for safe use in TeX bibliography fields.

    In UTF-8 mode, ordinary Unicode characters are preserved while
    TeX-special characters are escaped. In ASCII-only mode, supported
    non-ASCII characters are converted to TeX representations.

    Accented characters are handled using Unicode NFD normalization.
    This also supports characters with multiple combining marks. For
    example, ``ễ`` (U+1EC5) decomposes into ``e`` plus combining
    circumflex and combining tilde and is rendered as ``\\~{\\^{e}}``.

    Parameters
    ----------
    value : str
        Untrusted Unicode text to escape.
    ascii_only : bool
        If True, require ASCII-only output and represent supported
        non-ASCII characters using TeX commands. If False, preserve
        ordinary Unicode characters.

    Returns
    -------
    str
        TeX-safe representation of `value`.

    Raises
    ------
    EscapingError
        If the input contains unsafe control characters or, in
        ASCII-only mode, a character for which no safe representation
        is known.

    Examples
    --------
    Unicode is retained in UTF-8 mode:

    >>> escape_text("Nguyễn", ascii_only=False)
    'Nguyễn'

    Multiple combining marks are converted to nested TeX accents:

    >>> escape_text("Nguyễn", ascii_only=True)
    'Nguy\\\\~{\\\\^{e}}n'

    Simpler accented characters use the same mechanism:

    >>> escape_text("é", ascii_only=True)
    "\\\\'{e}"

    TeX-special characters are escaped:

    >>> escape_text("A & B", ascii_only=True)
    'A \\\\& B'
    """
    _validate_controls(value)
    if not ascii_only:
        return "".join(_SPECIAL.get(char, char) for char in value)

    result: list[str] = []
    for original in value:
        if original in _SPECIAL:
            result.append(_SPECIAL[original])
            continue
        if ord(original) < 128:
            result.append(original)
            continue
        if original in _DIRECT_ASCII_TEX:
            result.append(_DIRECT_ASCII_TEX[original])
            continue

        decomposed = unicodedata.normalize("NFD", original)
        if decomposed and ord(decomposed[0]) < 128 and len(decomposed) > 1:
            base = decomposed[0]
            marks = decomposed[1:]
            expression = base
            supported = True
            for mark in marks:
                macro = _COMBINING.get(mark)
                if macro is None:
                    supported = False
                    break
                expression = macro + "{" + expression + "}"
            if supported:
                result.append(expression)
                continue
        raise EscapingError(f"No safe ASCII TeX representation for U+{ord(original):04X} {original!r}")
    rendered = "".join(result)
    try:
        rendered.encode("ascii")
    except UnicodeEncodeError as exc:  # defensive invariant
        raise EscapingError("ASCII renderer produced non-ASCII output") from exc
    return rendered


def escape_url(value: str, *, ascii_only: bool) -> str:
    """Escape a URL-like field without allowing TeX syntax injection."""
    _validate_controls(value)
    # URLs may legitimately contain many punctuation characters; protect only
    # TeX syntax characters and rely on the field consumer for URL semantics.
    return escape_text(value, ascii_only=ascii_only)


def validate_doi(value: str) -> str:
    _validate_controls(value)
    value = value.strip()
    if not _DOI_RE.fullmatch(value):
        raise EscapingError(f"Invalid DOI: {value!r}")
    return value


def validate_isbn(value: str) -> str:
    _validate_controls(value)
    value = value.strip()
    if not _ISBN_RE.fullmatch(value):
        raise EscapingError(f"Invalid ISBN: {value!r}")
    return value
