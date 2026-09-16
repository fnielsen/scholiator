# Implement Scholiator 0.1

Build **Scholiator**, a small, security-conscious Python command-line program that generates `.bib` bibliography files from Wikidata items cited by QID in LaTeX documents.

Implement a complete, usable version 0.1, including tests and documentation. Prefer simple, readable Python over abstractions that are not yet needed.

## Core constraints

* Python >= 3.10.
* No mandatory third-party runtime dependencies.
* Prefer the Python standard library throughout.
* Standard tests must run without network access.
* Do not use the Wikidata SPARQL endpoint.
* Do not generate `.bbl` files.
* Do not implement DOI-to-Wikidata lookup in version 0.1.
* Do not interpret Wikidata P6835 (`title in LaTeX`) in version 0.1.
* Do not parse or merge existing hand-written `.bib` files.
* Treat all data obtained from Wikidata as untrusted input.

Use `unittest` unless there is a compelling reason not to, so that the test suite itself has no mandatory third-party dependencies.

---

# 1. Intended workflow

A LaTeX document may contain citations such as:

```tex
\cite{Q130361570}
\cite{Q130361570,Q1234567}
```

or mixed ordinary and Wikidata bibliography keys:

```tex
\cite{Smith2020,Q130361570,local-report}
```

Scholiator should extract only valid Wikidata item IDs. The last example therefore yields only:

```text
Q130361570
```

Non-QID citation keys are silently ignored.

QIDs should match the strict form:

```text
Q[1-9][0-9]*
```

Preserve first citation order while removing duplicate QIDs.

The normal processing pipeline is:

```text
AUX / BCF
    |
citation discovery
    |
QIDs
    |
cache lookup / wbgetentities
    |
raw Wikibase entities
    |
Wikidata normalization
    |
BibliographicRecord
    |
    +-- BibTeX renderer   -> TeX-safe ASCII
    |
    +-- biblatex renderer -> TeX-safe UTF-8
    |
   .bib
```

---

# 2. Command-line interface

Implement an executable named:

```text
scholiator
```

Support:

```text
scholiator paper
scholiator paper.aux
scholiator paper.bcf

scholiator --offline paper
scholiator --refresh paper

scholiator --format=bibtex paper
scholiator --format=biblatex paper

scholiator -o references.bib paper
scholiator --output references.bib paper

scholiator cache refresh Q130361570
scholiator cache remove Q130361570
scholiator cache clear
```

When given a basename such as:

```text
scholiator paper
```

resolve citation input as follows:

1. use `paper.bcf` if it exists;
2. otherwise use `paper.aux`;
3. otherwise fail clearly.

If `paper.aux` or `paper.bcf` is explicitly supplied, use exactly that file.

Input format and output format are independent. For example, reading a `.bcf` does not itself force `--format=biblatex`.

The default output is:

```text
paper.bib
```

unless overridden with `-o` / `--output`.

The output file belongs to Scholiator. Generate it from scratch. Do not parse, merge, or preserve manually edited entries in an existing output file.

Write output atomically:

```text
generate -> validate -> temporary file -> os.replace()
```

A failed run must not destroy a previously usable `.bib` file.

Use `argparse`.

Suggested exit behavior:

* `0`: successful generation; warnings may have occurred.
* `1`: bibliography could not safely be generated.
* `2`: command-line/configuration error, where appropriate.

Diagnostics and warnings go to stderr.

---

# 3. Suggested package structure

Use a modular structure approximately like:

```text
scholiator/
    __init__.py
    __main__.py
    cli.py
    citation.py
    config.py
    cache.py
    wikidata.py
    model.py
    normalize.py
    escaping.py
    bibtex.py
    biblatex.py

tests/
    test_citation.py
    test_cache.py
    test_wikidata.py
    test_normalize.py
    test_escaping.py
    test_bibtex.py
    test_biblatex.py
    test_cli.py

    fixtures/
        aux/
        bcf/
        wikidata/
```

This is a guideline, not an obligation. Keep responsibilities separate and avoid putting the whole application into one file.

Important separation:

```text
raw Wikidata JSON
        |
        v
BibliographicRecord
        |
        +--> BibTeX renderer
        +--> biblatex renderer
```

The canonical model must contain ordinary Unicode data and must not contain pre-escaped TeX.

---

# 4. Citation discovery

## Traditional BibTeX / natbib AUX

