import json
import logging
import unittest

from app.redact import JsonFormatter, redact


class TestRedact(unittest.TestCase):
    def test_email(self):
        self.assertNotIn("jane@example.com", redact("contact jane@example.com now"))

    def test_password_key_value(self):
        self.assertNotIn("hunter2", redact("password=hunter2"))

    def test_token_header(self):
        self.assertNotIn("abc123", redact("Authorization: Bearer abc123"))

    def test_plain_text_untouched(self):
        self.assertEqual(redact("no secrets here"), "no secrets here")


class TestJsonFormatter(unittest.TestCase):
    def _format(self, **extra):
        record = logging.LogRecord("x", logging.INFO, "", 0, "msg token=abc123", (), None)
        for k, v in extra.items():
            setattr(record, k, v)
        return json.loads(JsonFormatter().format(record))

    def test_redacts_and_is_json(self):
        payload = self._format(job_id=1, step="fill")
        self.assertEqual(payload["job_id"], 1)
        self.assertEqual(payload["step"], "fill")
        self.assertNotIn("abc123", payload["message"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
