"""`kb check`: format, structure, grammar, side effects, inheritance, navigation,
secrets and the security scan (SECURITY section 5). Everything runs on the
canonical form, and recipes are re-checked after merging with their base and
common cards so that a harmless-looking fragment cannot hide in inheritance."""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from pathlib import Path

from . import FORMAT
from .cards import (
    ALLOWED_FIELDS,
    KB,
    REQUIRED_FIELDS,
    SIDE_RANK,
    STATE_RANK,
    Card,
    expected_location,
    parse_id,
    swap_platform,
)
from .fmt import card_line_count
from .grammar import (
    ID_RE,
    NAME_RE,
    POINTER_VERBS,
    GrammarError,
    Var,
    parse_condition,
    parse_locator,
    parse_step,
)
from .i18n import all_langs
from .resolve import MAX_CALL_DEPTH, static_merge
from .scan import HIDDEN, scan_doc
from .versions import PLATFORMS, RangeError, parse_applies

MAX_LINES, MAX_STEPS = 30, 12
APP_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]{0,120}$")

# Elements whose purpose mentions one of these must be clicked with `!` (SECURITY 3.2).
RISK_ZH = ("发送", "提交", "删除", "支付", "付款", "授权", "分享", "发布", "转账", "签到", "购买",
           "下单", "清空", "卸载", "格式化", "注销", "退款", "打赏", "订阅", "移除", "重置", "发帖")
RISK_EN = re.compile(
    r"\b(send|sends|submit|submits|delete|deletes|remove|removes|pay|pays|payment|purchase|buy|"
    r"order|authorize|authorise|grant|share|shares|publish|post|posts|transfer|check[- ]?in|"
    r"sign[- ]?in reward|uninstall|format|erase|wipe|reset|refund|subscribe|donate|tip)\b", re.I)


@dataclass(frozen=True)
class Issue:
    path: str
    card: str
    rule: str
    msg: str

    def __str__(self):
        loc = f"{self.path}: " if self.path else ""
        who = f"{self.card}: " if self.card else ""
        return f"{loc}{who}[{self.rule}] {self.msg}"


def is_risky_purpose(purpose) -> str | None:
    for text in all_langs(purpose):
        for kw in RISK_ZH:
            if kw in text:
                return kw
        m = RISK_EN.search(text)
        if m:
            return m.group(0)
    return None


def _text_ok(v) -> bool:
    if isinstance(v, str):
        return True
    return isinstance(v, dict) and bool(v) and all(isinstance(k, str) and isinstance(x, str) for k, x in v.items())


def _aliases_ok(v) -> bool:
    if isinstance(v, list):
        return bool(v) and all(isinstance(x, str) and x.strip() for x in v)
    return (isinstance(v, dict) and bool(v)
            and all(isinstance(x, list) and x and all(isinstance(s, str) and s.strip() for s in x)
                    for x in v.values()))


