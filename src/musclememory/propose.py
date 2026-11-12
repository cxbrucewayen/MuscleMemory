"""`kb_propose`: the only way experience is written (SECURITY gate 1), and
`kb merge`, the maintainer-side step that turns a reviewed proposal into a card."""

from __future__ import annotations

import datetime
import re
from pathlib import Path

import yaml

from . import FORMAT
from .cards import (ALLOWED_FIELDS, DIR_OF_PLATFORM, KB, load_yaml, load_yaml_docs, parse_id)
from .check import check_card_dict, check_kb
from .fmt import CARD_ORDER, HEADER_ORDER, PROPOSAL_ORDER, dump_doc
from .grammar import ID_RE
from .i18n import canon_doc
from .scan import redact_doc, scan_doc
from .versions import APPLIES_KEYS

KINDS = ("update", "widen", "variant", "new")
MAX_PER_TASK = 3
_VERSION_ONLY = re.compile(r"^[A-Za-z][A-Za-z0-9_\-]*( (\d+(\.\d+)*|unknown))?$")


class ProposalError(Exception):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def normalize(text: str) -> dict:
    """Parse -> canonical form -> whitelist fields -> placeholders -> grammar -> scan.

    Raises ProposalError; nothing is written unless every stage passes."""
    try:
        doc = load_yaml(text)
    except yaml.YAMLError as e:
        raise ProposalError([f"not valid YAML: {str(e).splitlines()[0]}"])
    if not isinstance(doc, dict):
        raise ProposalError(["a proposal is one YAML mapping"])
    doc = canon_doc(doc)

    kinds = [k for k in KINDS if k in doc]
    if len(kinds) != 1:
        raise ProposalError(["a proposal needs exactly one of update / widen / variant / new"])
    kind = kinds[0]
    target = doc[kind]
    if not isinstance(target, str) or not ID_RE.match(target):
        raise ProposalError([f"{kind}: {target!r} is not a card id"])
    parts = parse_id(target)
    problems = []
    if kind == "variant" and not parts.tag:
        problems.append("variant: the id needs an @tag, e.g. ELEM.WIN.APP.NAME@4.2")
    if kind != "variant" and parts.tag and kind == "new":
        problems.append("new: use `variant:` for ids with an @tag")

    # Keep only what the schema allows; never try to strip "the sensitive bits".
    allowed = set(ALLOWED_FIELDS[parts.type]) - {"id", "state", "verified"}
    out = {kind: target}
    env = doc.get("env")
    if not isinstance(env, dict) or not env.get("os") or not env.get("lang"):
        problems.append("env is required and must include os and lang (the snapshot you ran in)")
        env = {}
    clean_env = {}
    for k in APPLIES_KEYS:
        v = env.get(k)
        if v is None:
            continue
        v = str(v).strip()
        if k in ("os", "app", "driver", "rom") and not _VERSION_ONLY.match(v):
            problems.append(f"env.{k} may only contain a name and a version")
            continue
        clean_env[k] = v
    out["env"] = clean_env
    dropped = []
    for k, v in doc.items():
        if k in KINDS or k == "env":
            continue
        if k in allowed:
            out[k] = v
        else:
            dropped.append(k)

    if kind in ("update",):
        extra = [k for k in out if k not in ("update", "env", "evidence")]
        if extra:
            problems.append(f"update only carries evidence; remove {extra}")
    if kind == "widen" and "applies" not in out:
        problems.append("widen needs the new applies range")
    if kind in ("variant", "new") and "applies" not in out:
        problems.append(f"{kind} needs applies (only the versions you verified, e.g. =4.2.0)")
    if "evidence" not in out:
        problems.append("evidence is required: what you observed, as structure (controls, error codes), not content")

    out = redact_doc(out)                       # known personal formats -> placeholders
    problems.extend(check_card_dict(out))
    if parts.type == "ELEM" and "locators" in out:
        from .grammar import GrammarError, parse_locator
        try:
            uses_text = any(parse_locator(x).uses_ui_text for x in out["locators"])
        except (GrammarError, ValueError):
            uses_text = False
        if uses_text and not (isinstance(out.get("applies"), dict) and out["applies"].get("lang")):
            problems.append("locators depend on UI text, so applies.lang is required")
    findings = scan_doc(out)                    # still flagged after replacement -> reject, never mask
    problems.extend(str(f) for f in findings)
    if problems:
        raise ProposalError(problems)
    if dropped:
        out["_dropped"] = dropped
    return out


