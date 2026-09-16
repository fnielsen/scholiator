from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scholiator.citation import CitationError, extract_aux, extract_bcf, resolve_input

FIXTURES = Path(__file__).parent / "fixtures"


class CitationTests(unittest.TestCase):
    def test_aux_mixed_duplicates_and_recursive_input(self):
        self.assertEqual(
            extract_aux(FIXTURES / "aux" / "main.aux"),
            ["Q100", "Q101", "Q102"],
        )

    def test_bcf(self):
        self.assertEqual(extract_bcf(FIXTURES / "bcf" / "main.bcf"), ["Q100", "Q101"])

    def test_aux_path_traversal_refused(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root.parent / "outside-scholiator-test.aux"
            outside.write_text("\\citation{Q999}\n", encoding="utf-8")
            try:
                (root / "main.aux").write_text(
                    f"\\@input{{../{outside.name}}}\n", encoding="utf-8"
                )
                with self.assertRaises(CitationError):
                    extract_aux(root / "main.aux")
            finally:
                outside.unlink(missing_ok=True)

    def test_aux_cycle_is_safe(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.aux").write_text("\\citation{Q1}\n\\@input{b.aux}\n", encoding="utf-8")
            (root / "b.aux").write_text("\\citation{Q2}\n\\@input{a.aux}\n", encoding="utf-8")
            self.assertEqual(extract_aux(root / "a.aux"), ["Q1", "Q2"])

    def test_basename_prefers_bcf(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp) / "paper"
            Path(f"{base}.aux").write_text("", encoding="utf-8")
            Path(f"{base}.bcf").write_text("<x/>", encoding="utf-8")
            source, output = resolve_input(base)
            self.assertEqual(source.suffix, ".bcf")
            self.assertEqual(output, Path(f"{base}.bib"))


if __name__ == "__main__":
    unittest.main()
