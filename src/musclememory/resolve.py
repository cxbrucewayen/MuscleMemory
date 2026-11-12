"""Resolution: pick the one card to use for an id in an environment (DESIGN 8),
and expand a recipe into its experience bundle (DESIGN 9 step 3, 12.1)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .cards import INHERITED_FROM_COMMON, KB, SIDE_RANK, STATE_RANK, Card, parse_id, swap_platform
from .grammar import GrammarError, parse_condition, parse_locator, parse_step
from .i18n import all_langs
from .versions import CLUE, MATCH, NO, Env, RangeError, match_applies, parse_applies, specificity

MAX_CALL_DEPTH = 3
FAIL_REF = re.compile(r"\bFAIL\.[A-Z0-9_]+(?:\.[A-Z0-9_]+){1,2}\b")


@dataclass
class Resolved:
    ref: str                      # what was asked for
    id: str | None = None         # the chosen card (may carry an @tag)
    data: dict = field(default_factory=dict)   # merged card
    match: str = "none"           # match | clue | none
    state: str | None = None
    chain: list[str] = field(default_factory=list)   # cards merged, lowest priority first
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.id is not None


def merge_variant(base: dict, variant: dict) -> dict:
    """An @ variant inherits everything and overrides whole fields."""
    out = dict(base)
    out.update(variant)
    return out


def merge_common(common: dict | None, platform: dict) -> dict:
    """A platform recipe inherits aliases/params/goal/output; side_effect only goes up."""
    if not common:
        return dict(platform)
    out = dict(platform)
    for k in INHERITED_FROM_COMMON:
        if k in common and k not in out:
            out[k] = common[k]
    sides = [s for s in (common.get("side_effect"), platform.get("side_effect")) if s in SIDE_RANK]
    if sides:
        out["side_effect"] = max(sides, key=SIDE_RANK.get)
    return out


def static_merge(kb: KB, card: Card) -> dict:
    """Merge a card with its base and common twin, ignoring the environment."""
    data = card.data
    if card.is_variant:
        base = kb.get(card.base_id)
        data = merge_variant(base.data if base else {}, card.data)
    if card.type == "RCP" and card.platform != "COMMON":
        twin = kb.common_twin(card.id)
        data = merge_common(twin.data if twin else None, data)
    return data


def _verified_last(card: Card) -> str:
    v = card.data.get("verified")
    return str(v.get("last", "")) if isinstance(v, dict) else ""


def resolve(kb: KB, ref: str, env: Env) -> Resolved:
    try:
        parts = parse_id(ref)
    except ValueError as e:
        return Resolved(ref, reason=str(e))
    if parts.tag:                       # explicit variant: only for inspection
        card = kb.get(ref)
        if not card:
            return Resolved(ref, reason="no such card")
        return Resolved(ref, card.id, {**static_merge(kb, card), "id": card.id}, MATCH,
                        card.data.get("state"), [card.base_id, card.id], "explicit variant")

    target = parts.base
    if parts.platform == "COMMON" and env.platform and env.platform != "COMMON":
        twin = swap_platform(target, env.platform)
        if kb.family(twin):
            target = twin
        elif parts.type == "RCP":
            return Resolved(ref, reason=f"no {env.platform} recipe for this goal yet (explore, then propose {twin})")
    family = kb.family(target)
    base = kb.get(target)
    if not family or not base:
        return Resolved(ref, reason="no such card" if not family else "variants exist but the base card is missing")

    scored = []
    for card in family:
        try:
            applies = parse_applies(card.data.get("applies") or {})
        except RangeError:
            continue
        verdict, dist = match_applies(applies, env)
        if verdict == NO:
            continue
        scored.append((card, verdict, dist, specificity(applies)))
    if not scored:
        return Resolved(ref, reason="no card for this platform/app")

    matches = [s for s in scored if s[1] == MATCH]
    if matches:
        matches.sort(key=lambda s: (-s[3], -STATE_RANK.get(s[0].data.get("state"), -1),
                                    _neg(_verified_last(s[0])), not s[0].is_variant))
        card, verdict, _, _ = matches[0]
        reason = "applies contains the environment"
    else:
        scored.sort(key=lambda s: (s[2], -s[3]))
        card, verdict, _, _ = scored[0]
        reason = "closest version; treat as a clue and verify on screen"

    data = merge_variant(base.data, card.data) if card.is_variant else dict(card.data)
    chain = [base.id] + ([card.id] if card.is_variant else [])
    if parts.type == "RCP" and card.platform != "COMMON":
        twin = kb.common_twin(card.id)
        if twin:
            data = merge_common(twin.data, data)
            chain.insert(0, twin.id)
    data["id"] = card.id
    return Resolved(ref, card.id, data, MATCH if verdict == MATCH else CLUE,
                    card.data.get("state"), chain, reason)


def _neg(s: str):
    # Sort helper: later dates first while keeping the tuple comparable.
    return tuple(-ord(c) for c in s)


# --------------------------------------------------------------------------- bundle

@dataclass
class Bundle:
    ref: str
    env: Env
    main: Resolved
    cards: dict[str, Resolved] = field(default_factory=dict)   # by reference id, in discovery order
    role: dict[str, str] = field(default_factory=dict)
    depth: dict[str, int] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    def bang_steps(self) -> list[tuple[str, int, str]]:
        """All `!` steps in the expanded recipe: (card id, step number, text)."""
        out = []
        for res in self.cards.values():
            if res.ok and res.id.startswith("RCP."):
                for i, raw in enumerate(res.data.get("steps") or [], 1):
                    try:
                        st = parse_step(raw)
                    except GrammarError:
                        continue
                    if st.leaf().bang:
                        out.append((res.id, i, raw))
        return out

    def side_effect(self) -> str:
        sides = [r.data.get("side_effect") for r in self.cards.values()
                 if r.ok and r.data.get("side_effect") in SIDE_RANK]
        return max(sides, key=SIDE_RANK.get) if sides else "none"


def recipe_refs(data: dict) -> tuple[list[str], list[str], list[str], list[str]]:
    """(called recipes, elements, apps, grammar problems) referenced by one recipe."""
    calls, elems, apps, problems = [], [], [], []
    for i, raw in enumerate(data.get("steps") or [], 1):
        try:
            st = parse_step(raw)
        except (GrammarError, ValueError) as e:
            problems.append(f"step {i}: {e}")
            continue
        leaf = st.leaf()
        if leaf.verb == "call":
            calls.append(leaf.target)
        if leaf.verb == "open":
            apps.append(leaf.target)
        elems.extend(st.elements())
    for key in ("requires", "check"):
        for i, raw in enumerate(data.get(key) or [], 1):
            try:
                elems.extend(parse_condition(raw).elements())
            except (GrammarError, ValueError) as e:
                problems.append(f"{key} {i}: {e}")
    if isinstance(data.get("ends_at"), str):
        elems.append(data["ends_at"])
    return calls, _uniq(elems), _uniq(apps), problems


def element_refs(data: dict) -> tuple[list[str], list[str]]:
    """(other elements an element depends on, grammar problems)."""
    refs, problems = [], []
    if isinstance(data.get("parent"), str):
        refs.append(data["parent"])
    for i, raw in enumerate(data.get("locators") or [], 1):
        try:
            loc = parse_locator(raw)
        except (GrammarError, ValueError) as e:
            problems.append(f"locator {i}: {e}")
            continue
        if loc.attrs.get("parent"):
            refs.append(loc.attrs["parent"])
        if loc.elem:
            refs.append(loc.elem)
    return _uniq(refs), problems


def _uniq(xs):
    seen, out = set(), []
    for x in xs:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def expand(kb: KB, ref: str, env: Env, env_for=None) -> Bundle:
    """Resolve a recipe and everything it calls or references."""
    def env_of(card_ref: str) -> Env:
        try:
            app = parse_id(card_ref).app
        except ValueError:
            return env
        if env_for and app:
            return env_for(app)
        if app and env.app and app != env.app:
            return env.with_app(app, None)
        return env

    main = resolve(kb, ref, env_of(ref))
    b = Bundle(ref, env, main)

    def add(r: str, role: str, depth: int) -> Resolved:
        if r in b.cards:
            return b.cards[r]
        res = resolve(kb, r, env_of(r))
        b.cards[r] = res
        b.role[r] = role
        b.depth[r] = depth
        if not res.ok:
            b.problems.append(f"{r}: {res.reason}")
        return res

    def add_element(r: str, depth: int):
        if r in b.cards:
            return
        res = add(r, "element", depth)
        if res.ok:
            refs, problems = element_refs(res.data)
            b.problems.extend(f"{res.id} {p}" for p in problems)
            for other in refs:
                add_element(other, depth + 1)

    def walk(r: str, role: str, depth: int, stack: tuple[str, ...]):
        if r in stack:
            b.problems.append(f"call cycle: {' -> '.join(stack + (r,))}")
            return
        if len(stack) > MAX_CALL_DEPTH:
            b.problems.append(f"call nesting deeper than {MAX_CALL_DEPTH}: {' -> '.join(stack + (r,))}")
            return
        known = r in b.cards
        res = b.cards[r] if known else add(r, role, depth)
        if not res.ok:
            return
        calls, elems, apps, problems = recipe_refs(res.data)
        if not known:
            b.problems.extend(f"{res.id} {p}" for p in problems)
        for c in calls:
            walk(c, "called", depth + 1, stack + (r,))
        if known:
            return
        for e in elems:
            add_element(e, depth + 1)
        for a in apps:
            add(a, "app", depth + 1)
        for text in all_langs(res.data.get("notes")):
            for f in FAIL_REF.findall(text):
                if kb.family(f) or kb.family(swap_platform(f, "COMMON")):
                    add(f, "notes", depth + 1)

    b.cards[ref] = main
    b.role[ref] = "main"
    b.depth[ref] = 0
    if main.ok:
        b.cards.pop(ref)          # walk() re-adds it first, keeping discovery order
        walk(ref, "main", 0, ())
    else:
        b.problems.append(f"{ref}: {main.reason}")
    return b


def runnable(bundle: Bundle) -> tuple[bool, list[str]]:
    """The gate for "directly runnable" (DESIGN 12.1, items 1-4)."""
    why = list(bundle.problems)
    if not bundle.main.ok:
        return False, why or ["no recipe"]
    if bundle.main.state != "stable":
        why.append(f"{bundle.main.id} is {bundle.main.state}, needs stable")
    for ref, res in bundle.cards.items():
        if not res.ok or bundle.role.get(ref) == "notes":
            continue
        if res.match != MATCH:
            why.append(f"{res.id} is only a clue for this environment")
        if res.id != bundle.main.id and STATE_RANK.get(res.state, 0) < STATE_RANK["reproduced"]:
            why.append(f"{res.id} is {res.state}, needs at least reproduced")
        if res.id.startswith("ELEM."):
            ok = False
            for raw in res.data.get("locators") or []:
                try:
                    ok = ok or parse_locator(raw).method != "vision"
                except (GrammarError, ValueError):
                    pass
            if not ok:
                why.append(f"{res.id} has no locator a program can use")
    return not why, why
