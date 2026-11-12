"""Locks (DESIGN 12.4): one executor per app; one per device when the driver
cannot work in the background. Lock files live in runs/locks/ and expire."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

DEVICE = "_device"
DEFAULT_TTL = 600.0


class LockError(Exception):
    def __init__(self, key: str, holder: dict):
        super().__init__(f"{key} is in use by {holder.get('owner', 'someone')}")
        self.key = key
        self.holder = holder


def _dir(root: Path) -> Path:
    d = Path(root) / "runs" / "locks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path(root: Path, key: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in key)
    return _dir(root) / f"{safe}.lock"


def _alive(pid) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except (PermissionError, OSError):
        return True
    return True


def holder(root: Path, key: str) -> dict | None:
    """Who holds a lock right now (None when free, expired or orphaned)."""
    p = _path(root, key)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if data.get("expires", 0) < time.time() or not _alive(data.get("pid")):
        try:
            p.unlink()
        except OSError:
            pass
        return None
    return data


def _take(root: Path, key: str, owner: str, ttl: float) -> bool:
    """Returns True when the lock was newly taken, False when re-entered."""
    p = _path(root, key)
    payload = json.dumps({"key": key, "owner": owner, "pid": os.getpid(), "expires": time.time() + ttl})
    for _ in range(2):
        try:
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            cur = holder(root, key)
            if cur is None:
                continue                        # stale lock was just removed; retry
            if cur.get("owner") == owner and cur.get("pid") == os.getpid():
                p.write_text(payload, encoding="utf-8")      # re-entrant refresh
                return False
            raise LockError(key, cur)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        return True
    raise LockError(key, holder(root, key) or {})


def acquire(root: Path, app: str | None, owner: str, *, device_wide: bool = False,
            ttl: float = DEFAULT_TTL) -> list[str]:
    """Take the lock needed to operate `app`. Returns the keys newly taken
    (empty when this owner already held it, so a nested run does not release it)."""
    key = DEVICE if (device_wide or not app) else app
    if key != DEVICE:
        dev = holder(root, DEVICE)
        if dev and not (dev.get("owner") == owner and dev.get("pid") == os.getpid()):
            raise LockError(DEVICE, dev)
    else:
        for p in _dir(root).glob("*.lock"):
            other = holder(root, p.stem)
            if other and p.stem != DEVICE and not (other.get("owner") == owner and other.get("pid") == os.getpid()):
                raise LockError(p.stem, other)
    return [key] if _take(root, key, owner, ttl) else []


def release(root: Path, keys: list[str], owner: str | None = None):
    for key in keys:
        p = _path(root, key)
        cur = holder(root, key)
        if cur and (owner is None or cur.get("owner") == owner):
            try:
                p.unlink()
            except OSError:
                pass
