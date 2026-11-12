"""cua-driver adapter (Windows / macOS / Linux desktops).

EXPERIMENTAL. It speaks MCP over stdio to `cua-driver mcp` and was written
against the driver's published tool contract (contract 0.8.0, skill pack
0.47.x): list_apps, list_windows, launch_app, get_window_state with
tree_format=elements, click, type_text, press_key, scroll, drag,
clipboard_write and set_window_frame. It has not been exercised against a
live driver in this repository's CI, so treat failures here as adapter bugs.

Known limits of the contract as read:
  * elements carry role / label / value but no automation id, so `ax id=`
    locators cannot match through this driver;
  * pointer coordinates are derived from element frames relative to the window.
"""

from __future__ import annotations

import json
import locale
import os
import platform as _platform
import shutil
import subprocess
import sys

from .base import Driver, DriverError, Node

PROTOCOL = "2025-06-18"


class _McpClient:
    """A minimal MCP stdio client: newline-delimited JSON-RPC."""

    def __init__(self, argv: list[str]):
        try:
            self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1)
        except FileNotFoundError:
            raise DriverError(f"{argv[0]} was not found; install cua-driver or set CUA_DRIVER_PATH")
        self._id = 0
        self.server = self.request("initialize", {
            "protocolVersion": PROTOCOL, "capabilities": {},
            "clientInfo": {"name": "musclememory", "version": "0.1.0"}})
        self.notify("notifications/initialized", {})

    def _send(self, msg: dict):
        try:
            self.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError):
            raise DriverError("cua-driver closed the connection")

    def notify(self, method: str, params: dict):
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def request(self, method: str, params: dict) -> dict:
        self._id += 1
        rid = self._id
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise DriverError("cua-driver exited unexpectedly")
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("id") != rid:
                if "method" in msg and "id" in msg:      # server-initiated request: decline
                    self._send({"jsonrpc": "2.0", "id": msg["id"],
                                "error": {"code": -32601, "message": "not supported"}})
                continue
            if "error" in msg:
                raise DriverError(f"cua-driver: {msg['error'].get('message', 'error')}")
            return msg.get("result") or {}

    def call(self, tool: str, args: dict) -> dict:
        res = self.request("tools/call", {"name": tool, "arguments": args})
        data = res.get("structuredContent")
        if data is None:
            data = {}
            for item in res.get("content") or []:
                if item.get("type") == "text":
                    try:
                        parsed = json.loads(item["text"])
                        if isinstance(parsed, dict):
                            data = parsed
                            break
                    except ValueError:
                        data.setdefault("_text", item["text"])
        if res.get("isError"):
            err = (data.get("error") or {}) if isinstance(data, dict) else {}
            raise DriverError(f"cua-driver {tool}: {err.get('code') or data.get('_text') or 'failed'}")
        return data

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.terminate()
        except OSError:
            pass


