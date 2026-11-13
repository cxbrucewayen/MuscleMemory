"""Loading the card library: files, headers, ids (DESIGN section 3 and 4)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import FORMAT
from .i18n import canon_doc

PLATFORM_DIRS = {"common": "COMMON", "windows": "WIN", "macos": "MAC", "linux": "LINUX",
                 "android": "ANDROID", "ios": "IOS", "harmony": "HARMONY"}
DIR_OF_PLATFORM = {v: k for k, v in PLATFORM_DIRS.items()}
TYPES = ("ENV", "APP", "ELEM", "RCP", "FAIL")
STATE_RANK = {"recheck": 0, "observed": 1, "reproduced": 2, "stable": 3}
SIDE_RANK = {"none": 0, "destructive": 1, "external": 2}

_COMMON = ("id", "applies", "notes")
_TRUST = ("evidence", "counterexample", "state", "verified")
ALLOWED_FIELDS = {
    "ENV": _COMMON + ("capabilities", "limits", "version_probe") + _TRUST,
    "APP": _COMMON + ("aliases", "app_id", "home", "preferred") + _TRUST,
    "ELEM": _COMMON + ("purpose", "parent", "locators") + _TRUST,
    "RCP": _COMMON + ("aliases", "params", "goal", "side_effect", "output", "requires",
                      "steps", "check", "ends_at") + _TRUST,
    "FAIL": _COMMON + ("symptom", "conclusion") + _TRUST,
}
REQUIRED_FIELDS = {
    "ENV": ("capabilities", "limits", "version_probe", "evidence", "state", "verified"),
    "APP": ("aliases", "app_id", "home", "evidence", "state", "verified"),
    "ELEM": ("purpose", "locators", "evidence", "state", "verified"),
    "FAIL": ("symptom", "conclusion", "evidence", "state", "verified"),
    "RCP_COMMON": ("aliases", "goal", "side_effect"),
    "RCP_PLATFORM": ("aliases", "goal", "side_effect", "steps", "check", "ends_at",
                     "evidence", "state", "verified"),
}
INHERITED_FROM_COMMON = ("aliases", "params", "goal", "output")


class LoadError(Exception):
    pass


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that refuses duplicate keys (a duplicate could hide a field)."""


def _construct_mapping(loader, node, deep=False):
    seen = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=True)
        try:
            dup = key in seen
        except TypeError:
            raise yaml.constructor.ConstructorError(None, None, "unhashable mapping key", key_node.start_mark)
        if dup:
            raise yaml.constructor.ConstructorError(None, None, f"duplicate key {key!r}", key_node.start_mark)
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def load_yaml_docs(text: str) -> list:
    return [d for d in yaml.load_all(text, Loader=_StrictLoader) if d is not None]


def load_yaml(text: str):
    return yaml.load(text, Loader=_StrictLoader)


@dataclass(frozen=True)
class IdParts:
    type: str
    platform: str
    app: str | None
    name: str | None
    tag: str | None

    @property
    def base(self) -> str:
        return ".".join(p for p in (self.type, self.platform, self.app, self.name) if p)


def parse_id(card_id: str) -> IdParts:
    base, _, tag = str(card_id).partition("@")
    segs = base.split(".")
    if len(segs) < 2 or segs[0] not in TYPES:
        raise ValueError(f"bad id {card_id!r}")
    typ, plat = segs[0], segs[1]
    if typ == "ENV":
        if len(segs) != 2:
            raise ValueError(f"ENV id must be ENV.<PLATFORM>: {card_id!r}")
        return IdParts(typ, plat, None, None, tag or None)
    if typ == "APP":
        if len(segs) != 3:
            raise ValueError(f"APP id must be APP.<PLATFORM>.<APP>: {card_id!r}")
        return IdParts(typ, plat, segs[2], None, tag or None)
    if len(segs) == 3:
        return IdParts(typ, plat, None, segs[2], tag or None)
    if len(segs) == 4:
        return IdParts(typ, plat, segs[2], segs[3], tag or None)
    raise ValueError(f"bad id {card_id!r}")


def swap_platform(card_id: str, platform: str) -> str:
    base, at, tag = card_id.partition("@")
    segs = base.split(".")
    segs[1] = platform
    return ".".join(segs) + (at + tag if at else "")


@dataclass
class Card:
    id: str
    data: dict
    path: Path | None = None
    parts: IdParts = field(init=False)

    def __post_init__(self):
        self.parts = parse_id(self.id)

    @property
    def type(self):
        return self.parts.type

    @property
    def platform(self):
        return self.parts.platform

    @property
    def app(self):
        return self.parts.app

    @property
    def base_id(self):
        return self.parts.base

    @property
    def is_variant(self):
        return self.parts.tag is not None

    @property
    def is_screen(self):
        return self.type == "ELEM" and not self.data.get("parent")


