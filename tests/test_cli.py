import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scholiator.cache import EntityCache
from scholiator.cli import main

FIXTURES = Path(__file__).parent / "fixtures" / "wikidata"


class CliTests(unittest.TestCase):
    def _populate_cache(self, cache_dir: Path):
        cache = EntityCache(cache_dir)
        for path in FIXTURES.glob("Q*.json"):
            cache.write_entity(json.loads(path.read_text(encoding="utf-8")))

    def test_offline_end_to_end(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_dir = root / "cache"
            self._populate_cache(cache_dir)
            config = root / "config.ini"
            config.write_text(
                f"[scholiator]\nformat = biblatex\ncache_dir = {cache_dir}\nlabel_languages = en,mul\ntitle_languages = en,mul\n",
                encoding="utf-8",
            )
            aux = root / "paper.aux"
            aux.write_text("\\citation{local,Q100}\n", encoding="utf-8")
            code = main(["--config", str(config), "--offline", str(root / "paper")])
            self.assertEqual(code, 0)
            output = (root / "paper.bib").read_text(encoding="utf-8")
            self.assertIn("@article{Q100,", output)
            self.assertIn("Exämple", output)

    def test_failure_does_not_replace_output(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_dir = root / "cache"
            config = root / "config.ini"
            config.write_text(f"[scholiator]\ncache_dir = {cache_dir}\n", encoding="utf-8")
            (root / "paper.aux").write_text("\\citation{Q999}\n", encoding="utf-8")
            output = root / "paper.bib"
            output.write_text("old bibliography\n", encoding="utf-8")
            code = main(["--config", str(config), "--offline", str(root / "paper")])
            self.assertEqual(code, 1)
            self.assertEqual(output.read_text(encoding="utf-8"), "old bibliography\n")


if __name__ == "__main__":
    unittest.main()
