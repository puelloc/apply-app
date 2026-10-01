import email
import unittest
from email.message import EmailMessage

from aliases import alias_for, token_for
from imap import extract_verification_url_from_message
from verification import find_verification_url


class TestAliases(unittest.TestCase):
    def test_alias_for(self):
        self.assertEqual(alias_for("jobs@x.com", "job3"), "jobs+job3@x.com")

    def test_alias_bad_email(self):
        with self.assertRaises(ValueError):
            alias_for("not-an-email", "x")

    def test_token_for(self):
        self.assertEqual(token_for(7), "job7")


class TestVerification(unittest.TestCase):
    def test_finds_url(self):
        body = "Please verify: https://acme.com/verify?token=abc123 thanks"
        self.assertEqual(find_verification_url(body), "https://acme.com/verify?token=abc123")

    def test_strips_trailing_punctuation(self):
        self.assertEqual(find_verification_url("click https://x.com/v)."), "https://x.com/v")

    def test_no_url(self):
        self.assertIsNone(find_verification_url("no link here"))


class TestImapParse(unittest.TestCase):
    def test_extract_from_message(self):
        msg = EmailMessage()
        msg["To"] = "jobs+job3@x.com"
        msg.set_content("Verify at https://acme.com/verify?t=1")
        self.assertEqual(extract_verification_url_from_message(msg, "jobs+job3@x.com"), "https://acme.com/verify?t=1")

    def test_wrong_alias(self):
        msg = EmailMessage()
        msg["To"] = "other@x.com"
        msg.set_content("Verify at https://acme.com/verify")
        self.assertIsNone(extract_verification_url_from_message(msg, "jobs+job3@x.com"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
