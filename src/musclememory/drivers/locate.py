"""Turning locators into nodes of the current snapshot (DESIGN 10).

Nothing here is cached between snapshots: handles are re-acquired every time.
"""

from __future__ import annotations

from collections.abc import Callable

from ..grammar import GrammarError, Locator, parse_locator
from .base import Node, point

MAX_DEPTH = 6


def _descendants(tree: list[Node], root: Node) -> set[int]:
    by_idx = {n.idx: n for n in tree}
    out = {root.idx}
    for n in tree:
        cur, hops = n, 0
        while cur.parent is not None and hops < 200:
            if cur.parent == root.idx or cur.parent in out:
                out.add(n.idx)
                break
            cur = by_idx.get(cur.parent)
            hops += 1
            if cur is None:
                break
    return out


def _eq(a: str, b: str) -> bool:
    return (a or "").strip().lower() == (b or "").strip().lower()


def _role_match(node_role: str, want: str) -> bool:
    return _eq(node_role, want) or (node_role or "").lower().endswith("." + want.lower())


def _id_match(node_id: str, want: str) -> bool:
    return bool(node_id) and (node_id == want or node_id.endswith("/" + want))


def _match_ax(loc: Locator, node: Node) -> bool:
    a = loc.attrs
    if "role" in a and not _role_match(node.role, a["role"]):
        return False
    if "name" in a and node.name != a["name"]:
        return False
    if "id" in a and not _id_match(node.id, a["id"]):
        return False
    if "value" in a and node.value != a["value"]:
        return False
    return True


def _relative(tree: list[Node], anchor: Node, position: str, scope: set[int] | None) -> Node | None:
    if not anchor.bounds:
        return None
    ax, ay, aw, ah = anchor.bounds
    ancestors, by_idx, cur = set(), {n.idx: n for n in tree}, anchor
    while cur is not None and cur.parent is not None:
        ancestors.add(cur.parent)
        cur = by_idx.get(cur.parent)
    best, best_key = None, None
    for n in tree:
        if n.idx == anchor.idx or n.idx in ancestors or not n.bounds:
            continue
        if scope is not None and n.idx not in scope:
            continue
        x, y, w, h = n.bounds
        v_overlap = min(ay + ah, y + h) - max(ay, y)
        h_overlap = min(ax + aw, x + w) - max(ax, x)
        if position == "right_of":
            ok, dist = v_overlap > 0 and x >= ax + aw - 1, x - (ax + aw)
        elif position == "left_of":
            ok, dist = v_overlap > 0 and x + w <= ax + 1, ax - (x + w)
        elif position == "below":
            ok, dist = h_overlap > 0 and y >= ay + ah - 1, y - (ay + ah)
        else:  # above
            ok, dist = h_overlap > 0 and y + h <= ay + 1, ay - (y + h)
        if not ok:
            continue
        key = (dist, w * h)
        if best_key is None or key < best_key:
            best, best_key = n, key
    return best


def locate(tree: list[Node], ref: str, get_elem: Callable[[str], dict | None],
           tried: list | None = None, _depth: int = 0) -> tuple[Node | None, int]:
    """Find an element card in a snapshot.

    Returns (node, n) where n is the 1-based index of the locator that worked.
    `tried` collects what was attempted, for the hand-off package.
    """
    if _depth > MAX_DEPTH:
        return None, 0
    data = get_elem(ref)
    if not data:
        if tried is not None:
            tried.append({"element": ref, "result": "no usable card"})
        return None, 0
    scope = None
    parent = data.get("parent")
    if parent:
        pnode, _ = locate(tree, parent, get_elem, None, _depth + 1)
        if pnode is None:
            if tried is not None:
                tried.append({"element": ref, "result": f"parent screen {parent} is not present"})
            return None, 0
        scope = _descendants(tree, pnode)
    for i, raw in enumerate(data.get("locators") or [], 1):
        try:
            loc = parse_locator(raw)
        except (GrammarError, ValueError):
            continue
        node = None if loc.method == "vision" else _apply(loc, tree, scope, get_elem, _depth)
        if tried is not None:
            tried.append({"element": ref, "locator": i, "text": raw,
                          "result": "skipped (vision needs an AI)" if loc.method == "vision"
                          else ("found" if node else "not found")})
        if node is not None:
            return node, i
    return None, 0


def _apply(loc: Locator, tree, scope, get_elem, depth) -> Node | None:
    if loc.method == "ax":
        sub = scope
        if loc.attrs.get("parent"):
            pnode, _ = locate(tree, loc.attrs["parent"], get_elem, None, depth + 1)
            if pnode is None:
                return None
            inner = _descendants(tree, pnode) - {pnode.idx}
            sub = inner if sub is None else (sub & inner)
        hits = [n for n in tree if (sub is None or n.idx in sub) and _match_ax(loc, n)]
        if not hits:
            return None
        pick = loc.attrs.get("pick", "first")
        if pick == "first":
            return hits[0]
        if pick == "last":
            return hits[-1]
        k = int(pick)
        return hits[k - 1] if k <= len(hits) else None
    if loc.method == "text":
        pool = [n for n in tree if scope is None or n.idx in scope]
        exact = [n for n in pool if loc.text in (n.name, n.value)]
        hits = exact or [n for n in pool if loc.text and (loc.text in (n.name or "") or loc.text in (n.value or ""))]
        if not hits:
            return None
        if loc.position == "self":
            return hits[0]
        for anchor in hits:
            found = _relative(tree, anchor, loc.position, scope)
            if found is not None:
                return found
        return None
    if loc.method == "coord":
        base, _ = locate(tree, loc.elem, get_elem, None, depth + 1)
        if base is None or not base.bounds:
            return None
        x, y, w, h = base.bounds
        return point(x + w * loc.x / 100.0, y + h * loc.y / 100.0)
    return None
