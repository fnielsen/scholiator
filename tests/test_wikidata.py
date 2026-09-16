from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scholiator.cache import EntityCache
from scholiator.wikidata import EntityRepository, FetchResult, WikidataError


class FakeClient:
    def __init__(self):
        self.calls = []

    def fetch(self, qids):
        self.calls.append(list(qids))
        if qids == ["Q1"]:
            return FetchResult(
                entities={"Q2": {"id": "Q2", "labels": {}, "claims": {}}},
                aliases={"Q1": "Q2"},
                missing=set(),
            )
        return FetchResult(
            entities={qid: {"id": qid, "labels": {}, "claims": {}} for qid in qids},
            aliases={},
            missing=set(),
        )


class RepositoryTests(unittest.TestCase):
    def test_redirect_persisted_for_offline(self):
        with TemporaryDirectory() as tmp:
            cache = EntityCache(Path(tmp))
            fake = FakeClient()
            repo = EntityRepository(cache, fake)
            self.assertEqual(repo.get_many(["Q1"])["Q1"]["id"], "Q2")
            self.assertEqual(fake.calls, [["Q1"]])
            offline_repo = EntityRepository(cache, FakeClient())
            self.assertEqual(offline_repo.get_many(["Q1"], offline=True)["Q1"]["id"], "Q2")

    def test_offline_miss_fails(self):
        with TemporaryDirectory() as tmp:
            repo = EntityRepository(EntityCache(Path(tmp)), FakeClient())
            with self.assertRaises(WikidataError):
                repo.get_many(["Q99"], offline=True)

    def test_refresh_bypasses_cache(self):
        with TemporaryDirectory() as tmp:
            cache = EntityCache(Path(tmp))
            cache.write_entity({"id": "Q3", "labels": {}, "claims": {}})
            fake = FakeClient()
            repo = EntityRepository(cache, fake)
            repo.get_many(["Q3"], refresh=True)
            self.assertEqual(fake.calls, [["Q3"]])


if __name__ == "__main__":
    unittest.main()
