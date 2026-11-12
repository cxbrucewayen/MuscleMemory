"""The driver interface: the only thing the executor knows about a device."""

from __future__ import annotations

import time
from dataclasses import dataclass

from ..versions import Env


class DriverError(Exception):
    pass


@dataclass
class Node:
    """One element of a UI tree snapshot. Valid for this snapshot only."""
    idx: int
    role: str = ""
    name: str = ""
    id: str = ""
    value: str = ""
    bounds: tuple[float, float, float, float] | None = None   # x, y, w, h (screen)
    parent: int | None = None
    focused: bool = False
    handle: object = None          # driver-private (never stored in a card)

    @property
    def center(self) -> tuple[float, float] | None:
        if not self.bounds:
            return None
        x, y, w, h = self.bounds
        return x + w / 2, y + h / 2

    def structure(self) -> dict:
        """What may go into a hand-off package: structure, not handles."""
        d = {"idx": self.idx, "role": self.role}
        for k in ("name", "id", "value"):
            if getattr(self, k):
                d[k] = getattr(self, k)
        if self.parent is not None:
            d["parent"] = self.parent
        return d


def point(x: float, y: float) -> Node:
    return Node(-1, role="point", bounds=(x, y, 0, 0))


class Driver:
    """Subclass and implement what the device supports; the rest raises DriverError."""

    name = "base"
    background = False        # True when it can act without taking mouse/focus

    # --- environment -----------------------------------------------------------
    def version(self) -> str | None:
        return None

    def platform(self) -> str:
        raise NotImplementedError

    def os_version(self) -> str | None:
        return None

    def lang(self) -> str | None:
        return None

    def display(self) -> str | None:
        return None

    def rom(self) -> str | None:
        return None

    def app_version(self, app_id: str) -> str | None:
        return None

    def user_busy(self, app_id: str | None) -> bool:
        return False

    # --- observation -----------------------------------------------------------
    def foreground(self) -> str | None:
        """app_id of the foreground app, or None when unknown."""
        return None

    def tree(self, app_id: str | None = None) -> list[Node]:
        raise NotImplementedError

    def screenshot(self, path: str) -> bool:
        return False

    # --- actions ---------------------------------------------------------------
    def _unsupported(self, what):
        raise DriverError(f"{self.name} driver does not support {what}")

    def open_app(self, app_id: str):
        self._unsupported("open")

    def click(self, node: Node, button: str = "left", count: int = 1):
        self._unsupported("click")

    def scroll(self, node: Node, direction: str, times: int):
        self._unsupported("scroll")

    def drag(self, src: Node, dst: Node):
        self._unsupported("drag")

    def key(self, combo: str):
        self._unsupported("key")

    def type_text(self, text: str):
        self._unsupported("type")

    def set_clipboard(self, text: str):
        self._unsupported("clipboard")

    def clear_clipboard(self):
        pass

    def move_window(self, node: Node, away_from: Node):
        self._unsupported("move_window")

    # --- time (virtual in the simulator) ---------------------------------------
    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float):
        time.sleep(seconds)

    def close(self):
        pass


def detect_env(driver: Driver, app: str | None = None, app_id: str | None = None,
               overrides: dict | None = None) -> Env:
    """Build the environment snapshot (SKILL step 1). Unknown items become 'unknown'."""
    raw = {"os": f"{driver.platform()} {driver.os_version() or 'unknown'}"}
    if app:
        ver = driver.app_version(app_id) if app_id else None
        raw["app"] = f"{app} {ver or 'unknown'}"
    raw["driver"] = f"{driver.name} {driver.version() or 'unknown'}"
    for key, val in (("lang", driver.lang()), ("display", driver.display()), ("rom", driver.rom())):
        if val:
            raw[key] = val
    raw.update({k: v for k, v in (overrides or {}).items() if v})
    return Env.parse(raw)
