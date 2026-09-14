# Agentic Mobile App

A small, deliberately simple MVP: **tell Gemini what you want done, and it operates an Android phone to do it.**

```
python -m phone_agent "Turn on airplane mode"
```

Is this a good idea, and how well does it work? Read **[RESEARCH.md](RESEARCH.md)** first. Short version: it's possible today on Android. It's reliable for short single-app tasks and weak on long multi-app ones. The hard problems are prompt injection and distribution, not raw capability.

## How it works

```
 ┌──────────── your computer ────────────┐        ┌──── phone / emulator ────┐
 │                                        │  adb   │                          │
 │  screenshot ──► Gemini (computer use,  │◄──────►│  screencap               │
 │                 environment="mobile")  │        │  input tap / text / swipe│
 │  action ◄────── click / type / open_app│        │  monkey (launch app)     │
 │     │                                  │        │                          │
 │     └── execute ──► new screenshot ──► repeat until Gemini says it's done  │
 └────────────────────────────────────────┘        └──────────────────────────┘
```

- **`phone_agent/adb.py`**: the bridge. It turns Gemini's actions (normalized 0–999 coordinates) into ADB commands and captures downscaled screenshots.
- **`phone_agent/agent.py`**: the loop. It calls the Gemini [Interactions API](https://ai.google.dev/gemini-api/docs/computer-use) with the `computer_use` tool, runs each action, and sends the result plus a fresh screenshot back.
- **`phone_agent/__main__.py`**: the CLI, `.env` loading, and `--dry-run`.

This follows the design of Google's [android computer-use quickstart](https://github.com/google-gemini/gemini-android-computer-use-quickstart), with safety and robustness added.

## Setup

**Needs:** Python 3.10+, [Android platform-tools](https://developer.android.com/tools/releases/platform-tools) (`adb`), and a Gemini API key from [AI Studio](https://aistudio.google.com/apikey).

1. **Get a device.** Start an Android emulator (Android Studio → Device Manager), or plug in a phone with **USB debugging** on. `adb devices` should list it.
2. **Install:**
   ```bash
   python -m venv .venv
   .venv/Scripts/activate        # macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Add your key.** Copy `.env.example` to `.env` and paste your key. `.env` is gitignored. Prefixed names copied from other projects, like `VITE_GEMINI_API_KEY`, also work.
4. **Check the phone connection (no API calls):**
   ```bash
   python -m phone_agent --dry-run
   ```
5. **Run a task:**
   ```bash
   python -m phone_agent "Turn on airplane mode"
   ```

| Flag | Default | Meaning |
|---|---|---|
| `-m, --model` | `gemini-3.8-flash` | Any Gemini model with computer use (e.g. `gemini-3.7-flash`) |
| `-t, --thinking-level` | `low` | `minimal` / `low` / `medium` / `high` |
| `-n, --max-steps` | `30` | Hard cap on actions |
| `-d, --device` | – | ADB serial when several devices are connected |
| `--dry-run` | – | Test the ADB bridge only |
| `--no-log` | – | Don't save screenshots and actions to `runs/` |

## Safety built in

- **Human confirmation.** If Gemini marks an action `require_confirmation` (payments, sending messages, and similar), the agent stops and asks you. It never auto-approves, and declining ends the run.
- **Prompt-injection defenses.** Gemini's `enable_prompt_injection_detection` is on, and the system prompt treats on-screen text as untrusted data.
- **Hard limits.** A step cap, Ctrl+C to stop at any time, and only whitelisted actions ever reach the device.
- **Audit trail.** Every run saves screenshots and a `log.jsonl` to `runs/<timestamp>/` (gitignored). Screenshots can contain personal data.
- **Privacy.** Screenshots are sent to Google's API. Don't point it at a phone with data you wouldn't share.

## Tests

Run from the repo root:

```bash
python -m unittest discover -s tests -v
```

The loop tests run offline against a scripted fake Gemini client. They build responses with the SDK's own models and validate the requests we send against the SDK's schema.

## Status

**Verified live** on an Android 16 emulator with `gemini-3.8-flash`. The task "Turn on airplane mode" took Gemini 3 actions (open Settings → Network & internet → toggle) in about 108 seconds, and `adb shell settings get global airplane_mode_on` went from `0` to `1`.

## Known limitations

- **Slow.** Each step is a round-trip to Gemini with a screenshot, typically about 30 seconds, so short tasks take a minute or two. Every request has a 120 second timeout.
- **Free-tier quota is small.** Every step is one API request, and a free key hit its limit (20 requests on `gemini-3.8-flash`) within a few test runs. Rate limits and server errors are retried up to 3 times using the wait time the API suggests. After that the run stops with a clear message. Enable billing for real use.
- Typing uses `adb shell input text`, which is **ASCII only**. Non-ASCII text is reported back to the model as an error.
- `open_app` matches common app names and package names. It can't read launcher labels for every app, so Gemini can call `list_apps` when a name doesn't match.
- It needs a computer and ADB, so it's a developer/QA tool, not yet a consumer app.

## Roadmap (after the MVP is solid)

1. Live-tested task suite with deterministic checks (e.g. airplane mode via `adb shell settings get global airplane_mode_on`).
2. On-device Android app using `AccessibilityService`, so no computer is needed.
3. Voice input and a persistent "stop" overlay.
