import json
from pathlib import Path
import unittest

from scholiator import biblatex
from scholiator.normalize import normalize_work

FIXTURES = Path(__file__).parent / "fixtures" / "wikidata"


def load(qid):
    return json.loads((FIXTURES / f"{qid}.json").read_text(encoding="utf-8"))


class BiblatexTests(unittest.TestCase):
    def test_utf8_and_biblatex_fields(self):
        lookup = {qid: load(qid) for qid in ["Q100", "Q200", "Q201", "Q202", "Q300", "Q400", "Q500"]}
        record = normalize_work("Q100", lookup["Q100"], lookup).record
        text = biblatex.render(record)
        self.assertIn("Exämple, Ada", text)
        self.assertIn("journaltitle", text)
        self.assertIn("date = {2026-09-16}", text)
        self.assertIn(r"Secure \^{} title", text)


if __name__ == "__main__":
    unittest.main()
