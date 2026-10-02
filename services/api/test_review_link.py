import time
import unittest

import app.review_link as rl


class TestReviewLink(unittest.TestCase):
    def test_roundtrip(self):
        token, expiry = rl.generate_token(7, ttl_s=3600)
        self.assertGreater(expiry, time.time())
        self.assertEqual(rl.verify_token(token), 7)

    def test_tampered_token_rejected(self):
        token, _ = rl.generate_token(7)
        bad = ("A" if token[0] != "A" else "B") + token[1:]  # change a data char (before padding)
        self.assertIsNone(rl.verify_token(bad))

    def test_expired_token_rejected(self):
        token, _ = rl.generate_token(7, ttl_s=-10)  # already expired
        self.assertIsNone(rl.verify_token(token))


if __name__ == "__main__":
    unittest.main(verbosity=2)
