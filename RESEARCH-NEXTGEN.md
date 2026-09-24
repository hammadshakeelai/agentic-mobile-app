# A "laptop in your pocket" AI app: what exists, what's missing, what to build

Research notes, September 2026. Follows [RESEARCH.md](RESEARCH.md), which asked whether an AI can operate a phone at all.

## The idea

One app that looks as simple as a chat box but can actually do the work people need a laptop for: read and write PDFs, Word files and spreadsheets, research, write, and act on the phone. It works with **any model**, whether on-device, on your own PC, or a cloud key you bring, and has as few limits as possible.

## TL;DR

- **Buildable today, and nobody ships the whole combination.** Big-tech assistants are polished but locked to one vendor's model, paywalled, and weak at making real files. Open-source agents are powerful but built for power users (terminals, workflow editors) and are sideload-only. Document apps are single-purpose "chat with your PDF" tools.
- **The gap:** *simple UI + any model (local or cloud) + real document creation + agent tools, in one app.*
- **Be realistic about the models.** On-device models are good for summarizing and rewriting, but too small for long multi-step work. Phone control succeeds on under half of real tasks. So: documents first, cloud or PC models for heavy lifting, phone control as a bonus.

## 1. What already exists

| Product | What it does | Models | Where the work runs | Why it doesn't cover this idea |
|---|---|---|---|---|
| **Gemini Intelligence** (Google) | Computer-use agent inside phone apps, e.g. shops a syllabus's book list | Gemini only | Phone + Google cloud | Pixel 10 / Galaxy S26 first (rolling out from summer 2026); one vendor; confirms purchases; not a document workspace |
| **Siri + App Intents** (Apple, iOS 27) | Multi-step actions in apps that implement App Intents | Apple's | iPhone | Only apps that opt in; no third-party general agent possible on iOS |
| **Grok Bot** (xAI, Aug 2026) | Operates a computer for you; Android available | Grok only | xAI cloud | Only on SuperGrok Heavy / Cursor Ultra / Teams Premium plans. Free "Tasks" are Zapier-style workflows |
| **Claude app** (Anthropic) | Chat; remote for Claude Code (Remote Control) and Cowork (Dispatch) | Claude | **Your desktop or the cloud**; the phone is only a remote | Needs a computer running elsewhere; Dispatch closed to new users |
| **ChatGPT / Perplexity** | Chat, voice, research | Their own | Cloud | Great answers, but few real files and no phone control |
| **Operit** (open source, 8.1k★, LGPL-3.0) | The closest thing: agent with Ubuntu 24.04 terminal, files, browser automation, phone control (Accessibility/Shizuku/root), MCP, skills, workflows, voice | Cloud + local (GGUF via llama.cpp, MNN, Ollama, LM Studio) | Phone | Power-user complexity; APK sideload only; ARM64 only |
| **OpenClaw Android / AnyClaw** (open source) | Personal agent with terminal and gateway; AnyClaw bundles OpenClaw + Codex + Claude Code in a Linux environment on the phone | Bring your own key; local via Ollama | Phone | A terminal-first developer tool, not a simple app for everyone |
| **Local-model apps**: Google AI Edge Gallery, PocketPal, MLC Chat | Chat with on-device models, offline | Gemma, Qwen, Llama, Phi | Phone | Chat only: no tools, no documents, no agent |
| **Document apps**: Acrobat mobile (+ AI Assistant add-on), PDFgear, UPDF, PDF Copilot | Edit and annotate PDFs, chat with a PDF, summarize, translate | Their cloud models | Cloud | Single-purpose; subscriptions; can't build a report from several sources or act across apps |
| **Linux on the phone**: Android 16 Linux terminal (Debian VM), Termux + proot | Real Python/Node/git on the phone | Anything you install | Phone | A terminal, not a product. Claude Code has had no Android build since v2.1.113 (April 2026) |

## 2. How good is the technology right now

