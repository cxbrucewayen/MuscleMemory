"""`kb fmt`: the canonical on-disk form (DESIGN 4.1).

English key names, fixed key order, two-space indent, quotes only where YAML
needs them. Comments are not part of the data model and are dropped.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import yaml

from .cards import load_yaml_docs
from .i18n import canon_doc

HEADER_ORDER = ["format", "platform", "app"]
CARD_ORDER = ["id", "applies", "aliases", "capabilities", "limits", "version_probe", "app_id",
              "home", "preferred", "purpose", "parent", "locators", "params", "output", "goal",
              "side_effect", "symptom", "conclusion", "requires", "steps", "check", "ends_at",
              "notes", "evidence", "counterexample", "state", "verified"]
FLOW_ORDER = ["format", "id", "aliases", "trigger", "workdir", "inputs", "secrets", "when_busy",
              "steps", "check", "authorize", "lock", "state", "verified", "lessons"]
PROPOSAL_ORDER = ["update", "widen", "variant", "new", "env"] + CARD_ORDER[1:]
SUB_ORDER = {
    "applies": ["os", "app", "driver", "lang", "display", "rom"],
    "env": ["os", "app", "driver", "lang", "display", "rom"],
    "verified": ["count", "last"],
    "authorize": ["unattended", "files", "recipients"],
}
INLINE_LISTS = {"params", "output", "secrets", "trigger", "unattended", "files", "recipients"}
INLINE_MAPS = {"verified"}
LANG_ORDER = ["en", "zh"]


def _ordered(d: dict, order: list[str]) -> list:
    keys = [k for k in order if k in d]
    keys += [k for k in d if k not in order]
    return keys


def _scalar(v, flow=False) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    s = str(v)
    if s and "\n" not in s and s == s.strip():
        try:
            probe = f"[{s}]" if flow else f"k: {s}"
            back = yaml.safe_load(probe)
            back = back[0] if flow else back["k"]
            if isinstance(back, str) and back == s and (not flow or len(yaml.safe_load(probe)) == 1):
                return s
        except Exception:
            pass
    return json.dumps(s, ensure_ascii=False)


def _is_scalar(v) -> bool:
    return not isinstance(v, (dict, list))


def _emit(key, value, indent: int, out: list[str], parent: str | None = None):
    pad = "  " * indent
    if isinstance(value, dict):
        if key in INLINE_MAPS and all(_is_scalar(x) for x in value.values()):
            keys = _ordered(value, SUB_ORDER.get(key, []))
            body = ", ".join(f"{k}: {_scalar(value[k], flow=True)}" for k in keys)
            out.append(f"{pad}{key}: {{{body}}}")
            return
        if not value:
            out.append(f"{pad}{key}: {{}}")
            return
        out.append(f"{pad}{key}:")
        order = SUB_ORDER.get(key, LANG_ORDER)
        for k in _ordered(value, order):
            _emit(k, value[k], indent + 1, out, parent=key)
    elif isinstance(value, list):
        inline = (key in INLINE_LISTS or parent == "aliases") and all(_is_scalar(x) for x in value)
        if inline or not value:
            out.append(f"{pad}{key}: [{', '.join(_scalar(x, flow=True) for x in value)}]")
            return
        out.append(f"{pad}{key}:")
        for item in value:
            if _is_scalar(item):
                out.append(f"{pad}  - {_scalar(item)}")
            else:
                # Nested structures inside a list are not part of the schema; keep them valid.
                out.append(f"{pad}  - {json.dumps(item, ensure_ascii=False, default=str)}")
    else:
        out.append(f"{pad}{key}: {_scalar(value)}")


def dump_doc(doc: dict, order: list[str]) -> str:
    out: list[str] = []
    for k in _ordered(doc, order):
        _emit(k, doc[k], 0, out)
    return "\n".join(out) + "\n"


def dump_card(card: dict) -> str:
    return dump_doc(card, CARD_ORDER)


def order_for(doc: dict) -> list[str]:
    if any(k in doc for k in ("update", "widen", "variant", "new")):
        return PROPOSAL_ORDER
    if str(doc.get("id", "")).startswith("FLOW."):
        return FLOW_ORDER
    if "id" in doc:
        return CARD_ORDER
    return HEADER_ORDER


def format_text(text: str) -> str:
    """Canonicalise a card file, a flow file or a proposal."""
    docs = [canon_doc(d) if isinstance(d, dict) else d for d in load_yaml_docs(text)]
    parts = []
    for d in docs:
        if not isinstance(d, dict):
            raise ValueError("every YAML document must be a mapping")
        parts.append(dump_doc(d, order_for(d)))
    return "---\n".join(parts)


def format_file(path: Path, *, check_only=False) -> bool:
    """Format a file in place. Returns True when it was (or would be) changed."""
    old = path.read_text(encoding="utf-8")
    new = format_text(old)
    if new == old:
        return False
    if not check_only:
        path.write_text(new, encoding="utf-8", newline="\n")
    return True


def card_line_count(card: dict) -> int:
    return len(dump_card(card).splitlines())
