import copy
import json
from pathlib import Path
import unittest

from scholiator.normalize import NormalizationError, collect_name_part_qids, collect_related_qids, normalize_work

FIXTURES = Path(__file__).parent / "fixtures" / "wikidata"


def load(qid):
    return json.loads((FIXTURES / f"{qid}.json").read_text(encoding="utf-8"))


def lookup():
    return {qid: load(qid) for qid in ["Q100", "Q200", "Q201", "Q202", "Q300", "Q400", "Q500"]}


class NormalizeTests(unittest.TestCase):
    def test_related_dependency_collection(self):
        self.assertEqual(
            collect_related_qids([load("Q100")]),
            ["Q200", "Q500", "Q300", "Q400"],
        )
        self.assertEqual(set(collect_name_part_qids([load("Q200")])), {"Q201", "Q202"})

    def test_article_normalization(self):
        result = normalize_work("Q100", load("Q100"), lookup())
        record = result.record
        self.assertEqual(record.entry_type, "article")
        self.assertEqual(record.title, "Secure ^ title")
        self.assertEqual(record.year, "2026")
        self.assertEqual(record.date, "2026-09-16")
        self.assertEqual(record.container_title, "Journal & Tests")
        self.assertEqual(record.publisher, "Publisher #1")
        self.assertEqual(record.authors[0].given, "Ada")
        self.assertEqual(record.authors[0].family, "Exämple")
        self.assertEqual(record.authors[1].literal, "Anonymous Contributor")
        self.assertEqual(record.language, "English")

    def test_p1932_preferred_for_stated_author_name(self):
        work = load("Q100")
        work["claims"]["P50"][0].setdefault("qualifiers", {})["P1932"] = [
            {"snaktype": "value", "property": "P1932", "datavalue": {"value": {"text": "A. Example", "language": "en"}, "type": "monolingualtext"}}
        ]
        result = normalize_work("Q100", work, lookup())
        self.assertEqual(result.record.authors[0].literal, "A. Example")

    def test_duplicate_series_ordinal_warns(self):
        work = load("Q100")
        work["claims"]["P2093"][0]["qualifiers"]["P1545"][0]["datavalue"]["value"] = "1"
        result = normalize_work("Q100", work, lookup())
        self.assertTrue(any("Duplicate series ordinal" in warning for warning in result.warnings))

    def test_deprecated_author_ignored(self):
        work = load("Q100")
        deprecated = copy.deepcopy(work["claims"]["P2093"][0])
        deprecated["rank"] = "deprecated"
        deprecated["mainsnak"]["datavalue"]["value"] = "Bad Author"
        work["claims"]["P2093"].append(deprecated)
        result = normalize_work("Q100", work, lookup())
        self.assertNotIn("Bad Author", [name.literal for name in result.record.authors])

    def test_preferred_title_selected(self):
        work = load("Q100")
        work["claims"]["P1476"] = [
            {"rank":"normal","mainsnak":{"snaktype":"value","property":"P1476","datavalue":{"value":{"text":"Normal","language":"en"},"type":"monolingualtext"}}},
            {"rank":"preferred","mainsnak":{"snaktype":"value","property":"P1476","datavalue":{"value":{"text":"Preferred","language":"en"},"type":"monolingualtext"}}},
        ]
        self.assertEqual(normalize_work("Q100", work, lookup()).record.title, "Preferred")

    def test_conflicting_supported_types_fail(self):
        work = load("Q100")
        extra = copy.deepcopy(work["claims"]["P31"][0])
        extra["mainsnak"]["datavalue"]["value"]["id"] = "Q571"
        work["claims"]["P31"].append(extra)
        with self.assertRaises(NormalizationError):
            normalize_work("Q100", work, lookup())

    def test_unsupported_type_fails(self):
        work = load("Q100")
        work["claims"]["P31"][0]["mainsnak"]["datavalue"]["value"]["id"] = "Q999"
        with self.assertRaises(NormalizationError):
            normalize_work("Q100", work, lookup())


if __name__ == "__main__":
    unittest.main()
