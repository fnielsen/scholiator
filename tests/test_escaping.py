import unittest

from scholiator.escaping import EscapingError, escape_text


class EscapingTests(unittest.TestCase):
    def test_tex_specials_and_double_caret(self):
        value = r"\\{}%#$&_^~^^"
        escaped = escape_text(value, ascii_only=True)
        self.assertNotIn("^^", escaped)
        self.assertIn(r"\textbackslash{}", escaped)
        self.assertIn(r"\%", escaped)

    def test_latin_unicode_to_ascii_tex(self):
        escaped = escape_text("Exämple Øresund", ascii_only=True)
        escaped.encode("ascii")
        self.assertIn(r'\"{a}', escaped)
        self.assertIn(r"\O", escaped)

    def test_utf8_mode_preserves_unicode(self):
        self.assertIn("漢字", escape_text("漢字", ascii_only=False))

    def test_unsupported_unicode_ascii_mode(self):
        with self.assertRaises(EscapingError):
            escape_text("漢字", ascii_only=True)

    def test_control_character_rejected(self):
        with self.assertRaises(EscapingError):
            escape_text("hello\x00world", ascii_only=False)
        with self.assertRaises(EscapingError):
            escape_text("hello\nworld", ascii_only=False)
        with self.assertRaises(EscapingError):
            escape_text("hello\u2028world", ascii_only=False)
        with self.assertRaises(EscapingError):
            escape_text("hello\u202eworld", ascii_only=False)


if __name__ == "__main__":
    unittest.main()
