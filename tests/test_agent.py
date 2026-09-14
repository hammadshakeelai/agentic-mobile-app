"""Offline tests for the agent loop: a scripted fake Gemini client and a fake phone.

Responses are built with the google-genai SDK's own Interaction models, and the
function results we send back are validated against the SDK's FunctionResultStep,
so a wire-format mistake fails here instead of against the live API.
"""

import unittest

from google.genai._gaos.resources.interactions import FunctionResultStep, Interaction
from google.genai._gaos.resources.interactions.tool import ComputerUse

from phone_agent.agent import PhoneAgent

PNG = b"\x89PNG fake"


class FakeBridge:
    def __init__(self):
        self.calls = []

    def screenshot(self):
        return PNG

    def __getattr__(self, name):
        def handler(**kwargs):
            if name == "click" and kwargs.get("x") == -1:
                raise RuntimeError("tap failed")
            self.calls.append((name, kwargs))
            return {"opened": kwargs["app_name"]} if name == "open_app" else None
        return handler


def call(call_id, name, **arguments):
    return {"type": "function_call", "id": call_id, "name": name, "arguments": arguments}


def reply(text):
    return {"type": "model_output", "content": [{"type": "text", "text": text}]}


def text_of(function_result):
    return next(c["text"] for c in function_result["result"] if c["type"] == "text")


class FakeClient:
    def __init__(self, *turns):
        self.turns = [Interaction.model_validate({"id": f"i{n}", "status": "completed", "steps": steps})
                      for n, steps in enumerate(turns)]
        self.requests = []
        self.interactions = self

    def create(self, **request):
        self.requests.append(request)
        return self.turns[len(self.requests) - 1]


def make_agent(client, bridge, **kw):
    return PhoneAgent(client, bridge, settle_seconds=0, log_dir=None, out=lambda *_: None, **kw)


class AgentLoopTest(unittest.TestCase):
    def test_executes_actions_and_returns_summary(self):
        client = FakeClient(
            [call("c1", "open_app", app_name="Settings", intent="open settings")],
            [call("c2", "click", x=500, y=120)],
            [reply("Airplane mode is on.")],
        )
        bridge = FakeBridge()
        summary = make_agent(client, bridge).run("Turn on airplane mode")

        self.assertEqual(summary, "Airplane mode is on.")
        self.assertEqual(bridge.calls, [("open_app", {"app_name": "Settings"}), ("click", {"x": 500, "y": 120})])
        first, second, third = client.requests
        self.assertIsNone(first["previous_interaction_id"])
        self.assertEqual(second["previous_interaction_id"], "i0")
        self.assertEqual(third["previous_interaction_id"], "i1")
        ComputerUse.model_validate(first["tools"][0])

        result = second["input"][0]
        FunctionResultStep.model_validate(result)  # raises if our payload doesn't match the SDK schema
        self.assertEqual(result["call_id"], "c1")
        self.assertFalse(result["is_error"])
        self.assertIn('"opened": "Settings"', text_of(result))

    def test_screenshot_is_first_in_function_result(self):
        # The live API returns 400 ("requires function response to contain an image") when the
        # text part comes first; the SDK schema accepts either order, so pin it here.
        client = FakeClient([call("c1", "go_back")], [reply("done")])
        make_agent(client, FakeBridge()).run("go back")
        parts = client.requests[1]["input"][0]["result"]
        self.assertEqual([p["type"] for p in parts], ["image", "text"])
        self.assertEqual(parts[0]["mime_type"], "image/png")

    def test_declined_safety_confirmation_stops_without_acting(self):
        risky = call("c1", "click", x=10, y=10,
                     safety_decision={"decision": "require_confirmation", "explanation": "Sends a payment"})
        bridge = FakeBridge()
        agent = make_agent(FakeClient([risky]), bridge, confirm=lambda _: False)
        self.assertIn("declined", agent.run("pay"))
        self.assertEqual(bridge.calls, [])

    def test_approved_safety_confirmation_is_acknowledged(self):
        risky = call("c1", "click", x=10, y=10,
                     safety_decision={"decision": "require_confirmation", "explanation": "Sends a message"})
        client = FakeClient([risky], [reply("Sent.")])
        bridge = FakeBridge()
        make_agent(client, bridge, confirm=lambda _: True).run("send hi")
        self.assertEqual(bridge.calls, [("click", {"x": 10, "y": 10})])
        self.assertIn('"safety_acknowledgement": true', text_of(client.requests[1]["input"][0]))

    def test_errors_are_reported_back_to_the_model(self):
        client = FakeClient([call("c1", "click", x=-1, y=0), call("c2", "format_phone")], [reply("gave up")])
        make_agent(client, FakeBridge()).run("x")
        failed_tap, unknown = client.requests[1]["input"]
        self.assertTrue(failed_tap["is_error"])
        self.assertIn("tap failed", text_of(failed_tap))
        self.assertTrue(unknown["is_error"])
        self.assertIn("Unknown action", text_of(unknown))

    def test_rate_limit_is_retried_after_suggested_delay(self):
        class RateLimited(Exception):
            status_code = 429

        client = FakeClient([reply("done")])
        real_create, attempts = client.create, []

        def flaky_create(**request):
            attempts.append(request)
            if len(attempts) == 1:
                raise RateLimited("Quota exceeded. Please retry in 2.5s.")
            return real_create(**request)

        client.create = flaky_create
        waits = []
        self.assertEqual(make_agent(client, FakeBridge(), sleep=waits.append).run("x"), "done")
        self.assertEqual(waits, [3.5])
        self.assertEqual(len(attempts), 2)

    def test_non_transient_api_errors_are_not_retried(self):
        class BadRequest(Exception):
            status_code = 400

        client = FakeClient()
        client.create = lambda **_: (_ for _ in ()).throw(BadRequest("invalid request"))
        waits = []
        with self.assertRaises(BadRequest):
            make_agent(client, FakeBridge(), sleep=waits.append).run("x")
        self.assertEqual(waits, [])

    def test_step_limit(self):
        client = FakeClient(*[[call(f"c{i}", "go_back")] for i in range(5)])
        agent = make_agent(client, FakeBridge(), max_steps=3)
        self.assertIn("3-step limit", agent.run("loop forever"))
        self.assertEqual(agent.actions_taken, 3)


if __name__ == "__main__":
    unittest.main()
