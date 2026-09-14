"""Offline tests for the agent loop with scripted fake model APIs and a fake phone.

Gemini responses are built with the google-genai SDK's own Interaction models, and the function
results we send back are validated against the SDK's FunctionResultStep, so a wire-format mistake
fails here instead of against the live API. The Agnes (chat-completions) provider runs against a
fake HTTP client using the request/response shapes confirmed against the live Agnes API.
"""

import copy
import json
import unittest

from google.genai._gaos.resources.interactions import FunctionResultStep, Interaction
from google.genai._gaos.resources.interactions.tool import ComputerUse

from phone_agent.agent import ACTIONS, PhoneAgent
from phone_agent.providers import ChatCompletionsProvider, GeminiProvider

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
    return PhoneAgent(GeminiProvider(client), bridge, settle_seconds=0, log_dir=None, out=lambda *_: None, **kw)


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

    def test_numbers_sent_as_strings_are_parsed(self):
        # Seen live: agnes-3.0-flash sent drag_and_drop(start_x='[499]', ...) as strings.
        client = FakeClient([call("c1", "click", x="[500]", y="120"), call("c2", "click", x="left", y=1)],
                            [reply("done")])
        bridge = FakeBridge()
        make_agent(client, bridge).run("tap")
        self.assertEqual(bridge.calls, [("click", {"x": 500.0, "y": 120.0})])
        self.assertTrue(client.requests[1]["input"][1]["is_error"])
        self.assertIn("expected a number", text_of(client.requests[1]["input"][1]))

    def test_step_limit(self):
        client = FakeClient(*[[call(f"c{i}", "go_back")] for i in range(5)])
        agent = make_agent(client, FakeBridge(), max_steps=3)
        self.assertIn("3-step limit", agent.run("loop forever"))
        self.assertEqual(agent.actions_taken, 3)


class FakeResponse:
    def __init__(self, status_code=200, body=None, headers=None):
        self.status_code, self._body, self.headers = status_code, body or {}, headers or {}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


def chat_reply(content="", tool_calls=()):
    calls = [{"id": f"call_{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
             for i, (name, args) in enumerate(tool_calls)]
    return FakeResponse(body={"choices": [{"message": {"role": "assistant", "content": content,
                                                       "tool_calls": calls or None}}]})


class FakeHTTP:
    def __init__(self, *responses):
        self.responses, self.requests = list(responses), []

    def post(self, url, headers=None, json=None, timeout=None):
        self.requests.append({"url": url, "headers": headers, "body": copy.deepcopy(json)})
        return self.responses.pop(0)


def make_chat_agent(http, bridge, **kw):
    provider = ChatCompletionsProvider("test-key", http=http)
    return PhoneAgent(provider, bridge, settle_seconds=0, log_dir=None, out=lambda *_: None, **kw)


class ChatProviderTest(unittest.TestCase):
    def test_runs_actions_and_sends_results_in_chat_format(self):
        http = FakeHTTP(chat_reply(tool_calls=[("open_app", {"app_name": "Settings", "intent": "open it"})]),
                        chat_reply(content="Airplane mode is on."))
        bridge = FakeBridge()
        self.assertEqual(make_chat_agent(http, bridge).run("Turn on airplane mode"), "Airplane mode is on.")
        self.assertEqual(bridge.calls, [("open_app", {"app_name": "Settings"})])

        first, second = http.requests
        self.assertTrue(first["url"].endswith("/chat/completions"))
        self.assertEqual(first["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(first["body"]["model"], "agnes-3.0-flash")
        self.assertEqual({t["function"]["name"] for t in first["body"]["tools"]}, ACTIONS - {"take_screenshot"})

        messages = second["body"]["messages"]
        self.assertEqual([m["role"] for m in messages], ["system", "user", "assistant", "tool", "user"])
        self.assertEqual(messages[2]["tool_calls"][0]["id"], "call_0")
        self.assertEqual(messages[3]["tool_call_id"], "call_0")
        self.assertIn('"opened": "Settings"', messages[3]["content"])
        images = [p for m in messages if isinstance(m["content"], list) for p in m["content"] if p["type"] == "image_url"]
        self.assertEqual(len(images), 1)  # older screenshots are dropped; only the newest is sent
        self.assertEqual(messages[-1]["content"][1]["type"], "image_url")

    def test_sensitive_action_needs_confirmation(self):
        risky = ("click", {"x": 1, "y": 2, "sensitive": True, "intent": "Send the message"})
        bridge = FakeBridge()
        agent = make_chat_agent(FakeHTTP(chat_reply(tool_calls=[risky])), bridge, confirm=lambda _: False)
        self.assertIn("declined", agent.run("send it"))
        self.assertEqual(bridge.calls, [])

    def test_rate_limit_uses_retry_after_header(self):
        http = FakeHTTP(FakeResponse(429, {"error": "slow down"}, {"retry-after": "2"}), chat_reply(content="done"))
        waits = []
        self.assertEqual(make_chat_agent(http, FakeBridge(), sleep=waits.append).run("x"), "done")
        self.assertEqual(waits, [3.0])
        self.assertEqual(len(http.requests), 2)


if __name__ == "__main__":
    unittest.main()
