import unittest

from allowlist import apex, build_allowlist


class TestAllowlist(unittest.TestCase):
    def test_apex(self):
        self.assertEqual(apex("boards.greenhouse.io"), "greenhouse.io")
        self.assertEqual(apex("acme.wd5.myworkdayjobs.com"), "myworkdayjobs.com")
        self.assertEqual(apex("localhost"), "localhost")

    def test_build_includes_host_apex_and_common(self):
        al = build_allowlist("https://boards.greenhouse.io/acme/jobs/123")
        self.assertIn("boards.greenhouse.io", al)
        self.assertIn("greenhouse.io", al)
        self.assertIn("gstatic.com", al)

    def test_dedupe_and_extra_normalized(self):
        al = build_allowlist("https://jobs.lever.co/acme/x", extra=["lever.co", "ACME.example"])
        self.assertEqual(len(al), len(set(al)))
        self.assertIn("acme.example", al)

    def test_bad_url_still_gets_common(self):
        al = build_allowlist("not a url")
        self.assertIn("gstatic.com", al)


if __name__ == "__main__":
    unittest.main(verbosity=2)