Recognize ordinary citation records such as:

```tex
\citation{Q1,Q2}
\citation{Q3}
```

Support multiple records and comma-separated keys.

Support subordinate AUX files referenced by records such as:

```tex
\@input{chapter1.aux}
```

Process subordinate AUX files recursively.

Do NOT execute or interpret TeX.

Recognize only explicitly supported AUX records.

Protect against path traversal:

* normalize included paths;
* restrict subordinate AUX files to the project/document area;
* prevent cycles;
* do not follow arbitrary system paths.

## biblatex / Biber

Prefer the `.bcf` file.

Use the Python standard library XML parser (`xml.etree.ElementTree`) and extract Biber citation keys, typically from elements whose local name is `citekey`.

Ignore non-QID citekeys.

Do not depend on internal biblatex AUX macros if `.bcf` support is sufficient for version 0.1.

---

# 5. Wikidata access

Use the Wikidata Action API `wbgetentities`.

Do not use SPARQL.

Use `urllib.request`, `json`, and other standard-library modules.

Batch QIDs conservatively rather than making one request per entity.

Use a descriptive User-Agent containing:

* Scholiator;
* its version;
* a project/contact URL.

Keep the project/contact URL in one obvious constant or configuration location so it is easy to change.

For Action API requests:

* include `maxlag`;
* request HTTP compression;
* use serial or very low-concurrency access;
* honor HTTP `429` and `Retry-After`;
* use reasonable timeouts;
* retry transient failures conservatively;
* do not retry permanent client errors indefinitely.

The network layer should be independently testable with mocked responses.

`Special:EntityData` may be added later or as a diagnostic helper, but `wbgetentities` is the normal data source.

---

# 6. Fetch related entities

Fetching only the cited work entities is not sufficient.

Properties such as:

* P50 author,
* P98 editor,
* P123 publisher,
* P1433 published in,
* P407 language of work,

refer to other Wikidata entities whose labels or claims may be required.

Implement a bounded dependency-expansion step:

1. fetch cited work entities;
2. inspect only the known bibliographic properties;
3. collect referenced QIDs needed for normalization/rendering;
4. batch-fetch missing referenced entities;
5. cache them.

Do not implement arbitrary recursive Wikidata graph traversal.

If additional entities such as given-name/family-name or language entities are needed by a clearly defined normalization rule, fetch them in another bounded batch.

---

# 7. Cache

Cache raw Wikibase entities, not generated bibliography data.

Prefer one cached canonical entity per file, for example conceptually:

```text
cache/
    entities/
        Q130361570.json
        Q1234567.json
```

A batched `wbgetentities` response should therefore be split into individual entity cache records.

Do not cache `BibliographicRecord` objects or `.bib` output.

Use a sensible user cache directory. On Unix-like systems, respect `XDG_CACHE_HOME` when set and otherwise use an appropriate user cache location.

Configuration may override `cache_dir`.

Do not require automatic cache expiration in version 0.1. Cached data remains valid until explicitly refreshed.

Semantics:

```text
--offline
```

means:

* make no network requests;
* use cached data only;
* fail if required data are not available.

```text
--refresh
```

means:

* re-fetch all entities needed for the current bibliography regardless of cache contents.

Support:

```text
scholiator cache refresh QID
scholiator cache remove QID
scholiator cache clear
```

## Redirects and merges

Suppose the document cites:

```tex
\cite{Q123}
```

but Q123 now redirects to Q456.

Use Q456's bibliographic information, but preserve the user's citation key:

```bibtex
@article{Q123,
    ...
    wikidata = {Q456},
}
```

Internally distinguish at least:

```text
citation_key = Q123
canonical_qid = Q456
```

Because offline operation must also work after redirects have been encountered, maintain minimal cache metadata mapping requested/alias QIDs to canonical QIDs if necessary.

---

# 8. Configuration

Use a small INI configuration via the standard-library `configparser`.

A possible initial configuration is:

```ini
[scholiator]
format = bibtex
label_languages = en,mul
title_languages = en,mul
cache_dir = ...
```

Use sensible built-in defaults.

Configuration precedence should be:

```text
command line > configuration file > defaults
```

Do not introduce many options in version 0.1.

In particular, avoid implementing elaborate author-presentation options until needed. Bibliography styles should normally decide whether names print as `Given Family`, `Family, Given`, initials, etc.

