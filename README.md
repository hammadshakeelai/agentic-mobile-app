# Agentic Mobile App

A small, deliberately simple MVP: **tell an AI model what you want done, and it operates an Android phone to do it.**

```
python -m phone_agent "Turn on airplane mode"
```

Where this is heading, a simple all-in-one AI app for documents and phone tasks: see **[RESEARCH-NEXTGEN.md](RESEARCH-NEXTGEN.md)**.

Is this a good idea, and how well does it work? Read **[RESEARCH.md](RESEARCH.md)** first. Short version: it's possible today on Android. It's reliable for short single-app tasks and weak on long multi-app ones. The hard problems are prompt injection and distribution, not raw capability.

## How it works

```
 ┌──────────── your computer ────────────┐        ┌──── phone / emulator ────┐
 │                                        │  adb   │                          │
 │  screenshot ──► model (Gemini / Agnes) │◄──────►│  screencap               │
 │                                        │        │  input tap / text / swipe│
 │  action ◄────── click / type / open_app│        │  monkey (launch app)     │
 │     │                                  │        │                          │
 │     └── execute ──► new screenshot ──► repeat until the model is done      │
 └────────────────────────────────────────┘        └──────────────────────────┘
```

- **`phone_agent/adb.py`**: the bridge. It turns the model's actions (normalized 0–999 coordinates) into ADB commands and captures downscaled screenshots.
- **`phone_agent/agent.py`**: the loop. It runs each action the model asks for, with safety confirmation, a step cap, retries and a run log.
- **`phone_agent/providers.py`**: the two model backends, described below.
- **`phone_agent/__main__.py`**: the CLI, `.env` loading, and `--dry-run`.

### Two model providers

| | `--provider gemini` (default) | `--provider agnes` |
|---|---|---|
| API | Gemini [Interactions API](https://ai.google.dev/gemini-api/docs/computer-use) with its built-in `computer_use` tool | [Agnes AI](https://github.com/AgnesAI-Labs/AgnesAI-Models), an OpenAI-compatible chat API; the agent declares the phone tools itself |
| Default model | `gemini-3.8-flash` | `agnes-3.0-flash` |
| Key | `GEMINI_API_KEY` | `AGNES_API_KEY` |
| Speed in our tests | about 35 s per step | about 5 s per step |
| Free tier | tiny (20 requests on `gemini-3.8-flash` ran out within a few runs) | 20 requests per minute |
| Server-side safety | Flags risky actions and detects prompt injection | **None.** Relies on the model marking actions `sensitive` and on the system prompt |

The Gemini path follows the design of Google's [android computer-use quickstart](https://github.com/google-gemini/gemini-android-computer-use-quickstart), with safety and robustness added. The Agnes path should work with any OpenAI-compatible model that accepts images and supports tool calling, but only Agnes has been tested.

## Setup

**Needs:** Python 3.10+, [Android platform-tools](https://developer.android.com/tools/releases/platform-tools) (`adb`), and a Gemini key from [AI Studio](https://aistudio.google.com/apikey) and/or an Agnes AI key.

1. **Get a device.** Start an Android emulator (Android Studio → Device Manager), or plug in a phone with **USB debugging** on. `adb devices` should list it.
2. **Install:**
   ```bash
   python -m venv .venv
   .venv/Scripts/activate        # macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Add your keys.** Copy `.env.example` to `.env` and fill in `GEMINI_API_KEY`, `AGNES_API_KEY`, or both. `.env` is gitignored. For Gemini, prefixed names copied from other projects, like `VITE_GEMINI_API_KEY`, also work.
4. **Check the phone connection (no API calls):**
   ```bash
   python -m phone_agent --dry-run
   ```
5. **Run a task:**
   ```bash
   python -m phone_agent "Turn on airplane mode"                    # Gemini
   python -m phone_agent --provider agnes "Turn on airplane mode"   # Agnes AI
   ```

| Flag | Default | Meaning |
|---|---|---|
| `-p, --provider` | `gemini` | `gemini` or `agnes` |
| `-m, --model` | `gemini-3.8-flash` / `agnes-3.0-flash` | Any model the provider offers (e.g. `gemini-3.7-flash`, `agnes-2.5-flash`) |
| `-t, --thinking-level` | `low` | Gemini only: `minimal` / `low` / `medium` / `high` |
| `-n, --max-steps` | `30` | Hard cap on actions |
| `-d, --device` | – | ADB serial when several devices are connected |
| `--dry-run` | – | Test the ADB bridge only |
| `--no-log` | – | Don't save screenshots and actions to `runs/` |

## Safety built in

- **Human confirmation.** If an action is flagged as sensitive (sending messages, paying, deleting data, changing accounts), the agent stops and asks you. It never auto-approves, and declining ends the run. Gemini flags actions with a server-side check. With Agnes, the flag comes only from the model itself, so it can be missed.
- **Prompt-injection defenses.** With Gemini, `enable_prompt_injection_detection` is on. With both providers, the system prompt treats on-screen text as untrusted data. Agnes has no injection detection.
- **Hard limits.** A step cap, Ctrl+C to stop at any time, and only whitelisted actions ever reach the device. Numeric arguments from the model are validated first.
- **Audit trail.** Every run saves screenshots and a `log.jsonl` to `runs/<timestamp>/` (gitignored). Screenshots can contain personal data.
- **Privacy.** Screenshots are sent to Google or Agnes AI. Don't point it at a phone with data you wouldn't share.

## Tests

Run from the repo root:

```bash
python -m unittest discover -s tests -v
```

The loop tests run offline against scripted fake APIs for both providers. Gemini responses are built with the SDK's own models, and our requests are validated against the SDK's schema. The Agnes tests use the chat request and response shapes confirmed against the live API.

## Status

**Verified live** on an Android 16 emulator with both providers. The task was "Turn on airplane mode", checked with `adb shell settings get global airplane_mode_on` before and after:

- **Gemini** (`gemini-3.8-flash`, thinking `low`): 3 actions (open Settings → Network & internet → toggle) in about 108 seconds; `0` → `1`. The key was passed through the environment for that run. Later runs of the plain README command, reading the key from `.env`, drove the phone but ran out of free-tier quota before finishing.
- **Agnes** (`agnes-3.0-flash`): 6 actions in about 33 seconds; `0` → `1`. The key was passed through the environment. Two actions had malformed arguments; they were reported back as errors and the model corrected itself. Its final summary wrongly said airplane mode was "already" on.

## Known limitations

- **Gemini is slow and its free quota is small.** Each step is a round-trip with a screenshot, about 35 seconds on Gemini, and a free key ran out within a few test runs. Rate limits, server errors and timeouts (120 s per request) are retried up to 3 times, using the wait time the API suggests.
- **Models make mistakes.** `agnes-3.0-flash` sometimes sends malformed arguments (e.g. `x='[500, 266]'`) or misreports what it did. Errors go back to the model, which usually retries correctly at the cost of a step. Check important results yourself.
- Typing uses `adb shell input text`, which is **ASCII only**. Non-ASCII text is reported back to the model as an error.
- `open_app` matches common app names and package names. It can't read launcher labels for every app, so the model can call `list_apps` when a name doesn't match.
- It needs a computer and ADB, so it's a developer/QA tool, not yet a consumer app.

## Roadmap (after the MVP is solid)

1. Live-tested task suite with deterministic checks (like the airplane-mode check above).
2. On-device Android app using `AccessibilityService`, so no computer is needed.
3. Voice input and a persistent "stop" overlay.
