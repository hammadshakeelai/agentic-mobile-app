# Can an agentic AI run a phone?

Short research notes (September 2026) behind this repo's MVP.

## TL;DR

**Yes, it's possible today, on Android.** A model looks at the screen, picks an action (tap, type, swipe, open app), the action runs, and the loop repeats. Google now ships this as a "mobile" environment in the Gemini API's computer-use tool, and open-source frameworks (DroidRun/Mobilerun, Mobile-Use) do the same.

**How good?** It works well on short, well-defined tasks inside one app. It's still unreliable on long tasks that span several apps. The honest number is the newer MobileWorld benchmark, where the best agent completes **51.7%** of tasks. The older AndroidWorld benchmark reads over 90%, but it's saturated and those scores are mostly self-reported.

**The real blockers are security and distribution, not capability.** Text on screen can hijack the agent (prompt injection). Google Play is hostile to apps that use the Accessibility API for anything other than assistive technology. And iOS doesn't let third-party apps drive other apps at all.

---

## 1. Is it possible? Three ways to build it

| Approach | How it sees the phone | How it acts | Who uses it | Trade-off |
|---|---|---|---|---|
| **Screen agent over ADB** (this MVP) | Screenshots from `adb screencap` | `adb shell input tap/text/swipe` | Google's [Android computer-use quickstart](https://github.com/google-gemini/gemini-android-computer-use-quickstart) | Works with any app, no install needed. But it needs a computer or USB debugging, so it's a dev/QA tool, not a consumer product. |
| **On-device Accessibility agent** | The accessibility tree (UI as structured text), plus screenshots | `AccessibilityService` gestures and global actions | [DroidRun / Mobilerun](https://github.com/droidrun/mobilerun), Mobile-Use | Runs on the phone itself. But it's hard to get onto Play Store, and the tree is an injection surface. |
| **OS / app-intent integration** | App-declared actions instead of pixels | Structured intents (Apple App Intents, Android app functions) | Apple Intelligence Siri, Gemini on Android | The most reliable and safe option. But it only covers apps that opt in, and it's platform-owned, so third parties can't build a general agent this way on iOS. |

**Android is the open platform for this**: ADB and AccessibilityService expose everything. **iOS is closed**. Third parties can only work through App Intents, which Apple is making the sole way Siri acts inside apps ([ecorpit, iOS 27 App Intents](https://ecorpit.com/ios-27-app-store-ai-agents-app-intents-developer-strategy-2026/)).

### What the Gemini API gives you

- The **computer-use tool** accepts `environment: "mobile"`. The model receives a screenshot and returns actions such as `open_app`, `click`, `type`, `long_press`, `drag_and_drop`, `press_key`, `go_back`, `wait` and `list_apps`. Coordinates are on a normalized 0–999 grid, the same for Android and iOS ([Gemini API: Computer use](https://ai.google.dev/gemini-api/docs/computer-use), [Philipp Schmid's walkthrough](https://www.philschmid.de/gemini-android-use)).
- Sensitive actions can come back with a `safety_decision` of `require_confirmation`. The client is expected to ask a human before acknowledging it. The tool also has an `enable_prompt_injection_detection` flag.
- Model IDs move fast. Google's quickstart defaults to `gemini-3.7-flash`, and the models page lists `gemini-3.8-flash` as the newest Flash (GA 2026-09-02, per the [changelog](https://ai.google.dev/gemini-api/docs/changelog)). The MVP takes the model as a flag and defaults to `gemini-3.8-flash`, which passed its live test. One gotcha surfaced only against the live API: a function result must put the screenshot *before* any text part, or the request is rejected. The quickstart's order fails.

## 2. How good will it be?

| Benchmark | Best reported | Notes |
|---|---|---|
| AndroidWorld | >90% (e.g. DroidRun 91.4%, self-reported) | Saturated; human baseline ≈80% ([AndroidWorld overview](https://www.emergentmind.com/topics/androidworld)) |
| AndroidWorld (2025 academic SOTA) | 62.9% (MobileUse, Qwen2.5-VL-72B) | [MobileUse paper](https://arxiv.org/pdf/2507.16853) |
| **MobileWorld** (harder, agent-user interaction, MCP) | **51.7%** | [MobileWorld, ACL 2026](https://arxiv.org/html/2512.19432v1) |

**What to expect in practice:**

- **Good at:** single-app, clearly specified tasks. "Turn on airplane mode", "open YouTube and search for X", "set an alarm for 7am".
- **Mediocre at:** tasks that need scrolling to find things, pop-ups and permission dialogs, unusual custom UIs, and anything that needs remembering state across many steps.
- **Bad at:** long multi-app workflows ("find the cheapest flight, add it to my calendar, message my friend"). Errors compound, since each extra step is another chance to fail.
- **Speed:** every step is a network round-trip with an image, so a human is usually faster. It's a *delegation* tool ("do this while I'm busy"), not a speed tool.

## 3. Benefits

- **Works with every app, no integrations.** If a human can tap it, the agent can, including apps with no API.
- **Hands-free and accessibility wins.** Voice-first control for people who can't easily use a touchscreen.
- **Automating chores.** Repetitive multi-tap flows like form filling, settings changes, and cross-app copy/paste.
- **QA and testing.** Natural-language test scripts ("sign up with a new account and check the welcome screen") that survive UI changes better than coordinate-based scripts.
- **Cheap to prototype.** One general model plus a thin action layer. This repo's agent is about 350 lines of Python.

## 4. Cons and risks

- **Prompt injection is the #1 risk.** On-screen or accessibility text can instruct the agent. A 2026 study hit **82.2%** attack success against MobileRun and 15% against Mobile-Use. Agents "treat passive environmental text as trusted instructions" ([Not an A11y, arXiv 2608.08939](https://arxiv.org/abs/2608.08939); [Android guidance on prompt injection](https://developer.android.com/privacy-and-security/risks/ai-risks/prompt-injection)).
- **Irreversible actions.** Sending messages, paying, or deleting data. A wrong tap costs more than a wrong chat answer, so you need human confirmation gates.
- **Privacy.** Every screenshot (notifications, messages, banking screens) goes to a cloud model.
- **Distribution.** Play Store heavily restricts non-assistive Accessibility use. ADB-based agents need USB debugging, which most consumers won't enable.
- **Reliability and latency.** See §2. Long tasks fail often and every step is slow.
- **Cost.** Every step sends an image. Cheap per step on Flash models, but it adds up over retries.
- **Platform lock-in.** Only Android is open to this. On iOS, only Apple's Siri gets general control.

## 5. What this means for the MVP

Build the simplest thing that proves the loop and is honest about the risks:

1. **Host-side ADB agent** (Python + `google-genai`), mirroring Google's reference design. It runs against an emulator or a USB-connected phone. It supports two providers: Gemini's built-in computer-use tool, and an OpenAI-compatible vision model with tool calling (Agnes AI), where the agent declares the phone actions itself. In live tests both turned airplane mode on. Agnes took about 5 s per step versus about 35 s for Gemini, but it made more malformed calls and has no server-side safety checks.
2. **Human-in-the-loop safety.** Actions flagged `require_confirmation` pause and ask you. They are never auto-acknowledged.
3. **Hard limits.** A max step count, Ctrl+C to stop, and a `--dry-run` that tests the phone bridge without calling the model.
4. **Keep a record.** Each run saves its screenshots and actions to `runs/` so you can see what the agent did.

The natural next step is an on-device `AccessibilityService` app, so no computer is needed. That brings the Play Store and injection problems above along with it.

## Sources

- [Gemini API: Computer use](https://ai.google.dev/gemini-api/docs/computer-use)
- [Gemini API: Models](https://ai.google.dev/gemini-api/docs/models) and [Changelog](https://ai.google.dev/gemini-api/docs/changelog)
- [google-gemini/gemini-android-computer-use-quickstart](https://github.com/google-gemini/gemini-android-computer-use-quickstart)
- [Philipp Schmid: Control an Android phone with Gemini computer use](https://www.philschmid.de/gemini-android-use)
- [9to5Google: Gemini control of Android](https://9to5google.com/2025/12/29/gemini-android-control/)
- [MobileWorld benchmark (arXiv 2512.19432)](https://arxiv.org/html/2512.19432v1)
- [AndroidWorld overview](https://www.emergentmind.com/topics/androidworld)
- [MobileUse (arXiv 2507.16853)](https://arxiv.org/pdf/2507.16853)
- [DroidRun / Mobilerun](https://github.com/droidrun/mobilerun)
- [Not an A11y: Android Accessibility and indirect prompt injection (arXiv 2608.08939)](https://arxiv.org/abs/2608.08939)
- [Android Developers: Mitigate prompt injection attacks](https://developer.android.com/privacy-and-security/risks/ai-risks/prompt-injection)
- [iOS 27 App Intents and AI agents](https://ecorpit.com/ios-27-app-store-ai-agents-app-intents-developer-strategy-2026/)