**Phone control (an agent tapping through apps) is still unreliable.**
- In a hands-on test of 65 real tasks, the best open framework (DroidRun) succeeded **43%** of the time. Others scored 29%, 14% and 7% ([AIMultiple, June 2026](https://aimultiple.com/mobile-ai-agent)).
- On the harder MobileWorld benchmark, the best agent reaches **51.7%** ([MobileWorld](https://arxiv.org/html/2512.19432v1)). The 90%+ scores on the older AndroidWorld benchmark are self-reported and saturated.
- Our own measurements in this repo: turning on airplane mode took Agnes (`agnes-3.0-flash`) about **5 s per step** and Gemini about **35 s per step**. Free tiers were about 20 requests *per minute* for Agnes and about 20 requests in total before Gemini's quota ran out.

**Local (on-device) models are real, but small.**
- 8 GB phones run 1.5–3B models at 10–20 tokens/s. A Galaxy S25 Ultra runs Qwen3 1.7B at about **40 tokens/s** on its NPU ([PromptQuorum](https://www.promptquorum.com/power-local-llm/best-local-llm-apps-android-2026)).
- Gemma 4 E2B runs in **under 1.5 GB** of memory and reached 31 tokens/s on a Qualcomm NPU ([RunLocalModel](https://runlocalmodel.com/gemma-on-phone-2026.html)).
- That's plenty for summarizing, rewriting, translating and Q&A over a document. It's too weak for long multi-step agent work, so the app should be **hybrid**: local by default for private and quick jobs, a cloud key or your own PC for heavy ones.
- Google's **LiteRT-LM** runtime gives Android apps on-device models with GPU/NPU acceleration and built-in tool calling. It has Kotlin and Flutter APIs ([LiteRT-LM](https://ai.google.dev/edge/litert-lm/overview)).

**Documents on the phone are solved at the library level.**
- Apache POI creates and edits DOCX/XLSX/PPTX inside Android apps ([poi-on-android](https://github.com/centic9/poi-on-android)).
- Android can write PDFs natively. Rendering and text extraction are available through libraries such as the open-source Fadocx viewer, which pairs POI with LibreOfficeKit ([Fadocx](https://github.com/anonfaded/Fadocx)).
- What's missing is an *agent* that uses these tools. For example: "turn these three PDFs into a two-page Word summary", or "this photo of a table → Excel".

## 3. The gap

| | Simple for everyone | Any model / offline | Makes real files | Agent tools | Free to start |
|---|---|---|---|---|---|
| Big-tech assistants | ✅ | ❌ | ⚠️ limited | ⚠️ their apps only | ⚠️ paywalls |
| Open-source agents (Operit, OpenClaw) | ❌ | ✅ | ⚠️ via terminal | ✅ | ✅ |
| Document apps | ✅ | ❌ | ✅ PDFs | ❌ | ⚠️ subscriptions |
| Local-model apps | ✅ | ✅ | ❌ | ❌ | ✅ |
| **The app proposed here** | ✅ | ✅ | ✅ | ✅ | ✅ |

## 4. The concept

**One screen: a chat box and your files.** Everything else appears only when needed.

- **Share anything in.** From any app's share menu: a PDF, a Word file, a photo of paper, a web page. The same goes for results: every file it makes can be opened, shared or saved.
- **Makes real files, not just answers.** "Summarize these contracts into a one-page DOCX." "Make a spreadsheet from this receipt photo." "Turn my notes into a 5-slide deck." "Fill in this PDF form."
- **Your model, your choice.** On-device (Gemma/Qwen via LiteRT-LM), your own PC (Ollama or LM Studio over Wi-Fi), or any cloud key (Gemini, Agnes, OpenRouter, Claude, OpenAI). The app adds no extra content filter on top of the model you pick.
- **Agent tools behind the scenes:** read and write files, web search and fetch, run Python for data work, and optionally operate other apps. That's the loop this repo already has, moved onto the phone.
- **Autonomy dial:** *ask every step* · *ask before irreversible actions* (default) · *full auto for this task*.

### About "no limits"

The limits people actually hit are **quotas, refusals to make real files, forced cloud, and paywalls**. This app removes all four: local or bring-your-own-key models, real file and code tools, offline by default, free to start.

Two things stay on by default because they protect *you from the agent*, not from yourself. **Confirmation before irreversible actions** (send, pay, delete) is one; agents fail more than half of real phone tasks. **Treating document and screen text as data, not orders** is the other; a 2026 study hijacked a mobile agent with injected text in 82% of attempts ([arXiv 2608.08939](https://arxiv.org/abs/2608.08939)).

One shipping fact: Google Play requires AI apps to disclose AI-generated content, offer in-app reporting, and block restricted content (policy of July 15, 2026). It also restricts non-assistive Accessibility use ([Play policy](https://support.google.com/googleplay/android-developer/answer/17134731)). So a Play Store build follows those rules, and power features like phone control ship as a direct APK, as Operit does.

## 5. Build plan (phased, small first)

- **Phase 0: done (this repo).** The agent core has two providers behind one interface: Gemini computer use, and Agnes / any OpenAI-compatible API. It includes phone control, confirmation gate, retries, run logs and 12 offline tests, and was verified live on an emulator.
- **Phase 1: "docs first" phone app (proposed next; not started).** Kotlin + Jetpack Compose:
  - A chat screen and a file workspace, with share-sheet intake.
  - Providers: any OpenAI-compatible endpoint (Agnes, OpenRouter, Ollama or LM Studio on your PC) plus Gemini.
  - Tools: read PDF/DOCX/XLSX; write DOCX/XLSX/PDF; web fetch.
  - The autonomy dial.
  - **Done when:** on a real phone, "turn these two PDFs into a one-page Word summary" produces a correct DOCX you can open and share.
- **Phase 2.** An on-device model (Gemma via LiteRT-LM), camera and OCR scanning, a Python sandbox, and phone control via AccessibilityService in a sideload build, porting this repo's loop.
- **Phase 3.** Connect to a PC or cloud runner (Claude Code, Codex, OpenClaw) for coding tasks; add voice, saved workflows, and an iOS version (share sheet + App Intents only, since iOS allows no general phone control).

**Why Kotlin rather than Flutter for Phase 1:** everything that makes this app different is Android-native. That means the share sheet, Accessibility, Apache POI, and LiteRT-LM's Kotlin API. Flutter only wins if iOS matters from day one.

## 6. Risks

- **Small local models** are weak at multi-step work. That's why the plan is hybrid, not "local only".
- **Prompt injection from documents.** A PDF can contain instructions, so the confirmation gate stays on by default.
- **Competition.** Gemini Intelligence will be on every new Pixel and Galaxy, and Operit already exists for power users. The edge has to be *simplicity + documents + any model*.
- **Battery and heat** with on-device models; **Play Store review** for AI and Accessibility features.

## Sources

- [Gemini Intelligence brings app automation to Android (Engadget)](https://www.engadget.com/2170770/gemini-intelligence-brings-app-automation-to-android/)
- [Grok Bot explained (Layer3 Labs)](https://www.layer3labs.io/guides/what-is-grok-bot) · [Grok features 2026 (Suprmind)](https://suprmind.ai/hub/grok/grok-features/)
- [Claude Code on mobile (docs)](https://code.claude.com/docs/en/mobile) · [Claude Code on your phone (Sealos)](https://sealos.io/blog/claude-code-on-phone/) · [Claude Cowork](https://claude.com/product/cowork) · [Dispatch (Forbes)](https://www.forbes.com/sites/ronschmelzer/2026/03/20/claude-dispatch-lets-you-control-claude-cowork-with-your-phone/)
- [Operit (GitHub)](https://github.com/AAswordman/Operit) · [OpenClaw Android docs](https://docs.openclaw.ai/platforms/android) · [AnyClaw (GitHub)](https://github.com/OpenClawAndroid/openclaw-android-assistant)
- [Local LLM apps on Android 2026 (PromptQuorum)](https://www.promptquorum.com/power-local-llm/best-local-llm-apps-android-2026) · [Gemma on phone (RunLocalModel)](https://runlocalmodel.com/gemma-on-phone-2026.html) · [LiteRT-LM](https://ai.google.dev/edge/litert-lm/overview)
- [Mobile AI agents tested across 65 tasks (AIMultiple)](https://aimultiple.com/mobile-ai-agent) · [MobileWorld benchmark](https://arxiv.org/html/2512.19432v1) · [Not an A11y: prompt injection (arXiv)](https://arxiv.org/abs/2608.08939)
- [Best PDF editor apps 2026 (Zapier)](https://zapier.com/blog/best-pdf-editor-apps/) · [Acrobat for Copilot](https://helpx.adobe.com/acrobat/web/use-acrobat-extensions/acrobat-for-copilot/overview.html) · [poi-on-android](https://github.com/centic9/poi-on-android) · [Fadocx](https://github.com/anonfaded/Fadocx)
- [Android 16 Linux terminal (MakeUseOf)](https://www.makeuseof.com/used-new-linux-terminal-on-android-impressed/) · [AI coding on Android with Termux (DEV)](https://dev.to/zecelmanatad/running-claude-code-ollama-and-openclaw-on-android-using-termux-ubuntu-2026-guide-1346)
- [Google Play policy announcement, July 15 2026](https://support.google.com/googleplay/android-developer/answer/17134731) · [Play AI-generated content policy](https://support.google.com/googleplay/android-developer/answer/14094294?hl=en)