---

# 9. Canonical data model

Use dataclasses where appropriate.

Create a renderer-independent `BibliographicRecord`.

It should be capable of representing at least:

* citation key;
* canonical Wikidata QID;
* bibliography type;
* title;
* authors;
* editors;
* publication date;
* container/journal/book title;
* publisher;
* volume;
* issue/number;
* pages;
* DOI;
* ISBN;
* URL;
* language.

Use an `Author`/`Name` structure capable of distinguishing structured person names from literal/unparsed names, for example conceptually:

```python
@dataclass
class Name:
    given: str | None = None
    family: str | None = None
    literal: str | None = None
    is_organization: bool = False
```

Do not invent given/family components when Wikidata does not provide reliable information.

---

# 10. Wikidata property handling

At minimum consider these properties where appropriate:

```text
P31    instance of
P50    author
P98    editor
P2093  author name string
P1932  object named as          (qualifier)
P1545  series ordinal           (qualifier)
P1476  title
P577   publication date
P1433  published in
P123   publisher
P407   language of work or name
P478   volume
P433   issue
P304   page(s)
P356   DOI
P212   ISBN-13
P957   ISBN-10
P953   full work available at URL
```

Only implement mappings that are bibliographically defensible. It is better to omit uncertain data with a warning than invent a value.

---

# 11. Author handling

Authors may come from P50 and/or P2093.

Preserve authors rather than trying to perform aggressive entity resolution.

Ordering:

* use P1545 (`series ordinal`) when available;
* preserve explicit series ordinals;
* when ordinals are absent or insufficient, use statement/JSON serialization order only as a deterministic fallback;
* do not claim that JSON order has semantic meaning.

P1932 (`object named as`) on a P50 statement may provide the name as it appeared in the work and may be preferable to a current entity label.

A reasonable name-source priority is:

```text
P50 statement with useful P1932
    ->
reliable structured/name information from the P50 entity
    ->
appropriate entity label

P2093 remains a literal author-name statement.
```

Do not collapse P50 and P2093 merely because their strings look similar.

If statements have the same explicit P1545 but conflict, preserve data where possible and emit a warning rather than silently choosing one.

Authors can be organizations. Do not force organization names through person-name parsing.

---

# 12. Language handling

Configuration:

```text
label_languages = en,mul
title_languages = en,mul
```

Distinguish title-language selection from labels for linked entities.

For titles:

1. prefer a P1476 title whose language agrees with the work language P407 when this can be determined reliably;
2. otherwise use configured `title_languages` order;
3. otherwise use a clearly documented deterministic fallback or fail if no usable title exists.

For labels of publisher, venue, etc., use `label_languages`.

If useful, P407 language entities may be inspected for language-code information, but do not build a general ontology/language inference system.

---

# 13. Bibliographic type mapping

Use a curated exact mapping of supported Wikidata class QIDs.

Do not perform general P279/subclass reasoning at runtime in version 0.1.

Initial mapping:

```text
Q13442814  scholarly article   -> article
Q23927052  conference paper    -> inproceedings
Q571       book                -> book
Q1980247   chapter             -> incollection
Q187685    doctoral thesis     -> phdthesis / thesis
Q1907875   master's thesis     -> mastersthesis / thesis
Q798134    bachelor's thesis   -> thesis or misc
Q10870555  report              -> techreport / report
Q7397      software            -> misc / software
```

Make the mapping easy to extend with additional specific Wikidata classes later.

If several supported P31 values imply conflicting bibliography types, warn/fail rather than silently choosing an arbitrary type.

If no supported type is found, do not silently treat everything as `article` or `misc`.

---

# 14. Wikidata rank handling

Do not use one global "preferred beats everything" rule for all properties.

General policy:

* ignore deprecated-rank statements;
* for properties representing alternative values, use preferred-rank statements when present, otherwise normal-rank statements;
* for inherently multi-valued properties such as authors/editors, retain all relevant non-deprecated statements unless a specific property rule says otherwise.

Implement rank handling in a way that allows property-specific behavior.

---

# 15. Output formats

Implement two renderers.

## `--format=bibtex`

Traditional BibTeX-oriented output.

* Output must be ASCII only.
* Convert supported Unicode characters into safe TeX representations.
* Never silently transliterate or drop unsupported characters.
* If a character cannot safely be represented, report a clear error/warning according to whether generation can remain correct.

