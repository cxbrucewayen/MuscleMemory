"""A declarative UI simulator.

It lets the whole pipeline (resolve -> run -> hand-off -> flow) be exercised in
CI and tried by newcomers without a device. A simulated app is a small state
machine described in YAML; see examples/demo/sim/ for the format.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

from ..cards import load_yaml
from .base import Driver, DriverError, Node

_TPL = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


class SimDriver(Driver):
    name = "sim"
    background = True

    def __init__(self, spec: dict | str | Path):
        if not isinstance(spec, dict):
            spec = load_yaml(Path(spec).read_text(encoding="utf-8"))
        if not isinstance(spec, dict) or "apps" not in spec:
            raise DriverError("simulator file needs an `apps` mapping")
        self.spec = copy.deepcopy(spec)
        self.apps = self.spec["apps"]
        for app in self.apps.values():
            app.setdefault("state", {})
            app.setdefault("nodes", [])
            app.setdefault("keys", [])
            app["_initial"] = copy.deepcopy(app["state"])
        self._fg = self.spec.get("foreground")
        self._clock = 0.0
        self._clipboard = ""
        self._focus: dict[str, str | None] = {}      # app_id -> node key
        self._selected: dict[str, bool] = {}
        self.log: list[str] = []                      # actions performed, for tests

    # --- environment -----------------------------------------------------------
    def version(self):
        return str(self.spec.get("driver_version", "0.1.0"))

    def platform(self):
        return str(self.spec.get("platform", "WIN"))

    def os_version(self):
        v = self.spec.get("os_version")
        return str(v) if v is not None else None

    def lang(self):
        return self.spec.get("lang")

    def display(self):
        return self.spec.get("display")

    def rom(self):
        return self.spec.get("rom")

    def app_version(self, app_id):
        app = self.apps.get(app_id)
        return str(app["version"]) if app and app.get("version") is not None else None

    def user_busy(self, app_id):
        return bool(self.spec.get("user_busy"))

    def now(self):
        return self._clock

    def sleep(self, seconds):
        self._clock += seconds

    # --- state helpers ---------------------------------------------------------
    def _app(self, app_id=None) -> tuple[str, dict]:
        app_id = app_id or self._fg
        if app_id not in self.apps:
            raise DriverError(f"no simulated app {app_id!r} in the foreground")
        return app_id, self.apps[app_id]

    def state(self, app_id=None) -> dict:
        return self._app(app_id)[1]["state"]

    @staticmethod
    def _holds(cond: dict | None, state: dict) -> bool:
        for k, want in (cond or {}).items():
            have = state.get(k)
            if isinstance(want, list):
                if have not in want:
                    return False
            elif have != want:
                return False
        return True

    @staticmethod
    def _fill(value, state: dict):
        if not isinstance(value, str):
            return value
        m = _TPL.fullmatch(value)
        if m:
            return state.get(m.group(1), "")
        return _TPL.sub(lambda m: str(state.get(m.group(1), "")), value)

    def _apply(self, app: dict, changes: dict | None):
        state = app["state"]
        new = {k: self._fill(v, state) for k, v in (changes or {}).items()}
        state.update(new)

    def _visible(self, app: dict) -> list[dict]:
        state = app["state"]
        shown, keys = [], set()
        for n in app["nodes"]:
            if not self._holds(n.get("show_if"), state):
                continue
            if n.get("parent") and n["parent"] not in keys:
                continue
            shown.append(n)
            keys.add(n.get("key"))
        return shown

    def _focused_key(self, app_id: str, app: dict) -> str | None:
        visible = self._visible(app)
        key = self._focus.get(app_id)
        if key and any(n.get("key") == key for n in visible):
            return key
        for n in visible:
            if "edit" in n and n.get("autofocus"):
                return n["key"]
        return None

    # --- observation -----------------------------------------------------------
    def foreground(self):
        return self._fg

    def tree(self, app_id=None):
        try:
            app_id, app = self._app(app_id)
        except DriverError:
            return []
        state = app["state"]
        visible = self._visible(app)
        index = {n.get("key"): i for i, n in enumerate(visible)}
        focus = self._focused_key(app_id, app)
        out = []
        for i, n in enumerate(visible):
            value = self._fill(n.get("value", ""), state)
            if "edit" in n:
                value = state.get(n["edit"], "")
            at = n.get("at")
            bounds = tuple(float(v) for v in at) if at else (0.0, 30.0 * i, 400.0, 24.0)
            out.append(Node(i, role=str(n.get("role", "")), name=str(self._fill(n.get("name", ""), state)),
                            id=str(n.get("id", "")), value=str(value), bounds=bounds,
                            parent=index.get(n.get("parent")), focused=(n.get("key") == focus),
                            handle=n.get("key")))
        return out

    # --- actions ---------------------------------------------------------------
    def open_app(self, app_id):
        if app_id not in self.apps:
            raise DriverError(f"app {app_id!r} is not installed in the simulator")
        self._fg = app_id
        app = self.apps[app_id]
        self._apply(app, app.get("on_open"))
        self._focus[app_id] = None
        self.log.append(f"open {app_id}")

    def _node(self, app: dict, node: Node) -> dict:
        for n in self._visible(app):
            if n.get("key") == node.handle:
                return n
        raise DriverError("stale element: it is no longer on screen")

    def click(self, node, button="left", count=1):
        app_id, app = self._app()
        if node.idx < 0:
            raise DriverError("the simulator cannot click bare coordinates")
        spec = self._node(app, node)
        self.log.append(f"{'right_' if button == 'right' else ''}{'double_' if count == 2 else ''}click {spec.get('key')}")
        self._selected[app_id] = False
        # Clicking a field focuses it; clicking anything else drops the focus,
        # so a newly shown autofocus field takes it.
        self._focus[app_id] = spec["key"] if "edit" in spec else None
        action = spec.get("right_click" if button == "right" else ("double_click" if count == 2 else "click"))
        if action is None and count == 2:
            action = spec.get("click")
        self._apply(app, action)

    def scroll(self, node, direction, times):
        _, app = self._app()
        spec = self._node(app, node)
        self.log.append(f"scroll {spec.get('key')} {direction} {times}")
        self._apply(app, spec.get(f"scroll_{direction}"))

    def drag(self, src, dst):
        _, app = self._app()
        a, b = self._node(app, src), self._node(app, dst)
        self.log.append(f"drag {a.get('key')} {b.get('key')}")
        self._apply(app, (a.get("drag_to") or {}).get(b.get("key")))

    def move_window(self, node, away_from):
        _, app = self._app()
        spec = self._node(app, node)
        self.log.append(f"move_window {spec.get('key')}")
        self._apply(app, spec.get("move"))

    def key(self, combo):
        app_id, app = self._app()
        self.log.append(f"key {combo}")
        low = combo.lower()
        focus = self._focused_key(app_id, app)
        if low in ("ctrl+a", "cmd+a", "meta+a") and focus:
            self._selected[app_id] = True
            return
        if low in ("ctrl+v", "cmd+v", "meta+v") and focus:
            self._insert(app_id, app, focus, self._clipboard)
            return
        for rule in app["keys"]:
            if str(rule.get("key", "")).lower() == low and self._holds(rule.get("if"), app["state"]):
                self._apply(app, rule.get("set"))
                self._selected[app_id] = False
                return

    def _insert(self, app_id, app, focus_key, text):
        spec = next(n for n in app["nodes"] if n.get("key") == focus_key)
        var = spec["edit"]
        current = "" if self._selected.get(app_id) else str(app["state"].get(var, ""))
        app["state"][var] = current + text
        self._selected[app_id] = False

    def type_text(self, text):
        app_id, app = self._app()
        focus = self._focused_key(app_id, app)
        if not focus:
            raise DriverError("nothing is focused to type into")
        self.log.append(f"type <{len(text)} chars>")
        self._insert(app_id, app, focus, text)

    def set_clipboard(self, text):
        self._clipboard = text
        self.log.append("clipboard set")

    def clear_clipboard(self):
        self._clipboard = ""
