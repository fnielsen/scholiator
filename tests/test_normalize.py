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


    def test_entity_name_uses_label_to_restore_middle_name(self):
        entities = lookup()
        entities["Q200"]["labels"]["en"]["value"] = "Ada Marie Exämple"
        result = normalize_work("Q100", entities["Q100"], entities)
        self.assertEqual(result.record.authors[0].given, "Ada Marie")
        self.assertEqual(result.record.authors[0].family, "Exämple")

    def test_entity_with_missing_family_name_uses_full_label(self):
        entities = lookup()
        entities["Q200"]["claims"].pop("P734")
        entities["Q200"]["labels"]["en"]["value"] = "Ada Marie Example"
        result = normalize_work("Q100", entities["Q100"], entities)
        self.assertEqual(result.record.authors[0].literal, "Ada Marie Example")
        self.assertIsNone(result.record.authors[0].given)
        self.assertIsNone(result.record.authors[0].family)

    def test_p50_wins_over_p2093_at_same_explicit_ordinal(self):
        work = load("Q100")
        duplicate = copy.deepcopy(work["claims"]["P2093"][0])
        duplicate["mainsnak"]["datavalue"]["value"] = "Ada Example"
        duplicate["qualifiers"]["P1545"][0]["datavalue"]["value"] = "1"
        work["claims"]["P2093"].insert(0, duplicate)
        result = normalize_work("Q100", work, lookup())
        rendered = [name.literal or f"{name.given} {name.family}" for name in result.record.authors]
        self.assertEqual(rendered.count("Ada Exämple"), 1)
        self.assertNotIn("Ada Example", rendered)
        self.assertTrue(any("same ordinal" in warning for warning in result.warnings))

    def test_duplicate_series_ordinal_warns(self):
        work = load("Q100")
        duplicate = copy.deepcopy(work["claims"]["P2093"][0])
        duplicate["mainsnak"]["datavalue"]["value"] = "Second Literal Author"
        work["claims"]["P2093"].append(duplicate)
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

    def test_article_and_chapter_selects_incollection(self):
        work = load("Q100")
        extra = copy.deepcopy(work["claims"]["P31"][0])
        extra["mainsnak"]["datavalue"]["value"]["id"] = "Q1980247"
        work["claims"]["P31"].append(extra)
        result = normalize_work("Q100", work, lookup())
        self.assertEqual(result.record.entry_type, "incollection")
        self.assertTrue(any("selected incollection" in warning for warning in result.warnings))

    def test_proceedings_container_selects_inproceedings(self):
        work = load("Q100")
        extra = copy.deepcopy(work["claims"]["P31"][0])
        extra["mainsnak"]["datavalue"]["value"]["id"] = "Q1980247"
        work["claims"]["P31"].append(extra)

        entities = lookup()
        entities["Q300"]["claims"]["P4745"] = [
            {
                "rank": "normal",
                "mainsnak": {
                    "snaktype": "value",
                    "property": "P4745",
                    "datavalue": {
                        "value": {"entity-type": "item", "numeric-id": 999, "id": "Q999"},
                        "type": "wikibase-entityid",
                    },
                },
            }
        ]
        result = normalize_work("Q100", work, entities)
        self.assertEqual(result.record.entry_type, "inproceedings")
        self.assertTrue(any("P4745" in warning for warning in result.warnings))

    def test_unrelated_conflicting_supported_types_fail_with_identifier(self):
        work = load("Q100")
        extra = copy.deepcopy(work["claims"]["P31"][0])
        extra["mainsnak"]["datavalue"]["value"]["id"] = "Q571"
        work["claims"]["P31"].append(extra)
        with self.assertRaisesRegex(NormalizationError, r"Q100: conflicting supported bibliographic types"):
            normalize_work("Q100", work, lookup())

    def test_unsupported_type_fails_with_identifier(self):
        work = load("Q100")
        work["claims"]["P31"][0]["mainsnak"]["datavalue"]["value"]["id"] = "Q999"
        with self.assertRaisesRegex(NormalizationError, r"Q100: unsupported or missing bibliographic type"):
            normalize_work("Q100", work, lookup())


if __name__ == "__main__":
    unittest.main()