class Checker:
    def __init__(self, kb: KB):
        self.kb = kb
        self.issues: list[Issue] = []
        self._path = ""
        self._card = ""

    def err(self, rule: str, msg: str):
        self.issues.append(Issue(self._path, self._card, rule, msg))

    def rel(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.kb.root))
        except ValueError:
            return str(path)

    # ------------------------------------------------------------------ driver
    def run(self) -> list[Issue]:
        kb = self.kb
        self._repo_checks()
        for cf in kb.files:
            self._path, self._card = self.rel(cf.path), ""
            if cf.error:
                self.err("format", cf.error)
                continue
            self._header(cf)
            for doc in cf.docs:
                self._card = doc.get("id", "?") if isinstance(doc, dict) else "?"
                self._card_doc(cf, doc)
        for card_id, path in kb.duplicates:
            self._path, self._card = self.rel(path), card_id
            self.err("structure", "duplicate id")
        for card in kb.cards.values():
            self._path, self._card = self.rel(card.path), card.id
            self._semantic(card)
        return self.issues

    def _repo_checks(self):
        root = self.kb.root
        skip = {".git", "runs", "node_modules", ".venv", "venv", "__pycache__"}
        self._card = ""
        for p in root.iterdir() if root.is_dir() else []:
            if p.name in skip:
                continue
            for f in ([p] if p.is_file() else p.rglob("*")):
                if f.is_file() and (f.name == ".env" or f.name.startswith(".env.")):
                    self._path = self.rel(f)
                    self.err("secret", ".env files must live outside the repository")
        for sub in ("cards", "proposals"):
            d = root / sub
            for f in d.rglob("*.yaml") if d.is_dir() else []:
                self._path = self.rel(f)
                try:
                    raw = f.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    self.err("format", "not UTF-8")
                    continue
                if "KB_SECRET_" in raw:
                    self.err("secret", "KB_SECRET_ must never appear in the repository")
                for rx, label in HIDDEN[:3] + HIDDEN[4:]:
                    if rx.search(raw):
                        self.err("hidden", f"{label} in raw file")

    def _header(self, cf):
        h = cf.header
        for k in h:
            if k not in ("format", "platform", "app"):
                self.err("structure", f"unknown header field {k!r}")
        if h.get("platform") not in PLATFORMS:
            self.err("structure", f"header platform must be one of {', '.join(PLATFORMS)}")
        plat, app = expected_location(cf.path, self.kb.cards_dir)
        if plat is None:
            self.err("structure", "card files must be cards/<platform dir>/<app>.yaml")
        elif (plat, app) != (h.get("platform"), str(h.get("app", ""))):
            self.err("structure", f"header says {h.get('platform')}/{h.get('app')} but the file location means {plat}/{app}")

    # ------------------------------------------------------- per-document shape
    def _card_doc(self, cf, doc):
        if not isinstance(doc, dict):
            self.err("format", "card must be a mapping")
            return
        cid = doc.get("id")
        if not isinstance(cid, str) or not ID_RE.match(cid):
            self.err("structure", "id must be TYPE.PLATFORM[.APP].NAME[@tag] in ASCII upper case, digits and _")
            return
        try:
            parts = parse_id(cid)
        except ValueError as e:
            self.err("structure", str(e))
            return
        h = cf.header
        if parts.platform != h.get("platform"):
            self.err("structure", f"id platform {parts.platform} does not match file platform {h.get('platform')}")
        happ = str(h.get("app", ""))
        want_app = None if happ == "_platform" else happ
        if parts.app != want_app:
            self.err("structure", f"id app segment {parts.app or '(none)'} does not match file app {happ}")
        for k in doc:
            if k not in ALLOWED_FIELDS[parts.type]:
                self.err("structure", f"field {k!r} is not allowed on {parts.type} cards")
        n = card_line_count(doc)
        if n > MAX_LINES:
            self.err("format", f"card is {n} lines in canonical form (max {MAX_LINES}); split it")
        steps = doc.get("steps")
        if isinstance(steps, list) and len(steps) > MAX_STEPS:
            self.err("format", f"{len(steps)} steps (max {MAX_STEPS}); split into smaller recipes and call them")
        for f in scan_doc(doc):
            self.err(f.rule, f"{f.detail} in {f.where}")

    # ------------------------------------------------------------ merged checks
    def _semantic(self, card: Card):
        kb, d = self.kb, card.data
        merged = static_merge(kb, card)

        # applies
        applies = None
        if "applies" not in d:
            self.err("structure", "applies is required" + (" (a variant must write its own)" if card.is_variant else ""))
        else:
            try:
                applies = parse_applies(d["applies"])
            except RangeError as e:
                self.err("structure", f"applies: {e}")
        if applies:
            os_name = applies["os"].name
            if card.platform == "COMMON":
                if os_name is not None:
                    self.err("structure", "COMMON cards must use `os: any`")
            elif os_name != card.platform:
                self.err("structure", f"applies.os must be {card.platform} ...")
            if card.app:
                spec = applies.get("app")
                if spec is None or spec.name != card.app:
                    self.err("structure", f"applies.app must be `{card.app} <range>`")
            elif "app" in applies:
                self.err("structure", "platform-level cards cannot restrict applies.app")

        if card.is_variant and not kb.get(card.base_id):
            self.err("inherit", f"variant has no base card {card.base_id}")
            return

        # required fields
        key = card.type
        if card.type == "RCP":
            key = "RCP_COMMON" if card.platform == "COMMON" else "RCP_PLATFORM"
        for f in REQUIRED_FIELDS[key]:
            if f == "ends_at" and not card.app:
                continue        # platform-level recipes (e.g. INPUT_TEXT) are not tied to a screen
            if f not in merged:
                self.err("structure", f"missing field {f!r}")

        if card.type == "RCP" and card.platform == "COMMON":
            for f in ("steps", "requires", "check", "ends_at", "state", "verified", "evidence"):
                if f in d:
                    self.err("structure", f"COMMON recipes describe the goal only; {f!r} belongs on platform cards")
        else:
            self._trust(d, merged)

        for f in ("purpose", "goal", "notes", "symptom", "conclusion", "capabilities", "limits",
                  "version_probe", "preferred", "evidence", "counterexample"):
            if f in d and not _text_ok(d[f]) and not (isinstance(d[f], list) and all(isinstance(x, str) for x in d[f])):
                self.err("structure", f"{f} must be text or {{lang: text}}")
        if "aliases" in d and not _aliases_ok(d["aliases"]):
            self.err("structure", "aliases must be {lang: [text, ...]}")
        for f in ("params", "output"):
            if f in d and not (isinstance(d[f], list) and all(isinstance(x, str) and NAME_RE.match(x) for x in d[f])
                               and len(set(d[f])) == len(d[f])):
                self.err("structure", f"{f} must be a list of distinct names")
        if "side_effect" in merged and merged["side_effect"] not in SIDE_RANK:
            self.err("structure", "side_effect must be none, destructive or external")

        if card.type == "APP":
            self._app(card, merged)
        elif card.type == "ELEM":
            self._elem(card, merged, applies)
        elif card.type == "RCP":
            self._recipe_inheritance(card)
            if card.platform != "COMMON":
                self._recipe(card, merged)

    def _trust(self, d, merged):
        state = merged.get("state")
        if state is not None and state not in STATE_RANK:
            self.err("structure", "state must be observed, reproduced, stable or recheck")
        v = merged.get("verified")
        count = None
        if v is not None:
            if (not isinstance(v, dict) or not isinstance(v.get("count"), int) or v["count"] < 0
                    or not isinstance(v.get("last"), (datetime.date, str))):
                self.err("structure", "verified must be {count: N, last: YYYY-MM-DD}")
            else:
                count = v["count"]
                if isinstance(v["last"], str) and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v["last"]):
                    self.err("structure", "verified.last must be a date")
        if state == "stable":
            if not merged.get("counterexample"):
                self.err("structure", "stable needs a counterexample (when does this NOT hold?)")
            if count is not None and count < 3:
                self.err("structure", "stable needs at least 3 verifications")
        if state == "reproduced" and count is not None and count < 2:
            self.err("structure", "reproduced needs at least 2 verifications")

    def _exists(self, ref: str, card: Card, kind: str) -> Card | None:
        """A referenced card must exist on the same platform (or be a COMMON goal)."""
        try:
            parts = parse_id(ref)
        except ValueError:
            self.err("structure", f"bad reference {ref!r}")
            return None
        if parts.type != kind:
            self.err("structure", f"{ref} is not a {kind} card")
            return None
        if parts.platform == "COMMON" and kind in ("RCP", "FAIL"):
            target = self.kb.get(ref)
            if not target:
                self.err("structure", f"referenced card {ref} does not exist")
            return target
        if parts.platform != card.platform:
            self.err("structure", f"{ref} belongs to another platform")
            return None
        target = self.kb.get(ref)
        if not target:
            self.err("structure", f"referenced card {ref} does not exist")
        return target

    def _app(self, card, merged):
        app_id = merged.get("app_id")
        if app_id is not None and not (isinstance(app_id, str) and APP_ID_RE.match(app_id)):
            self.err("structure", "app_id must be a package / bundle / executable name")
        home = merged.get("home")
        if isinstance(home, str):
            target = self._exists(home, card, "ELEM")
            if target and not target.is_screen:
                self.err("nav", "home must be a screen (an ELEM without parent)")

    def _elem(self, card, merged, applies):
        locs = merged.get("locators")
        if not isinstance(locs, list) or not locs:
            self.err("structure", "locators must be a non-empty list")
            return
        needs_lang = False
        for i, raw in enumerate(locs, 1):
            try:
                loc = parse_locator(raw)
            except (GrammarError, ValueError) as e:
                self.err("grammar", f"locator {i}: {e}")
                continue
            needs_lang = needs_lang or loc.uses_ui_text
            for ref in (loc.attrs.get("parent"), loc.elem):
                if ref:
                    if ref == card.base_id:
                        self.err("structure", f"locator {i} refers to the element itself")
                    else:
                        self._exists(ref, card, "ELEM")
        own_lang = applies.get("lang") if applies else None
        if needs_lang and "locators" in card.data and not own_lang:
            self.err("lang", "locators depend on UI text (text / name= / value=) but applies.lang is missing")
        parent = merged.get("parent")
        if parent is not None:
            if not isinstance(parent, str):
                self.err("structure", "parent must be an element id")
            elif parent == card.base_id:
                self.err("structure", "an element cannot be its own parent")
            else:
                self._exists(parent, card, "ELEM")
                seen, cur = {card.base_id}, parent
                while cur:
                    if cur in seen:
                        self.err("structure", "parent chain forms a cycle")
                        break
                    seen.add(cur)
                    nxt = self.kb.get(cur)
                    cur = nxt.data.get("parent") if nxt else None

    def _recipe_inheritance(self, card):
        kb, d = self.kb, card.data
        if card.platform != "COMMON" and not card.is_variant:
            twin = kb.common_twin(card.id)
            if twin:
                for f in ("params", "goal"):
                    if f in d and d[f] != twin.data.get(f):
                        self.err("inherit", f"platform cards cannot change {f!r} of {twin.id}")
                if d.get("side_effect") in SIDE_RANK and twin.data.get("side_effect") in SIDE_RANK \
                        and SIDE_RANK[d["side_effect"]] < SIDE_RANK[twin.data["side_effect"]]:
                    self.err("side_effect", f"side_effect is lower than {twin.id}")
        if card.is_variant:
            base = kb.get(card.base_id)
            for f in ("params", "goal"):
                if f in d and base and d[f] != static_merge(kb, base).get(f):
                    self.err("inherit", f"variants cannot change {f!r}")
            if base and d.get("side_effect") in SIDE_RANK:
                base_side = static_merge(kb, base).get("side_effect")
                if base_side in SIDE_RANK and SIDE_RANK[d["side_effect"]] < SIDE_RANK[base_side]:
                    self.err("side_effect", "side_effect is lower than the base card")

    def _callee(self, ref: str, platform: str) -> tuple[dict | None, Card | None]:
        """Statically resolve a call target to the merged recipe on this platform."""
        kb = self.kb
        parts = parse_id(ref)
        if parts.platform == "COMMON":
            twin = kb.get(swap_platform(ref, platform))
            if twin:
                return static_merge(kb, twin), twin
            common = kb.get(ref)
            return (dict(common.data), None) if common else (None, None)
        target = kb.get(ref)
        return (static_merge(kb, target), target) if target else (None, None)

    def _recipe(self, card, merged):
        kb = self.kb
        params = list(merged.get("params") or [])
        known = set(params)
        side = merged.get("side_effect")
        has_bang = False
        steps = merged.get("steps")
        if not isinstance(steps, list) or not steps:
            self.err("structure", "steps must be a non-empty list")
            steps = []

        def use(var, where):
            if isinstance(var, Var) and var.name not in known:
                self.err("grammar", f"{where}: {{{var.name}}} is neither a parameter nor assigned earlier")

        def cond_refs(cond, where):
            for a in cond.atoms:
                if a.kind in ("elem_state", "elem_cmp"):
                    self._exists(a.subject, card, "ELEM")
                use(a.subject, where)
                use(a.value, where)

        for i, raw in enumerate(steps, 1):
            where = f"step {i}"
            try:
                st = parse_step(raw)
            except (GrammarError, ValueError) as e:
                self.err("grammar", f"{where}: {e}")
                continue
            if st.cond:
                cond_refs(st.cond, where)
            leaf = st.leaf()
            has_bang = has_bang or leaf.bang
            for ref in (leaf.target, leaf.target2):
                if ref and ref.startswith("ELEM."):
                    target = self._exists(ref, card, "ELEM")
                    if target and leaf.verb == "goto" and not target.is_screen:
                        self.err("nav", f"{where}: goto needs a screen (an ELEM without parent)")
                    if target and leaf.verb in POINTER_VERBS and not leaf.bang:
                        for member in kb.family(target.base_id):
                            kw = is_risky_purpose(member.data.get("purpose"))
                            if kw:
                                self.err("side_effect", f"{where}: {ref} looks high-risk ({kw!r}); the step must be marked with !")
                                break
            if leaf.verb == "open":
                self._exists(leaf.target, card, "APP")
            if leaf.verb in ("type", "clipboard"):
                use(leaf.arg, where)
            if leaf.verb == "call":
                self._call(card, leaf, where, use, side)
            if leaf.out is not None:
                if st.verb == "if":
                    self.err("grammar", f"{where}: a conditional step cannot assign a variable")
                known.add(leaf.out.name)

        for key in ("requires", "check"):
            conds = merged.get(key)
            if conds is None and key == "requires":
                continue
            if not isinstance(conds, list) or (key == "check" and not conds):
                self.err("structure", f"{key} must be a list of conditions")
                continue
            for i, raw in enumerate(conds, 1):
                try:
                    cond = parse_condition(raw)
                except (GrammarError, ValueError) as e:
                    self.err("grammar", f"{key} {i}: {e}")
                    continue
                if key == "requires":
                    saved, known_now = known, set(params)
                    known = known_now
                    cond_refs(cond, f"{key} {i}")
                    known = saved
                else:
                    cond_refs(cond, f"{key} {i}")
        ends = merged.get("ends_at")
        if isinstance(ends, str):
            self._exists(ends, card, "ELEM")
        elif ends is not None:
            self.err("structure", "ends_at must be an element id")

        for out in merged.get("output") or []:
            if out not in known:
                self.err("structure", f"output {{{out}}} never gets a value (assign it with read/call ->, or name it after a parameter)")
        if has_bang and side == "none":
            self.err("side_effect", "a recipe with ! steps cannot be side_effect: none")
        self._call_depth(card)

    def _call(self, card, leaf, where, use, side):
        target = self._exists(leaf.target, card, "RCP")
        if not target:
            return
        callee, _ = self._callee(leaf.target, card.platform)
        if callee is None:
            return
        want = list(callee.get("params") or [])
        got = list(leaf.args)
        if sorted(want) != sorted(got):
            self.err("grammar", f"{where}: {leaf.target} takes parameters {want}, got {got}")
        for v in leaf.args.values():
            use(v, where)
        if leaf.out is not None and not callee.get("output"):
            self.err("grammar", f"{where}: {leaf.target} declares no output to receive with ->")
        cs = callee.get("side_effect")
        if cs in SIDE_RANK and side in SIDE_RANK and SIDE_RANK[side] < SIDE_RANK[cs]:
            self.err("side_effect", f"{where}: side_effect {side} is lower than called recipe {leaf.target} ({cs})")

    def _call_depth(self, card):
        kb = self.kb

        def calls_of(data):
            out = []
            for raw in data.get("steps") or []:
                try:
                    st = parse_step(raw).leaf()
                except (GrammarError, ValueError):
                    continue
                if st.verb == "call":
                    out.append(st.target)
            return out

        def walk(data, cid, stack):
            if cid in stack:
                self.err("inherit", f"call cycle: {' -> '.join(stack + (cid,))}")
                return
            if len(stack) > MAX_CALL_DEPTH:
                self.err("inherit", f"call nesting deeper than {MAX_CALL_DEPTH}: {' -> '.join(stack + (cid,))}")
                return
            for ref in calls_of(data):
                callee, target = self._callee(ref, card.platform)
                if callee is not None and target is not None:
                    walk(callee, target.base_id, stack + (cid,))

        walk(static_merge(kb, card), card.base_id, ())