@dataclass
class CardFile:
    path: Path
    header: dict
    docs: list           # canonicalised card dicts (may include malformed ones)
    error: str | None = None


def expected_location(path: Path, cards_dir: Path) -> tuple[str | None, str | None]:
    """(platform, app) implied by a file's position under cards/."""
    try:
        rel = path.relative_to(cards_dir)
    except ValueError:
        return None, None
    if len(rel.parts) != 2:
        return None, None
    plat = PLATFORM_DIRS.get(rel.parts[0])
    stem = rel.name[:-len(".yaml")] if rel.name.endswith(".yaml") else rel.name
    if stem in ("_common", "_platform"):
        return plat, "_platform"
    return plat, stem.split(".")[0].upper()


class KB:
    """An in-memory view of one library root (cards/, flows/, proposals/, runs/)."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.cards: dict[str, Card] = {}
        self.files: list[CardFile] = []
        self.duplicates: list[tuple[str, Path]] = []
        self._by_base: dict[str, list[Card]] = {}

    @property
    def cards_dir(self) -> Path:
        return self.root / "cards"

    @classmethod
    def load(cls, root: Path | str) -> KB:
        kb = cls(Path(root))
        if kb.cards_dir.is_dir():
            for path in sorted(kb.cards_dir.rglob("*.yaml")):
                kb._load_file(path)
        return kb

    def _load_file(self, path: Path):
        try:
            docs = load_yaml_docs(path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, UnicodeDecodeError) as e:
            self.files.append(CardFile(path, {}, [], f"not valid YAML: {str(e).splitlines()[0]}"))
            return
        if not docs or not isinstance(docs[0], dict):
            self.files.append(CardFile(path, {}, [], "missing file header"))
            return
        header = canon_doc(docs[0])
        cf = CardFile(path, header, [])
        self.files.append(cf)
        if "id" in header:
            cf.error = "first document must be the file header (format/platform/app), not a card"
            return
        if header.get("format") != FORMAT:
            cf.error = f"unsupported format {header.get('format')!r} (this parser reads format {FORMAT}; try `kb migrate`)"
            return
        for raw in docs[1:]:
            doc = canon_doc(raw) if isinstance(raw, dict) else raw
            cf.docs.append(doc)
            if not isinstance(doc, dict) or not isinstance(doc.get("id"), str):
                continue
            try:
                card = Card(doc["id"], doc, path)
            except ValueError:
                continue
            if card.id in self.cards:
                self.duplicates.append((card.id, path))
                continue
            self.cards[card.id] = card
            self._by_base.setdefault(card.base_id, []).append(card)

    # ------------------------------------------------------------------ lookups
    def get(self, card_id: str) -> Card | None:
        return self.cards.get(card_id)

    def family(self, base_id: str) -> list[Card]:
        """The base card plus all of its @ variants."""
        return list(self._by_base.get(base_id, []))

    def common_twin(self, card_id: str) -> Card | None:
        parts = parse_id(card_id)
        if parts.platform == "COMMON":
            return None
        return self.cards.get(swap_platform(parts.base, "COMMON"))

    def by_type(self, typ: str, platform: str | None = None, app: str | None = "*") -> list[Card]:
        out = []
        for c in self.cards.values():
            if c.type != typ:
                continue
            if platform is not None and c.platform != platform:
                continue
            if app != "*" and c.app != app:
                continue
            out.append(c)
        return out

    def screens(self, platform: str, app: str | None) -> list[str]:
        """Base ids of the screen elements (ELEM without parent) of one app."""
        seen = []
        for c in self.by_type("ELEM", platform, app):
            if not c.is_variant and c.is_screen and c.base_id not in seen:
                seen.append(c.base_id)
        return seen

    # ------------------------------------------------------------------- flows
    @property
    def flows_dir(self) -> Path:
        return self.root / "flows"

    def flow_files(self) -> list[Path]:
        return sorted(self.flows_dir.glob("*.flow.yaml")) if self.flows_dir.is_dir() else []


def find_root(start: Path | str | None = None) -> Path:
    """Locate the library root: $KB_ROOT, the nearest parent containing cards/,
    the `root` recorded by `kb setup`, or ~/.cua-experience/library."""
    env = os.environ.get("KB_ROOT")
    if env:
        return Path(env)
    p = Path(start or Path.cwd()).resolve()
    for cand in (p, *p.parents):
        if (cand / "cards").is_dir():
            return cand
    configured = load_config().get("root")
    for cand in (configured, user_home() / "library"):
        if cand and (Path(cand) / "cards").is_dir():
            return Path(cand)
    return p


def user_home() -> Path:
    """The per-user directory that holds config.yaml and .env (outside the repo)."""
    override = os.environ.get("CUA_EXPERIENCE_HOME")
    return Path(override) if override else Path.home() / ".cua-experience"


def load_config() -> dict:
    path = user_home() / "config.yaml"
    if not path.is_file():
        return {}
    try:
        data = load_yaml(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}
