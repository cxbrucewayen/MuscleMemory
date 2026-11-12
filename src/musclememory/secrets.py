"""Secrets (DESIGN 13, SECURITY 3.5).

Values live outside the repository (a per-user .env file or the OS keychain)
and only ever flow into `type` / `clipboard`. Everything else sees `***`.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
from pathlib import Path

from .cards import load_config, user_home

NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
PREFIX = "KB_SECRET_"
SERVICE = "cua-experience"
MASK = "***"


class SecretError(Exception):
    pass


class Secret:
    """A handle to a secret. Printing, logging or serialising it yields ***."""

    __slots__ = ("name", "_store")

    def __init__(self, name: str, store: SecretStore):
        self.name = name
        self._store = store

    def reveal(self) -> str:
        value = self._store.get(self.name)
        if value is None:
            raise SecretError(f"secret {self.name} is not stored; run `kb secret set {self.name}`")
        return value

    def __str__(self):
        return MASK

    __repr__ = __str__

    def __format__(self, spec):
        return MASK


class SecretStore:
    def __init__(self, backend: str | None = None, home: Path | None = None):
        self.home = Path(home) if home else user_home()
        self.backend = backend or load_config().get("secret_backend") or "auto"
        if self.backend not in ("env", "keychain", "auto"):
            raise SecretError("secret_backend must be env, keychain or auto")

    @property
    def env_path(self) -> Path:
        return self.home / ".env"

    # --- .env backend ----------------------------------------------------------
    def _read_env(self) -> dict[str, str]:
        out = {}
        if not self.env_path.is_file():
            return out
        for line in self.env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line.startswith(PREFIX) or "=" not in line:
                continue          # only KB_SECRET_ lines are read
            k, v = line.split("=", 1)
            out[k[len(PREFIX):].strip()] = v
        return out

    def _write_env(self, data: dict[str, str]):
        self.home.mkdir(parents=True, exist_ok=True)
        keep = []
        if self.env_path.is_file():
            keep = [ln for ln in self.env_path.read_text(encoding="utf-8").splitlines()
                    if not ln.strip().startswith(PREFIX)]
        body = keep + [f"{PREFIX}{k}={v}" for k, v in sorted(data.items())]
        tmp = self.env_path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(body) + "\n")
        os.replace(tmp, self.env_path)
        self._restrict(self.env_path)

    @staticmethod
    def _restrict(path: Path):
        if sys.platform == "win32":
            user = os.environ.get("USERNAME")
            if user:
                subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:F"],
                               capture_output=True, check=False)
        else:
            os.chmod(path, 0o600)

    # --- keychain backend ------------------------------------------------------
    @staticmethod
    def _keyring():
        try:
            import keyring
            return keyring
        except ImportError:
            return None

    def _use_keychain(self, for_write=False) -> bool:
        if self.backend == "env":
            return False
        if self.backend == "keychain":
            if not self._keyring():
                raise SecretError("secret_backend is keychain but the `keyring` package is not installed")
            return True
        return False if for_write else bool(self._keyring())   # auto: .env first, then keychain

    # --- public API ------------------------------------------------------------
    @staticmethod
    def check_name(name: str):
        if not NAME_RE.match(name or ""):
            raise SecretError("secret names use upper-case letters, digits and _ (e.g. OA_PASSWORD)")

    def get(self, name: str) -> str | None:
        self.check_name(name)
        if self.backend != "keychain":
            value = self._read_env().get(name)
            if value is not None:
                return value
        if self._use_keychain():
            return self._keyring().get_password(SERVICE, name)
        return None

    def has(self, name: str) -> bool:
        return self.get(name) is not None

    def handle(self, name: str) -> Secret:
        self.check_name(name)
        return Secret(name, self)

    def set(self, name: str, value: str):
        self.check_name(name)
        if "\n" in value or "\r" in value:
            raise SecretError("a secret cannot contain line breaks")
        if self._use_keychain(for_write=True):
            self._keyring().set_password(SERVICE, name, value)
            return
        data = self._read_env()
        data[name] = value
        self._write_env(data)

    def remove(self, name: str) -> bool:
        self.check_name(name)
        removed = False
        data = self._read_env()
        if name in data:
            del data[name]
            self._write_env(data)
            removed = True
        if self.backend != "env" and self._keyring():
            try:
                self._keyring().delete_password(SERVICE, name)
                removed = True
            except Exception:
                pass
        return removed

    def names(self) -> list[str]:
        """Names only. Keychain entries cannot be enumerated portably."""
        return sorted(self._read_env())

    def check(self, repo_root: Path | None = None) -> list[str]:
        """Problems with where and how the .env file is stored (empty = fine)."""
        problems = []
        p = self.env_path
        if repo_root:
            try:
                p.resolve().relative_to(Path(repo_root).resolve())
                problems.append(f"{p} is inside the repository; move it to the user directory")
            except ValueError:
                pass
        if not p.is_file():
            return problems
        if sys.platform == "win32":
            out = subprocess.run(["icacls", str(p)], capture_output=True, text=True, check=False).stdout
            for group in ("Everyone", "BUILTIN\\Users", "Authenticated Users"):
                if group in out:
                    problems.append(f"{p} is readable by {group}; restrict it to the current user")
        else:
            mode = stat.S_IMODE(p.stat().st_mode)
            if mode & 0o077:
                problems.append(f"{p} has mode {oct(mode)}; it must be 600")
        return problems


def redact(text: str, values: list[str]) -> str:
    """Replace every known secret value in a string with ***."""
    for v in sorted((v for v in values if v), key=len, reverse=True):
        text = text.replace(v, MASK)
    return text
