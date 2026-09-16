import json
from pathlib import Path
import unittest

from scholiator import bibtex
from scholiator.model import BibliographicRecord, Name
from scholiator.normalize import normalize_work

FIXTURES = Path(__file__).parent / "fixtures" / "wikidata"


def load(qid):
    return json.loads((FIXTURES / f"{qid}.json").read_text(encoding="utf-8"))


class BibtexTests(unittest.TestCase):
    def test_ascii_and_fields(self):
        lookup = {qid: load(qid) for qid in ["Q100", "Q200", "Q201", "Q202", "Q300", "Q400", "Q500"]}
        record = normalize_work("Q100", lookup["Q100"], lookup).record
        text = bibtex.render(record)
        text.encode("ascii")
        self.assertIn("@article{Q100,", text)
        self.assertIn(r"title = {{Secure \^{} title}}", text)
        self.assertIn(r"journal = {Journal \& Tests}", text)
        self.assertIn(r"doi = {10.1234/ABC\_DEF}", text)
        self.assertIn("wikidata = {Q100}", text)
        self.assertIn(r'Ex\"{a}mple, Ada', text)

    def test_middle_name_is_preserved_in_structured_name(self):
        record = BibliographicRecord(
            citation_key="Q1",
            canonical_qid="Q1",
            entry_type="article",
            title="Title",
            authors=(Name(given="Finn Årup", family="Nielsen"),),
        )
        text = bibtex.render(record)
        self.assertIn(r"author = {Nielsen, Finn {\AA}rup}", text)

    def test_redirect_key_and_canonical_wikidata_field(self):
        record = BibliographicRecord(
            citation_key="Q1", canonical_qid="Q2", entry_type="article", title="Title"
        )
        text = bibtex.render(record)
        self.assertIn("@article{Q1,", text)
        self.assertIn("wikidata = {Q2}", text)


if __name__ == "__main__":
    unittest.main()
