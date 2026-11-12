"""Drivers: how the executor reaches a device.

  sim:<file.yaml>   declarative simulator (demo, tests, CI)
  adb[:<serial>]    Android over adb + uiautomator
  cua               desktop apps through cua-driver (experimental adapter)
"""

from __future__ import annotations

from .base import Driver, DriverError, Node, detect_env
from .locate import locate


def make_driver(spec: str | None) -> Driver:
    if not spec:
        raise DriverError("no driver configured: pass --driver sim:<file>, adb[:serial] or cua "
                          "(or set KB_DRIVER / driver: in ~/.cua-experience/config.yaml)")
    kind, _, arg = spec.partition(":")
    kind = kind.lower()
    if kind == "sim":
        from .sim import SimDriver
        if not arg:
            raise DriverError("sim driver needs a file: sim:<file.yaml>")
        return SimDriver(arg)
    if kind == "adb":
        from .adb import AdbDriver
        return AdbDriver(arg or None)
    if kind in ("cua", "cua-driver"):
        from .cua import CuaDriver
        return CuaDriver(arg or None)
    raise DriverError(f"unknown driver {kind!r} (expected sim, adb or cua)")


__all__ = ["Driver", "DriverError", "Node", "detect_env", "locate", "make_driver"]
