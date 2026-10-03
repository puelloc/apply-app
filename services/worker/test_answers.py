import unittest

from answers import answers, build_fill_summary, build_task


class TestAnswers(unittest.TestCase):
    def test_first_fill_canary(self):
        a = answers({"fill_summary": None, "answer_overrides": None})
        self.assertEqual(a["first_name"], "CANARY-First")

    def test_frozen_replayed(self):
        job = {"fill_summary": {"fields": [{"name": "first_name", "value": "Replay-First"}]}, "answer_overrides": None}
        self.assertEqual(answers(job)["first_name"], "Replay-First")

    def test_override_merged_over_frozen(self):
        job = {
            "fill_summary": {"fields": [{"name": "first_name", "value": "Replay-First"}, {"name": "email", "value": "a@x.com"}]},
            "answer_overrides": {"email": "new@x.com"},
        }
        a = answers(job)
        self.assertEqual(a["first_name"], "Replay-First")
        self.assertEqual(a["email"], "new@x.com")

    def test_fill_summary_sources(self):
        job = {"fill_summary": {"fields": [{"name": "first_name", "value": "Replay-First"}]}, "answer_overrides": {"email": "new@x.com"}}
        sources = {f["name"]: f["source"] for f in build_fill_summary(job)["fields"]}
        self.assertEqual(sources["first_name"], "frozen")
        self.assertEqual(sources["email"], "override")

    def test_build_task_uses_override(self):
        job = {"application_url": "http://x", "fill_summary": None, "answer_overrides": {"first_name": "Edited"}}
        self.assertIn("first name Edited", build_task(job))

    def test_profile_used_for_first_fill(self):
        job = {"fill_summary": None, "answer_overrides": None}
        profile = {"first_name": "Jane", "last_name": "Doe", "email": "jane@x.com", "phone": "555"}
        a = answers(job, profile)
        self.assertEqual(a["first_name"], "Jane")
        self.assertEqual(a["email"], "jane@x.com")

    def test_override_beats_profile(self):
        job = {"fill_summary": None, "answer_overrides": {"phone": "999"}}
        profile = {"first_name": "Jane", "last_name": "Doe", "email": "jane@x.com", "phone": "555"}
        a = answers(job, profile)
        self.assertEqual(a["phone"], "999")
        self.assertEqual(a["first_name"], "Jane")


if __name__ == "__main__":
    unittest.main(verbosity=2)