class CuaDriver(Driver):
    name = "cua-driver"
    background = True

    def __init__(self, binary: str | None = None, session: str = "musclememory"):
        self.binary = binary or os.environ.get("CUA_DRIVER_PATH") or shutil.which("cua-driver") or "cua-driver"
        self.session = session
        self._client: _McpClient | None = None
        self._target: dict | None = None      # last window we observed: {"pid", "window_id"}
        self._app_id: str | None = None

    @property
    def client(self) -> _McpClient:
        if self._client is None:
            self._client = _McpClient([self.binary, "mcp"])
        return self._client

    # --- environment -----------------------------------------------------------
    def version(self):
        try:
            out = subprocess.run([self.binary, "--version"], capture_output=True, text=True, timeout=15).stdout
        except (OSError, subprocess.TimeoutExpired):
            return None
        import re
        m = re.search(r"\d+(?:\.\d+)+", out)
        return m.group(0) if m else None

    def platform(self):
        return {"Windows": "WIN", "Darwin": "MAC"}.get(_platform.system(), "LINUX")

    def os_version(self):
        system = _platform.system()
        if system == "Windows":
            return _platform.version()
        if system == "Darwin":
            return _platform.mac_ver()[0] or None
        return _platform.release().split("-")[0] or None

    def lang(self):
        if sys.platform == "win32":
            try:
                import ctypes
                lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
                return locale.windows_locale.get(lang_id, "").replace("_", "-") or None
            except Exception:
                return None
        raw = os.environ.get("LC_ALL") or os.environ.get("LANG") or ""
        code = raw.split(".")[0].replace("_", "-")
        return code if "-" in code else None

    def display(self):
        if sys.platform == "win32":
            try:
                import ctypes
                return f"DPI {round(ctypes.windll.user32.GetDpiForSystem() / 96 * 100)}%"
            except Exception:
                return None
        return None

    def _apps(self) -> list[dict]:
        return self.client.call("list_apps", {}).get("apps") or []

    @staticmethod
    def _is(app: dict, app_id: str) -> bool:
        want = app_id.lower()
        names = [app.get("bundle_id") or "", app.get("name") or "",
                 os.path.basename((app.get("launch_path") or "").strip('"').split('" ')[0])]
        stems = [n.lower() for n in names if n]
        return want in stems or want.removesuffix(".exe") in [s.removesuffix(".exe") for s in stems]

    def _find(self, app_id: str, running=True) -> dict | None:
        for app in self._apps():
            if self._is(app, app_id) and (app.get("running") or not running):
                return app
        return None

    def app_version(self, app_id):
        app = self._find(app_id, running=False)
        path = ((app or {}).get("launch_path") or "").strip('"')
        if not path or not os.path.exists(path):
            return None
        try:
            if sys.platform == "win32":
                out = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "(Get-Item -LiteralPath $args[0]).VersionInfo.ProductVersion", path],
                    capture_output=True, text=True, timeout=20).stdout
            elif sys.platform == "darwin":
                out = subprocess.run(["mdls", "-name", "kMDItemVersion", "-raw", path],
                                     capture_output=True, text=True, timeout=20).stdout
            else:
                return None
        except (OSError, subprocess.TimeoutExpired):
            return None
        out = out.strip()
        return out if out and out[0].isdigit() else None

    # --- observation -----------------------------------------------------------
    def foreground(self):
        if self._app_id:
            app = self._find(self._app_id)
            if app and app.get("active"):
                return self._app_id
        for app in self._apps():
            if app.get("active"):
                return app.get("bundle_id") or app.get("name")
        return None

    def tree(self, app_id=None):
        app_id = app_id or self._app_id
        app = self._find(app_id) if app_id else next((a for a in self._apps() if a.get("active")), None)
        if not app:
            return []
        pid = app["pid"]
        wins = self.client.call("list_windows", {"pid": pid, "on_screen_only": True}).get("windows") or []
        wins.sort(key=lambda w: -(w.get("z_index") or 0))
        nodes: list[Node] = []
        for w in wins:
            wid = w["window_id"]
            state = self.client.call("get_window_state", {
                "pid": pid, "window_id": wid, "tree_format": "elements",
                "include_screenshot": False, "session": self.session})
            b = state.get("window_bounds") or w.get("bounds") or {}
            origin = (b.get("x", 0.0), b.get("y", 0.0))
            root = len(nodes)
            target = {"pid": pid, "window_id": wid, "origin": origin}
            nodes.append(Node(root, role="Window", name=state.get("window_title") or w.get("title") or "",
                              bounds=(origin[0], origin[1], b.get("width", 0.0), b.get("height", 0.0)),
                              handle={"target": target}))
            base = len(nodes)
            index_of = {}
            for el in state.get("elements") or []:
                idx = len(nodes)
                index_of[el["element_index"]] = idx
                f = el.get("frame")
                parent = index_of.get(el.get("parent_index"), root) if el.get("parent_index") is not None else root
                nodes.append(Node(idx, role=el.get("role") or "", name=el.get("label") or "",
                                  value=el.get("value") or "",
                                  bounds=(f["x"], f["y"], f["w"], f["h"]) if f else None, parent=parent,
                                  handle={"target": target, "token": el.get("element_token")}))
            if self._target is None or base == 1:
                self._target = target
        return nodes

    # --- actions ---------------------------------------------------------------
    def _window(self, node: Node | None = None) -> dict:
        t = (node.handle or {}).get("target") if node is not None and isinstance(node.handle, dict) else self._target
        if not t:
            raise DriverError("no target window; observe the app first")
        return {"kind": "window", "pid": t["pid"], "window_id": t["window_id"]}

    def _local(self, node: Node) -> tuple[float, float]:
        t = (node.handle or {}).get("target") if isinstance(node.handle, dict) else self._target
        c = node.center
        if c is None or not t:
            raise DriverError("element has no frame")
        return c[0] - t["origin"][0], c[1] - t["origin"][1]

    def _act(self, tool: str, args: dict) -> dict:
        args.setdefault("session", self.session)
        out = self.client.call(tool, args)
        if out.get("effect") == "refused":
            err = out.get("error") or {}
            raise DriverError(f"cua-driver refused {tool}: {err.get('code') or out.get('hint') or 'refused'}")
        return out

    def open_app(self, app_id):
        self._app_id = app_id
        if self._find(app_id):
            return
        key = "bundle_id" if sys.platform == "darwin" else "name"
        value = app_id if key == "bundle_id" else app_id.removesuffix(".exe")
        self.client.call("launch_app", {key: value})

    def click(self, node, button="left", count=1):
        args = {"target": self._window(node), "delivery_mode": "background", "button": button, "count": count}
        token = (node.handle or {}).get("token") if isinstance(node.handle, dict) else None
        if token:
            args["element_token"] = token
        else:
            args["x"], args["y"] = self._local(node)
        self._act("click", args)

    def scroll(self, node, direction, times):
        x, y = self._local(node)
        self._act("scroll", {"target": self._window(node), "direction": direction, "amount": times,
                             "by": "line", "x": x, "y": y})

    def drag(self, src, dst):
        x1, y1 = self._local(src)
        x2, y2 = self._local(dst)
        self._act("drag", {"target": self._window(src), "from_x": x1, "from_y": y1, "to_x": x2, "to_y": y2})

    def key(self, combo):
        parts = combo.split("+")
        args = {"key": parts[-1].lower(), "target": self._window()}
        if len(parts) > 1:
            args["modifiers"] = [p.lower() for p in parts[:-1]]
        self._act("press_key", args)

    def type_text(self, text):
        self._act("type_text", {"target": self._window(), "text": text})

    def set_clipboard(self, text):
        self._act("clipboard_write", {"text": text})

    def clear_clipboard(self):
        try:
            self._act("clipboard_write", {"text": ""})
        except DriverError:
            pass

    def move_window(self, node, away_from):
        t = self._window(node)
        if not node.bounds or not away_from.bounds:
            raise DriverError("window frames are unknown")
        _, y, w, h = node.bounds
        ax, _, aw, _ = away_from.bounds
        self._act("set_window_frame", {"pid": t["pid"], "window_id": t["window_id"],
                                       "x": ax + aw + 8, "y": y, "width": w, "height": h})

    def close(self):
        if self._client:
            self._client.close()
            self._client = None
