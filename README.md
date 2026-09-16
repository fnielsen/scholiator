# Scholiator

Scholiator 0.1 is a small Python command-line tool that generates `.bib` files from Wikidata QIDs cited by LaTeX documents.

It intentionally does **not** use SPARQL, generate `.bbl` files, perform DOI-to-QID lookup, or interpret Wikidata's `title in LaTeX` property (P6835).

## Requirements

- Python 3.10 or newer
- no mandatory third-party runtime dependencies

## Installation

From the project directory:

```sh
python -m pip install .
```

For development you can also run it without installing:

```sh
python -m scholiator --help
```

## Usage

Given a LaTeX run that produced `paper.aux`:

```tex
\cite{Q130361570}
```

run:

```sh
scholiator paper
```

Scholiator prefers `paper.bcf` when present, otherwise `paper.aux`, and writes `paper.bib`.

Explicit inputs and output:

```sh
scholiator paper.aux
scholiator paper.bcf
scholiator -o references.bib paper
```

Output modes:

```sh
scholiator --format=bibtex paper
scholiator --format=biblatex paper
```

- `bibtex`: ASCII-only, TeX-safe output.
- `biblatex`: UTF-8, TeX-safe output intended for Biber.

Mixed citation keys are allowed. Only strict Wikidata item IDs are handled:

```tex
\cite{Smith2020,Q130361570,local-report}
```

Scholiator handles only `Q130361570` and ignores the other two keys.

## Cache and offline builds

Raw Wikibase entities are cached individually. The default Unix cache location is `$XDG_CACHE_HOME/scholiator` when `XDG_CACHE_HOME` is set, otherwise `~/.cache/scholiator`.

```sh
scholiator --offline paper
scholiator --refresh paper
scholiator cache refresh Q130361570
scholiator cache remove Q130361570
scholiator cache clear
```

`--offline` makes no network requests and fails if required entities are absent. `--refresh` re-fetches all entities required for the current bibliography.

## Configuration

The default Unix configuration file is `$XDG_CONFIG_HOME/scholiator/config.ini`, or `~/.config/scholiator/config.ini` when `XDG_CONFIG_HOME` is not set.

```ini
[scholiator]
format = bibtex
label_languages = en,mul
title_languages = en,mul
cache_dir = /optional/custom/cache
```

Use `--config FILE` to select another INI file. Command-line options override configuration values.

## Security model

Wikidata is untrusted input. Scholiator keeps raw Unicode data in its internal model and performs field-sensitive escaping only at the rendering boundary. TeX metacharacters, including carets involved in TeX's early `^^` processing, are escaped. ASCII control characters are rejected. P6835 is ignored.

Included AUX files referenced through `\@input{...}` are treated as data only, restricted to the project directory, and never interpreted as TeX.

Output replacement is atomic: a failed generation does not overwrite the previous `.bib` file.

## Wikidata access

Scholiator uses the Wikidata Action API `wbgetentities`, batches requests, sends a descriptive User-Agent, uses `maxlag`, requests compression, and backs off on transient HTTP failures including 429 responses. It does not use WDQS/SPARQL.

The User-Agent project URL is centralized in `scholiator/wikidata.py` and should be updated when Scholiator gets its own canonical project URL.

## Tests

The standard test suite is entirely offline:

```sh
python -m unittest discover -v
```

Fixtures under `tests/fixtures/` cover AUX/BCF parsing and synthetic Wikibase entities.

## Version 0.1 limitations

- no DOI-to-QID lookup;
- no `.bbl` generation;
- no existing `.bib` merge/preservation;
- no general P279/subclass reasoning;
- no interpretation of P6835;
- deliberately bounded fetching of linked bibliographic entities;
- curated bibliographic type mapping only;
- traditional BibTeX mode supports only Unicode characters for which Scholiator has an explicit safe ASCII/TeX representation.
