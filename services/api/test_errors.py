import unittest

from app.errors import get


class TestErrors(unittest.TestCase):
    def test_known_code(self):
        spec = get("ollama_unreachable")
        self.assertEqual(spec.code, "ollama_unreachable")
        self.assertTrue(spec.cause)
        self.assertTrue(spec.fix)

    def test_every_code_has_cause_and_fix(self):
        from app.errors import ERRORS

        for spec in ERRORS.values():
            self.assertTrue(spec.cause, spec.code)
            self.assertTrue(spec.fix, spec.code)

    def test_unknown_falls_back_to_internal(self):
        self.assertEqual(get("no_such_code").code, "internal")


if __name__ == "__main__":
    unittest.main(verbosity=2)
