"""Android driver over adb + uiautomator.

Uses only stock platform tools. Non-ASCII text needs the ADBKeyBoard IME on the
device (stock `input text` cannot type it); the clipboard is not reachable
through plain adb, so `clipboard` steps are unsupported here.
"""

from __future__ import annotations

import base64
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

from .base import Driver, DriverError, Node

_BOUNDS = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
KEYCODES = {
    "back": 4, "home": 3, "enter": 66, "return": 66, "tab": 61, "space": 62, "delete": 67,
    "backspace": 67, "del": 112, "escape": 111, "esc": 111, "menu": 82, "search": 84,
    "up": 19, "down": 20, "left": 21, "right": 22, "pageup": 92, "pagedown": 93,
    "appswitch": 187, "power": 26, "volumeup": 24, "volumedown": 25,
    "ctrl": 113, "shift": 59, "alt": 57, "meta": 117,
}
ROM_PROPS = [
    ("ro.mi.os.version.name", "HyperOS"), ("ro.miui.ui.version.name", "MIUI"),
    ("ro.build.version.opporom", "ColorOS"), ("ro.vivo.os.version", "OriginOS"),
    ("ro.build.version.magic", "MagicOS"), ("ro.build.version.emui", "EMUI"),
    ("ro.build.version.oneui", "OneUI"),
]


def _keycode(name: str) -> int:
    low = name.lower()
    if low in KEYCODES:
        return KEYCODES[low]
    if len(low) == 1 and "a" <= low <= "z":
        return 29 + ord(low) - ord("a")
    if len(low) == 1 and low.isdigit():
        return 7 + int(low)
    if re.fullmatch(r"f([1-9]|1[0-2])", low):
        return 130 + int(low[1:])
    raise DriverError(f"unknown key {name!r} for adb")


class AdbDriver(Driver):
    name = "adb"
    background = False

    def __init__(self, serial: str | None = None, adb: str | None = None, timeout: float = 30.0):
        self.adb = adb or shutil.which("adb") or "adb"
        self.serial = serial
        self.timeout = timeout

    def _run(self, *args: str, binary=False) -> str:
        cmd = [self.adb] + (["-s", self.serial] if self.serial else []) + list(args)
        try:
            p = subprocess.run(cmd, capture_output=True, timeout=self.timeout)
        except FileNotFoundError:
            raise DriverError("adb was not found on PATH")
        except subprocess.TimeoutExpired:
            raise DriverError(f"adb timed out: {' '.join(args[:3])}")
        if p.returncode != 0:
            raise DriverError(f"adb failed: {p.stderr.decode('utf-8', 'replace').strip()[:200]}")
        return p.stdout.decode("utf-8", "replace")

    def _shell(self, *args: str) -> str:
        return self._run("shell", *args)

    def _prop(self, name: str) -> str:
        return self._shell("getprop", name).strip()

    # --- environment -----------------------------------------------------------
    def version(self):
        m = re.search(r"version (\d+(?:\.\d+)+)", self._run("version"))
        return m.group(1) if m else None

    def platform(self):
        return "ANDROID"

    def os_version(self):
        return self._prop("ro.build.version.release") or None

    def lang(self):
        return self._prop("persist.sys.locale") or self._prop("ro.product.locale") or None

    def display(self):
        m = re.search(r"density:\s*(\d+)", self._shell("wm", "density"))
        return f"density {m.group(1)}" if m else None

    def rom(self):
        for prop, name in ROM_PROPS:
            v = self._prop(prop)
            if v:
                m = re.search(r"\d+(?:\.\d+)*", v)
                return f"{name} {m.group(0)}" if m else name
        return None

    def app_version(self, app_id):
        m = re.search(r"versionName=(\S+)", self._shell("dumpsys", "package", app_id))
        return m.group(1) if m else None

    # --- observation -----------------------------------------------------------
    def tree(self, app_id=None):
        raw = self._run("exec-out", "uiautomator", "dump", "/dev/tty")
        end = raw.rfind("</hierarchy>")
        if end < 0:
            raise DriverError("uiautomator returned no hierarchy (screen may be secure or animating)")
        root = ET.fromstring(raw[raw.find("<"):end + len("</hierarchy>")])
        nodes: list[Node] = []

        def walk(el, parent):
            for child in el.findall("node"):
                a = child.attrib
                m = _BOUNDS.match(a.get("bounds", ""))
                bounds = None
                if m:
                    x1, y1, x2, y2 = (int(g) for g in m.groups())
                    bounds = (x1, y1, x2 - x1, y2 - y1)
                idx = len(nodes)
                text = a.get("text", "")
                nodes.append(Node(idx, role=a.get("class", ""), name=text or a.get("content-desc", ""),
                                  id=a.get("resource-id", ""), value=text, bounds=bounds, parent=parent,
                                  focused=a.get("focused") == "true", handle=a.get("package", "")))
                walk(child, idx)

        walk(root, None)
        return nodes

    def foreground(self):
        nodes = self.tree()
        return nodes[0].handle if nodes else None

    def screenshot(self, path):
        cmd = [self.adb] + (["-s", self.serial] if self.serial else []) + ["exec-out", "screencap", "-p"]
        p = subprocess.run(cmd, capture_output=True, timeout=self.timeout)
        if p.returncode != 0 or not p.stdout:
            return False
        with open(path, "wb") as f:
            f.write(p.stdout)
        return True

    # --- actions ---------------------------------------------------------------
    def open_app(self, app_id):
        self._shell("monkey", "-p", app_id, "-c", "android.intent.category.LAUNCHER", "1")

    def _xy(self, node: Node) -> tuple[str, str]:
        c = node.center
        if c is None:
            raise DriverError("element has no bounds")
        return str(int(c[0])), str(int(c[1]))

    def click(self, node, button="left", count=1):
        x, y = self._xy(node)
        if button == "right":                      # long press
            self._shell("input", "swipe", x, y, x, y, "600")
            return
        for _ in range(count):
            self._shell("input", "tap", x, y)

    def scroll(self, node, direction, times):
        if not node.bounds:
            raise DriverError("element has no bounds")
        x, y, w, h = node.bounds
        cx = str(int(x + w / 2))
        top, bottom = str(int(y + h * 0.3)), str(int(y + h * 0.7))
        a, b = (bottom, top) if direction == "down" else (top, bottom)
        for _ in range(times):
            self._shell("input", "swipe", cx, a, cx, b, "300")

    def drag(self, src, dst):
        x1, y1 = self._xy(src)
        x2, y2 = self._xy(dst)
        self._shell("input", "swipe", x1, y1, x2, y2, "800")

    def key(self, combo):
        codes = [str(_keycode(k)) for k in combo.split("+")]
        if len(codes) == 1:
            self._shell("input", "keyevent", codes[0])
        else:
            self._shell("input", "keycombination", *codes)

    def type_text(self, text):
        if text.isascii():
            escaped = re.sub(r"([\\'\"`$&|;<>()*?#~ ])", lambda m: "%s" if m.group(1) == " " else "\\" + m.group(1), text)
            self._shell("input", "text", escaped)
            return
        ime = self._shell("settings", "get", "secure", "default_input_method")
        if "adbkeyboard" not in ime.lower():
            raise DriverError("non-ASCII input over adb needs the ADBKeyBoard IME to be the active keyboard")
        b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
        self._shell("am", "broadcast", "-a", "ADB_INPUT_B64", "--es", "msg", b64)
