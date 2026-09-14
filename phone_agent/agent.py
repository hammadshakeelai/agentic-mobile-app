"""The agent loop: screenshot -> model -> actions -> new screenshot -> ... until the model says it's done."""

import json
import re
import time
from datetime import datetime
from pathlib import Path

# Whitelist of handlers the model may call on the bridge.
ACTIONS = {"click", "long_press", "drag_and_drop", "type", "press_key", "go_back",
           "open_app", "list_apps", "wait", "take_screenshot"}

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
NUMERIC_ARGS = {"x", "y", "start_x", "start_y", "end_x", "end_y", "seconds"}


def _number(value) -> float:
    """Models sometimes send numbers as strings such as "500" or "[500]"."""
    if isinstance(value, (int, float)):
        return value
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    if not match:
        raise ValueError(f"expected a number, got {value!r}")
    return float(match.group())


def _retry_delay(error: Exception, attempt: int) -> float | None:
    """Seconds to wait before retrying a transient API error (rate limit, overload, timeout), else None."""
    text = str(error)
    status = getattr(error, "status_code", None)
    if not isinstance(status, int):
        match = re.search(r"Error code: (\d{3})", text)
        status = int(match.group(1)) if match else None
    if status not in RETRYABLE_STATUS and "timeout" not in type(error).__name__.lower():
        return None
    hint = re.search(r"retry in ([\d.]+)s", text)  # the API says how long a rate limit lasts
    return min(float(hint.group(1)) + 1, 90) if hint else 10 * 2 ** attempt


def _ask(question: str) -> bool:
    try:
        return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


class PhoneAgent:
    def __init__(self, provider, bridge, max_steps=30, settle_seconds=1.0, log_dir="runs", confirm=_ask,
                 out=print, request_timeout=120, max_retries=3, sleep=time.sleep):
        self.provider, self.bridge = provider, bridge
        self.request_timeout, self.max_retries, self.sleep = request_timeout, max_retries, sleep
        self.max_steps, self.settle_seconds = max_steps, settle_seconds
        self.confirm, self.out = confirm, out
        self.run_dir = Path(log_dir) / datetime.now().strftime("%Y%m%d-%H%M%S") if log_dir else None
        self.actions_taken = 0

    def _log(self, record: dict, png: bytes | None = None):
        if not self.run_dir:
            return
        self.run_dir.mkdir(parents=True, exist_ok=True)
        if png:
            record["screenshot"] = f"step_{self.actions_taken:03d}.png"
            (self.run_dir / record["screenshot"]).write_bytes(png)
        with open(self.run_dir / "log.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _with_retries(self, send):
        for attempt in range(self.max_retries + 1):
            try:
                return send()
            except Exception as e:
                delay = _retry_delay(e, attempt)
                if delay is None or attempt == self.max_retries:
                    raise
                self.out(f"  .. API rate-limited or busy; retrying in {delay:.0f}s "
                         f"({attempt + 1}/{self.max_retries})")
                self.sleep(delay)

    def _execute(self, call) -> tuple[dict, bool]:
        """Run one action. Returns (result payload, keep_going)."""
        args = dict(call.arguments or {})
        safety = args.pop("safety_decision", None)  # Gemini flags risky actions server-side
        intent = args.pop("intent", None)
        if args.pop("sensitive", False) in (True, "true", "True"):  # chat providers flag them via the tool schema
            safety = {"decision": "require_confirmation", "explanation": intent or "The model marked this action sensitive"}
        shown = ", ".join(f"{k}={v!r}" for k, v in args.items())
        self.out(f"  -> {call.name}({shown})" + (f"  # {intent}" if intent else ""))

        result = {"status": "ok"}
        if safety and safety.get("decision") == "require_confirmation":
            self.out(f"  !! Flagged as sensitive: {safety.get('explanation', 'needs confirmation')}")
            if not self.confirm("  Allow this action?"):
                return {"status": "error", "error": "The user declined this action."}, False
            result["safety_acknowledgement"] = True

        if call.name not in ACTIONS:
            return {"status": "error", "error": f"Unknown action: {call.name}"}, True
        try:
            args = {k: _number(v) if k in NUMERIC_ARGS else v for k, v in args.items()}
            extra = getattr(self.bridge, call.name)(**args)
            if isinstance(extra, dict):
                result.update(extra)
        except Exception as e:  # report failures back to the model so it can recover
            result = {"status": "error", "error": str(e)}
            self.out(f"     error: {e}")
        return result, True

    def run(self, task: str) -> str:
        self.out(f"Task: {task}\nModel: {self.provider.model} | max steps: {self.max_steps}")
        png = self.bridge.screenshot()
        self._log({"task": task, "model": self.provider.model}, png)
        calls, text = self._with_retries(lambda: self.provider.start(task, png, self.request_timeout))

        while calls:
            results = []
            for call in calls:
                if self.actions_taken >= self.max_steps:
                    return f"Stopped: reached the {self.max_steps}-step limit."
                self.actions_taken += 1
                payload, keep_going = self._execute(call)
                if not keep_going:
                    self._log({"action": call.name, "args": call.arguments, "result": payload})
                    return "Stopped: you declined a sensitive action."
                time.sleep(self.settle_seconds)
                png = self.bridge.screenshot()
                self._log({"action": call.name, "args": call.arguments, "result": payload}, png)
                results.append((call, payload, png))
            calls, text = self._with_retries(lambda: self.provider.step(results, self.request_timeout))

        summary = text or "(no summary)"
        self._log({"done": summary})
        return summary
