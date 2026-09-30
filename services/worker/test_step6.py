import unittest

from adapters import fields, selector
from reasoning import agent_step_to_payload, from_browser_use


class TestAdapters(unittest.TestCase):
    def test_greenhouse_selector(self):
        self.assertEqual(selector("greenhouse", "email"), "input[name=email]")
        self.assertEqual(selector("greenhouse", "work_auth"), "select[name=work_auth]")

    def test_unknown_ats_and_field(self):
        self.assertIsNone(selector("workday", "email"))
        self.assertIsNone(selector("greenhouse", "nope"))

    def test_fields(self):
        self.assertIn("first_name", fields("greenhouse"))
        self.assertIn("why", fields("lever"))


class TestReasoning(unittest.TestCase):
    def test_payload_shape(self):
        step = {
            "step": 3, "action": "input_text", "eval": "done", "memory": "...",
            "next_goal": "fill email", "url": "http://x", "error": None,
        }
        payload = agent_step_to_payload("greenhouse", "run-1", step)
        self.assertEqual(payload["step"], "agent-3")
        self.assertEqual(payload["action"], "input_text")
        self.assertEqual(payload["postcondition"], "pass")
        self.assertEqual(payload["model_meta"]["next_goal"], "fill email")

    def test_error_sets_fail_and_error_code(self):
        payload = agent_step_to_payload("greenhouse", "r", {"step": 1, "action": "click", "error": "x", "error_code": "selector_missing"})
        self.assertEqual(payload["postcondition"], "fail")
        self.assertEqual(payload["error_code"], "selector_missing")


class _FakeModelOutput:
    def __init__(self):
        self.evaluation_previous_goal = "eval"
        self.memory = "mem"
        self.next_goal = "next"
        self.action = [_FakeAction()]


class _FakeAction:
    name = "input_text"


class _FakeStep:
    step_number = 2
    model_output = _FakeModelOutput()
    state = None


class TestFromBrowserUse(unittest.TestCase):
    def test_normalize(self):
        step = from_browser_use(_FakeStep())
        self.assertEqual(step["step"], 2)
        self.assertEqual(step["action"], "input_text")
        self.assertEqual(step["eval"], "eval")
        self.assertEqual(step["url"], None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
