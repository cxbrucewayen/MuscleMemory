"""Version ranges and `applies` matching (DESIGN section 5 and 8)."""

from __future__ import annotations

import re
from dataclasses import dataclass

APPLIES_KEYS = ("os", "app", "driver", "lang", "display", "rom")
RANGED_KEYS = ("os", "app", "driver", "rom")       # "<NAME> <range>"
EXACT_KEYS = ("lang", "display")                    # compared as plain strings
PLATFORMS = ("COMMON", "WIN", "MAC", "LINUX", "ANDROID", "IOS", "HARMONY")

_CONSTRAINT = re.compile(r"^(>=|<=|=|>|<)(\d+(?:\.\d+)*)$")
_VERSION = re.compile(r"^\d+(?:\.\d+)*")


class RangeError(ValueError):
    pass


def parse_version(s) -> tuple[int, ...] | None:
    """'4.10.2' -> (4, 10, 2). Returns None for unknown / unparsable versions."""
    if s is None:
        return None
    m = _VERSION.match(str(s).strip())
    if not m:
        return None
    return tuple(int(p) for p in m.group(0).split("."))


def _cmp(a: tuple[int, ...], b: tuple[int, ...]) -> int:
    n = max(len(a), len(b))
    a = a + (0,) * (n - len(a))
    b = b + (0,) * (n - len(b))
    return (a > b) - (a < b)


@dataclass(frozen=True)
class Range:
    """A version range: 'any' or a conjunction of constraints."""
    constraints: tuple[tuple[str, tuple[int, ...]], ...] = ()

    @property
    def is_any(self) -> bool:
        return not self.constraints

    def contains(self, v: tuple[int, ...]) -> bool:
        for op, bound in self.constraints:
            c = _cmp(v, bound)
            ok = {"=": c == 0, ">=": c >= 0, ">": c > 0, "<=": c <= 0, "<": c < 0}[op]
            if not ok:
                return False
        return True

    @property
    def specificity(self) -> int:
        if self.is_any:
            return 0
        ops = {op for op, _ in self.constraints}
        if "=" in ops:
            return 3
        lower = bool(ops & {">=", ">"})
        upper = bool(ops & {"<=", "<"})
        return 2 if (lower and upper) else 1

    def distance(self, v: tuple[int, ...]) -> float:
        """How far a version is from this range (0 when inside)."""
        if self.contains(v):
            return 0.0
        return min((abs(_as_number(v) - _as_number(b)) for _, b in self.constraints), default=0.0)


def _as_number(v: tuple[int, ...]) -> float:
    v = (v + (0, 0, 0))[:3]
    return v[0] * 1e6 + v[1] * 1e3 + min(v[2], 999)


def parse_range(tokens: list[str]) -> Range:
    if tokens == ["any"]:
        return Range()
    if not tokens:
        raise RangeError("missing version range (use 'any' for any version)")
    out = []
    for t in tokens:
        m = _CONSTRAINT.match(t)
        if not m:
            raise RangeError(f"bad version constraint {t!r} (expected any, =1.2, >=1.2, <1.2)")
        out.append((m.group(1), parse_version(m.group(2))))
    return Range(tuple(out))


@dataclass(frozen=True)
class Spec:
    """One `applies` entry of a ranged key, e.g. ``WECHAT >=4.0 <4.2``."""
    name: str | None       # None means "any name"
    range: Range


def parse_spec(key: str, value) -> Spec:
    toks = str(value).split()
    if not toks:
        raise RangeError(f"applies.{key} is empty")
    if toks == ["any"]:
        return Spec(None, Range())
    return Spec(toks[0], parse_range(toks[1:]))