def check_kb(kb: KB, *, flows: bool = True) -> list[Issue]:
    issues = Checker(kb).run()
    if flows:
        from .flows import check_flow_file
        for path in kb.flow_files():
            for msg in check_flow_file(kb, path):
                issues.append(Issue(str(path.relative_to(kb.root)), "", "flow", msg))
    return issues


def check_card_dict(doc: dict) -> list[str]:
    """Stand-alone grammar check of one card-shaped mapping (used by kb_propose)."""
    out = []
    for i, raw in enumerate(doc.get("steps") or [], 1):
        try:
            parse_step(raw)
        except (GrammarError, ValueError) as e:
            out.append(f"step {i}: {e}")
    for key in ("requires", "check"):
        for i, raw in enumerate(doc.get(key) or [], 1):
            try:
                parse_condition(raw)
            except (GrammarError, ValueError) as e:
                out.append(f"{key} {i}: {e}")
    for i, raw in enumerate(doc.get("locators") or [], 1):
        try:
            parse_locator(raw)
        except (GrammarError, ValueError) as e:
            out.append(f"locator {i}: {e}")
    if "applies" in doc:
        try:
            parse_applies(doc["applies"])
        except RangeError as e:
            out.append(f"applies: {e}")
    if isinstance(doc.get("steps"), list) and len(doc["steps"]) > MAX_STEPS:
        out.append(f"more than {MAX_STEPS} steps")
    return out


__all__ = ["Issue", "check_kb", "check_card_dict", "is_risky_purpose", "FORMAT"]
