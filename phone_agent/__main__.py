"""CLI: python -m phone_agent "Turn on airplane mode" """

import argparse
import os
import sys
import time
from pathlib import Path

from .adb import ADBBridge


def load_dotenv(path: Path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():  # -sig: Windows editors add a BOM
        key, sep, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        if sep and key and not key.startswith("#"):
            os.environ.setdefault(key, value.strip().strip('"').strip("'"))


def dry_run(bridge: ADBBridge):
    """Exercise the phone bridge without calling Gemini."""
    print(f"Device screen: {bridge.width}x{bridge.height}")
    print(f"Screenshot: {len(bridge.screenshot()) // 1024} KB (downscaled PNG)")
    print(f"Launcher apps: {len(bridge.launcher_packages())}")
    steps = [
        ("press_key", {"key": "home"}),
        ("open_app", {"app_name": "Settings"}),
        ("drag_and_drop", {"start_x": 500, "start_y": 750, "end_x": 500, "end_y": 300}),
        ("go_back", {}),
    ]
    for name, args in steps:
        result = getattr(bridge, name)(**args)
        time.sleep(1.5)
        print(f"  ok  {name}({args}) -> foreground: {bridge.foreground_package()} {result or ''}")
        if name == "open_app" and bridge.foreground_package() != "com.android.settings":
            sys.exit("FAIL: Settings did not open")
    print("Dry run passed: the bridge can see and drive the phone.")


def main():
    parser = argparse.ArgumentParser(prog="phone_agent", description="Let Gemini operate an Android phone.")
    parser.add_argument("task", nargs="*", help="What you want done, in plain language")
    parser.add_argument("-m", "--model", default="gemini-3.7-flash", help="Gemini model id (default: %(default)s)")
    parser.add_argument("-t", "--thinking-level", default="medium", choices=["minimal", "low", "medium", "high"])
    parser.add_argument("-n", "--max-steps", type=int, default=30, help="Hard cap on actions (default: %(default)s)")
    parser.add_argument("-d", "--device", help="ADB serial, if more than one device is connected")
    parser.add_argument("--dry-run", action="store_true", help="Test the phone bridge only; no API calls")
    parser.add_argument("--no-log", action="store_true", help="Don't save screenshots/actions to runs/")
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    load_dotenv(Path.cwd() / ".env")

    try:
        bridge = ADBBridge(args.device)
    except RuntimeError as e:
        sys.exit(f"Error: {e}")
    if args.dry_run:
        return dry_run(bridge)

    task = " ".join(args.task).strip()
    if not task:
        parser.error("give a task, e.g.  python -m phone_agent \"Turn on airplane mode\"")
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        sys.exit("Error: set GEMINI_API_KEY (in your environment or a .env file). "
                 "Get a key at https://aistudio.google.com/apikey")

    from google import genai  # imported late so --dry-run works without the SDK configured
    from .agent import PhoneAgent

    agent = PhoneAgent(genai.Client(api_key=api_key), bridge, model=args.model,
                       thinking_level=args.thinking_level, max_steps=args.max_steps,
                       log_dir=None if args.no_log else "runs")
    try:
        summary = agent.run(task)
    except KeyboardInterrupt:
        summary = "Stopped by you (Ctrl+C)."
    except Exception as e:
        summary = f"API error: {e}"
        if "API_KEY_INVALID" in str(e):
            summary = "API error: your Gemini API key was rejected. Check GEMINI_API_KEY."
        elif "404" in str(e) or "not found" in str(e).lower():
            summary += "\nTry another model, e.g. --model gemini-3.8-flash"
    print(f"\nResult: {summary}\nActions taken: {agent.actions_taken}")
    if agent.run_dir and agent.run_dir.exists():
        print(f"Run log: {agent.run_dir}")


if __name__ == "__main__":
    main()
