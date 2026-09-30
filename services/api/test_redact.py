import unittest

from app.redact import redact


class TestRedact(unittest.TestCase):
    def test_email(self):
        self.assertNotIn("jane@example.com", redact("contact jane@example.com now"))

    def test_password_key_value(self):
        self.assertNotIn("hunter2", redact("password=hunter2"))

    def test_token_header(self):
        self.assertNotIn("abc123", redact("Authorization: Bearer abc123"))

    def test_plain_text_untouched(self):
        self.assertEqual(redact("no secrets here"), "no secrets here")


if __name__ == "__main__":
    unittest.main(verbosity=2)