def parse_applies(applies: dict) -> dict:
    """Validate and parse an `applies` mapping. Raises RangeError."""
    if not isinstance(applies, dict):
        raise RangeError("applies must be a mapping")
    out = {}
    for k, v in applies.items():
        if k not in APPLIES_KEYS:
            raise RangeError(f"unknown applies key {k!r}")
        if k in RANGED_KEYS:
            out[k] = parse_spec(k, v)
        else:
            if not isinstance(v, str) or not v.strip():
                raise RangeError(f"applies.{k} must be a non-empty string")
            out[k] = v.strip()
    if "os" not in out:
        raise RangeError("applies.os is required")
    if out["os"].name is not None and out["os"].name not in PLATFORMS:
        raise RangeError(f"applies.os platform {out['os'].name!r} is not one of {PLATFORMS}")
    return out


@dataclass
class Env:
    """An environment snapshot: ``os: WIN 10.0.22631``, ``app: WECHAT 4.1.2`` ..."""
    raw: dict

    @classmethod
    def parse(cls, raw: dict | None) -> Env:
        raw = dict(raw or {})
        return cls({k: (str(v).strip() if v is not None else None)
                    for k, v in raw.items() if k in APPLIES_KEYS})

    def _split(self, key) -> tuple[str | None, tuple[int, ...] | None]:
        v = self.raw.get(key)
        if not v or v == "unknown":
            return None, None
        toks = v.split()
        name = toks[0]
        ver = parse_version(toks[1]) if len(toks) > 1 and toks[1] != "unknown" else None
        return name, ver

    @property
    def platform(self) -> str | None:
        return self._split("os")[0]

    @property
    def app(self) -> str | None:
        return self._split("app")[0]

    def version(self, key) -> tuple[int, ...] | None:
        return self._split(key)[1]

    def name(self, key) -> str | None:
        return self._split(key)[0]

    def with_app(self, app: str | None, version: str | None) -> Env:
        raw = dict(self.raw)
        if app:
            raw["app"] = f"{app} {version or 'unknown'}"
        else:
            raw.pop("app", None)
        return Env(raw)

    def to_dict(self) -> dict:
        return {k: self.raw[k] for k in APPLIES_KEYS if self.raw.get(k)}

    def describe(self) -> str:
        return " / ".join(self.raw[k] for k in APPLIES_KEYS if self.raw.get(k)) or "unknown"


MATCH, CLUE, NO = "match", "clue", "no"


def match_applies(applies: dict, env: Env) -> tuple[str, float]:
    """Compare a parsed `applies` with an environment.

    Returns (verdict, distance):
      MATCH - the range fully contains the environment
      CLUE  - same platform/app but the version is outside the range or unknown
      NO    - different platform, app, driver or ROM family
    """
    verdict, dist = MATCH, 0.0
    for key in RANGED_KEYS:
        spec: Spec | None = applies.get(key)
        if spec is None or (spec.name is None and spec.range.is_any):
            continue
        name, ver = env.name(key), env.version(key)
        if name is None:
            # The environment does not say. A required rom/driver cannot be confirmed.
            verdict = CLUE
            continue
        if spec.name is not None and name.lower() != spec.name.lower():
            return NO, 0.0
        if spec.range.is_any:
            continue
        if ver is None:
            verdict = CLUE
        elif not spec.range.contains(ver):
            verdict = CLUE
            dist += spec.range.distance(ver)
    for key in EXACT_KEYS:
        want = applies.get(key)
        if want is None:
            continue
        have = env.raw.get(key)
        if not have or have == "unknown":
            verdict = CLUE
        elif have.lower() != want.lower():
            # A different UI language is a different environment: usable only as a clue.
            verdict = CLUE
            dist += 1e9
    return verdict, dist


def specificity(applies: dict) -> int:
    """More written conditions and narrower ranges rank first (DESIGN 8, step 4)."""
    score = 0
    for key in RANGED_KEYS:
        spec = applies.get(key)
        if spec is None:
            continue
        if spec.name is not None:
            score += 1
        score += spec.range.specificity
    for key in EXACT_KEYS:
        if applies.get(key):
            score += 2
    return score