Examples of conversions may use Unicode normalization plus an explicit mapping for supported characters/combining marks.

## `--format=biblatex`

Output intended for biblatex + Biber.

* Output is UTF-8.
* Preserve ordinary Unicode characters.
* Still escape TeX-sensitive syntax safely.

The two renderers may also differ semantically, for example:

```text
BibTeX:    journal, year, techreport, phdthesis
biblatex:  journaltitle, date, report, thesis, software
```

Do not treat biblatex as merely "BibTeX with UTF-8".

Both should emit:

```text
wikidata = {Q...}
```

where appropriate.

---

# 16. Security requirements

Security is a primary requirement.

All Wikidata-derived text is untrusted.

Never copy arbitrary Wikidata strings directly into TeX/BibTeX output.

In particular handle safely:

```text
\
{
}
%
#
$
&
_
^
~
^^
```

Pay particular attention to TeX's early `^^` processing.

Reject or safely encode:

* NUL;
* ASCII control characters;
* unexpected line-control characters;
* other input that could alter generated bibliography syntax.

Do not interpret Wikidata P6835 (`title in LaTeX`) in version 0.1.

P6835 should simply be ignored.

Escaping should be field-sensitive rather than blindly applying one transformation everywhere.

Conceptually:

```text
ordinary text -> escape_text()
names         -> encode_name()
URLs          -> escape_url()
identifiers   -> validate_identifier()
```

The canonical `BibliographicRecord` contains unescaped Unicode. Escaping happens only when rendering.

No untrusted Wikidata value may become executable TeX syntax.

---

# 17. Failure policy

Be conservative.

Missing optional fields may simply be omitted.

Warn conspicuously about questionable but potentially recoverable data, such as:

* incomplete author ordering;
* duplicate series ordinals;
* conflicting optional values.

Fail rather than manufacture plausible-looking bibliography data when essential information is unavailable or unsafe, for example:

* cited Wikidata item cannot be obtained;
* required cache item missing in offline mode;
* no usable title;
* unsupported/ambiguous bibliographic type;
* malformed Wikidata data required for generation;
* character cannot safely be represented in strict BibTeX output.

A failed generation must not replace the existing output file.

Do not treat ordinary non-QID citation keys such as `Smith2020` as errors.

---

# 18. Tests

Create a comprehensive offline test suite.

Standard unit/integration tests MUST NOT contact Wikimedia.

Use stored AUX, BCF, and Wikidata JSON fixtures.

Include tests for at least:

```text
\citation{Q1,Q2}

separate natbib-style:
\citation{Q1}
\citation{Q2}

mixed keys:
\citation{Smith2020,Q1,local-report}

duplicate citations

recursive \@input{chapter1.aux}

attempted AUX path traversal

BCF citekeys

redirected/merged QIDs

offline cache hit
offline cache miss
refresh behavior

P50 authors
P2093 authors
mixed P50/P2093
P1932
P1545 ordering
missing P1545
duplicate/conflicting P1545

preferred/normal/deprecated ranks

supported and unsupported P31 classes

language selection

BibTeX ASCII output
biblatex UTF-8 output

TeX-sensitive input:
\
%
#
$
&
_
{
}
^
~
^^

NUL/control characters

accented Latin characters

unsupported non-ASCII characters in BibTeX mode
```

Optional live-Wikidata tests may exist but must not run as part of the normal test suite.

---

# 19. Implementation approach

Please implement rather than only describe the design.

Work incrementally, but leave the repository in a functioning state.

Suggested order:

1. package skeleton and CLI;
2. AUX/BCF citation extraction;
3. canonical data model;
4. cache;
5. Wikidata API client;
6. bounded fetching of linked entities;
7. normalization/property extraction;
8. secure escaping;
9. BibTeX renderer;
10. biblatex renderer;
11. atomic output;
12. complete offline tests;
13. README with installation and usage examples.

Keep functions small and type-annotated where useful.

Use clear docstrings.

Avoid speculative functionality outside version 0.1.

If a requirement is ambiguous, choose the simplest conservative behavior consistent with data integrity and security, document that choice in the code/README, and continue implementation rather than broadening the scope.

At completion, show:

1. the resulting file/module structure;
2. important design decisions made;
3. commands to run the tests;
4. a minimal end-to-end usage example;
5. any intentionally deferred version-0.1 limitations.
