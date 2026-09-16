from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scholiator.config import load_config


class ConfigTests(unittest.TestCase):
    def test_ini(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.ini"
            path.write_text("[scholiator]\nformat=biblatex\nlabel_languages=da,en,mul\n", encoding="utf-8")
            config = load_config(path)
            self.assertEqual(config.format, "biblatex")
            self.assertEqual(config.label_languages, ("da", "en", "mul"))


if __name__ == "__main__":
    unittest.main()
