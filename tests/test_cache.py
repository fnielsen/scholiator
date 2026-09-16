from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scholiator.cache import EntityCache


class CacheTests(unittest.TestCase):
    def test_entity_and_alias(self):
        with TemporaryDirectory() as tmp:
            cache = EntityCache(Path(tmp))
            cache.write_entity({"id": "Q2", "claims": {}, "labels": {}})
            cache.set_alias("Q1", "Q2")
            self.assertEqual(cache.get("Q1")["id"], "Q2")
            self.assertEqual(cache.resolve("Q1"), "Q2")

    def test_remove_canonical_removes_aliases(self):
        with TemporaryDirectory() as tmp:
            cache = EntityCache(Path(tmp))
            cache.write_entity({"id": "Q2"})
            cache.set_alias("Q1", "Q2")
            cache.remove("Q2")
            self.assertIsNone(cache.get("Q1"))


    def test_remove_alias_keeps_canonical_entity(self):
        with TemporaryDirectory() as tmp:
            cache = EntityCache(Path(tmp))
            cache.write_entity({"id": "Q2"})
            cache.set_alias("Q1", "Q2")
            cache.remove("Q1")
            self.assertIsNotNone(cache.get("Q2"))
            self.assertIsNone(cache.get("Q1"))

    def test_clear(self):
        with TemporaryDirectory() as tmp:
            cache = EntityCache(Path(tmp))
            cache.write_entity({"id": "Q2"})
            cache.clear()
            self.assertIsNone(cache.get("Q2"))


if __name__ == "__main__":
    unittest.main()