def propose(kb: KB, text: str) -> tuple[Path, dict]:
    doc = normalize(text)
    dropped = doc.pop("_dropped", [])
    kind = next(k for k in KINDS if k in doc)
    d = kb.root / "proposals"
    d.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^A-Za-z0-9_.@-]", "_", doc[kind])
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path, n = d / f"{stamp}-{kind}-{slug}.yaml", 1
    while path.exists():
        n += 1
        path = d / f"{stamp}-{kind}-{slug}-{n}.yaml"
    path.write_text(dump_doc(doc, PROPOSAL_ORDER), encoding="utf-8", newline="\n")
    return path, {"kind": kind, "id": doc[kind], "dropped_fields": dropped}


# --------------------------------------------------------------------------- merge

def _card_file(kb: KB, card_id: str) -> Path:
    parts = parse_id(card_id)
    folder = kb.cards_dir / DIR_OF_PLATFORM[parts.platform]
    if parts.app:
        return folder / f"{parts.app.lower()}.yaml"
    return folder / ("_common.yaml" if parts.platform == "COMMON" else "_platform.yaml")


def _read(path: Path, card_id: str) -> list[dict]:
    if path.is_file():
        return [canon_doc(d) for d in load_yaml_docs(path.read_text(encoding="utf-8"))]
    parts = parse_id(card_id)
    return [{"format": FORMAT, "platform": parts.platform, "app": parts.app or "_platform"}]


def _write(path: Path, docs: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "---\n".join(dump_doc(d, HEADER_ORDER if i == 0 else CARD_ORDER) for i, d in enumerate(docs))
    path.write_text(text, encoding="utf-8", newline="\n")


def merge(kb: KB, proposal_path: Path, *, today: datetime.date | None = None) -> str:
    """Apply a reviewed proposal to cards/. The merge decides state and verified;
    a proposal can never set them. Refuses when `kb check` fails afterwards."""
    today = today or datetime.date.today()
    doc = normalize(Path(proposal_path).read_text(encoding="utf-8"))
    doc.pop("_dropped", None)
    kind = next(k for k in KINDS if k in doc)
    card_id = doc[kind]
    path = _card_file(kb, card_id)
    original = path.read_text(encoding="utf-8") if path.is_file() else None
    docs = _read(path, card_id)
    existing = next((d for d in docs[1:] if d.get("id") == card_id), None)
    fields = {k: v for k, v in doc.items() if k not in KINDS and k != "env"}

    if kind in ("new", "variant"):
        if existing is not None:
            raise ProposalError([f"{card_id} already exists; propose update, widen or a different variant tag"])
        card = {"id": card_id, **fields}
        if not (card_id.startswith("RCP.COMMON.")):
            card["state"] = "observed"
            card["verified"] = {"count": 1, "last": today}
        docs.append(card)
        msg = f"added {card_id} as observed"
    else:
        if existing is None:
            raise ProposalError([f"{card_id} does not exist"])
        if kind == "widen":
            existing["applies"] = fields["applies"]
        v = existing.get("verified") if isinstance(existing.get("verified"), dict) else {"count": 0}
        count = int(v.get("count", 0)) + 1
        existing["verified"] = {"count": count, "last": today}
        state = existing.get("state")
        if state in ("observed", "recheck") and count >= 2:
            state = "reproduced"
        if state == "reproduced" and count >= 3 and existing.get("counterexample"):
            state = "stable"
        existing["state"] = state
        msg = f"{card_id}: verified {count} time(s), state {state}"

    _write(path, docs)
    issues = [i for i in check_kb(KB.load(kb.root), flows=False)]
    if issues:
        if original is None:
            path.unlink()
        else:
            path.write_text(original, encoding="utf-8", newline="\n")
        raise ProposalError(["merge would break `kb check`:"] + [str(i) for i in issues[:8]])
    return msg
