"""ADB bridge: executes Gemini's mobile computer-use actions on a real device or emulator.

Gemini returns coordinates on a normalized 0-999 grid; every handler converts them to
physical pixels. Handler names match the model's predefined mobile function names.
"""

import io
import os
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path

from PIL import Image

# Common app names the model is likely to use, mapped to stock Android / Google packages.
KNOWN_APPS = {
    "settings": "com.android.settings",
    "chrome": "com.android.chrome",
    "youtube": "com.google.android.youtube",
    "gmail": "com.google.android.gm",
    "maps": "com.google.android.apps.maps",
    "google maps": "com.google.android.apps.maps",
    "photos": "com.google.android.apps.photos",
    "camera": "com.android.camera2",
    "clock": "com.google.android.deskclock",
    "calendar": "com.google.android.calendar",
    "contacts": "com.google.android.contacts",
    "phone": "com.google.android.dialer",
    "messages": "com.google.android.apps.messaging",
    "play store": "com.android.vending",
    "google play": "com.android.vending",
    "files": "com.google.android.documentsui",
    "calculator": "com.google.android.calculator",
}

KEYCODES = {
    "home": 3, "back": 4, "call": 5, "volume_up": 24, "volume_down": 25, "power": 26,
    "camera": 27, "tab": 61, "space": 62, "enter": 66, "del": 67, "backspace": 67,
    "delete": 67, "menu": 82, "search": 84, "app_switch": 187, "recents": 187,
}


def find_adb() -> str:
    for root in (os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk")):
        if root:
            exe = Path(root) / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb")
            if exe.exists():
                return str(exe)
    adb = shutil.which("adb")
    if not adb:
        raise RuntimeError("adb not found. Install Android platform-tools or set ANDROID_HOME.")
    return adb


class ADBBridge:
    def __init__(self, device_id: str | None = None, screenshot_width: int = 720):
        self.prefix = [find_adb()] + (["-s", device_id] if device_id else [])
        self.screenshot_width = screenshot_width
        self._ensure_device()
        self.width, self.height = self._screen_size()

    # ---- plumbing -------------------------------------------------------------

    def _run(self, *args: str, check: bool = True) -> str:
        result = subprocess.run(self.prefix + list(args), capture_output=True)
        out = result.stdout.decode("utf-8", errors="replace")
        if check and result.returncode != 0:
            err = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"adb {' '.join(args)} failed: {err or out}")
        return out

    def _shell(self, command: str, check: bool = True) -> str:
        return self._run("shell", command, check=check)

    def _ensure_device(self):
        state = subprocess.run(self.prefix + ["get-state"], capture_output=True, text=True)
        if state.returncode != 0 or state.stdout.strip() != "device":
            raise RuntimeError("No Android device connected. Start an emulator or plug in a phone "
                               "with USB debugging enabled, then check `adb devices`.")

    def _screen_size(self) -> tuple[int, int]:
        out = self._shell("wm size")
        sizes = dict(re.findall(r"(Physical|Override) size: (\d+x\d+)", out))
        w, h = (sizes.get("Override") or sizes.get("Physical", "1080x1920")).split("x")
        return int(w), int(h)

    def _px(self, x: float, y: float) -> tuple[int, int]:
        return round(x / 1000 * self.width), round(y / 1000 * self.height)

    def screenshot(self) -> bytes:
        """PNG of the current screen, downscaled to keep requests small."""
        raw = subprocess.run(self.prefix + ["exec-out", "screencap", "-p"], capture_output=True)
        if raw.returncode != 0 or not raw.stdout.startswith(b"\x89PNG"):
            raise RuntimeError("screencap failed: " + raw.stderr.decode(errors="replace"))
        img = Image.open(io.BytesIO(raw.stdout)).convert("RGB")
        if img.width > self.screenshot_width:
            img = img.resize((self.screenshot_width, round(img.height * self.screenshot_width / img.width)))
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()

    def launcher_packages(self) -> list[str]:
        out = self._shell("cmd package query-activities --brief -a android.intent.action.MAIN "
                          "-c android.intent.category.LAUNCHER", check=False)
        pkgs = sorted({line.strip().split("/")[0] for line in out.splitlines() if "/" in line})
        if pkgs:
            return pkgs
        out = self._shell("pm list packages")
        return sorted(line.split(":", 1)[1].strip() for line in out.splitlines() if line.startswith("package:"))

    def foreground_package(self) -> str:
        out = self._shell("dumpsys window", check=False)
        match = re.search(r"mCurrentFocus=Window\{\S+ \S+ ([\w.]+)/", out)
        return match.group(1) if match else ""

    # ---- model actions (names match Gemini's mobile computer-use functions) ----

    def click(self, x, y, **_):
        px, py = self._px(x, y)
        self._shell(f"input tap {px} {py}")

    def long_press(self, x, y, seconds=2, **_):
        px, py = self._px(x, y)
        self._shell(f"input swipe {px} {py} {px} {py} {int(float(seconds) * 1000)}")

    def drag_and_drop(self, start_x, start_y, end_x, end_y, **_):
        sx, sy = self._px(start_x, start_y)
        ex, ey = self._px(end_x, end_y)
        self._shell(f"input swipe {sx} {sy} {ex} {ey} 400")

    def type(self, text, press_enter=False, **_):
        if not text.isascii():
            raise ValueError("adb can only type ASCII text; rephrase without special characters.")
        if text:
            # `input text` treats %s as a space; quote the rest for the device shell.
            self._shell("input text " + shlex.quote(text.replace(" ", "%s")))
        if press_enter:
            self._shell(f"input keyevent {KEYCODES['enter']}")

    def press_key(self, key, **_):
        name = str(key).strip().lower().removeprefix("keycode_")
        code = KEYCODES.get(name, name if name.isdigit() else None)
        if code is None:
            raise ValueError(f"Unsupported key '{key}'. Use one of: {', '.join(sorted(KEYCODES))}.")
        self._shell(f"input keyevent {code}")

    def go_back(self, **_):
        self._shell(f"input keyevent {KEYCODES['back']}")

    def open_app(self, app_name=None, package_name=None, **_):
        name = (package_name or app_name or "").strip()
        if not name:
            raise ValueError("open_app needs an app_name.")
        installed = self.launcher_packages()
        pkg = name if name in installed else KNOWN_APPS.get(name.lower())
        if pkg not in installed:
            needle = re.sub(r"[^a-z0-9]", "", name.lower())
            matches = [p for p in installed if needle and needle in p.lower().replace("_", "")]
            pkg = matches[0] if matches else None
        if not pkg:
            raise ValueError(f"App '{name}' not found. Call list_apps to see installed packages.")
        out = self._shell(f"monkey -p {pkg} -c android.intent.category.LAUNCHER 1", check=False)
        if "No activities found" in out or "aborted" in out:
            raise RuntimeError(f"Could not launch {pkg}.")
        return {"opened": pkg}

    def list_apps(self, **_):
        return {"apps": self.launcher_packages()}

    def wait(self, seconds=1, **_):
        time.sleep(min(float(seconds), 10))

    def take_screenshot(self, **_):
        return None  # A fresh screenshot is attached to every function result anyway.
