"""The small grammars: card steps, conditions, locators and flow steps.

The grammar *is* the whitelist (SECURITY 3.1): anything that does not parse is
rejected, and there is simply no way to spell "run a command" or "open a URL".
All parsers expect the canonical English form (see i18n.canon_doc).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .i18n import tokenize


class GrammarError(ValueError):
    pass


ID_RE = re.compile(r"^(ENV|APP|ELEM|RCP|FAIL)\.[A-Z0-9_]+(?:\.[A-Z0-9_]+){0,2}(?:@[A-Za-z0-9_.\-]+)?$")
REF_RE = re.compile(r"^(ENV|APP|ELEM|RCP|FAIL)\.[A-Z0-9_]+(?:\.[A-Z0-9_]+){0,2}$")   # references never carry @
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
VAR_RE = re.compile(r"^\{([A-Za-z_][A-Za-z0-9_]*)(?:\.([^{}.\s]+))?\}$")
SECRET_RE = re.compile(r"^\{secret:([A-Z0-9_]+)\}$")
KEY_RE = re.compile(r"^[A-Za-z0-9]+(?:\+[A-Za-z0-9]+)*$")
TEMPLATE_VAR = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)(?:\.([^{}.\s]+))?\}")

CARD_VERBS = ("open", "goto", "click", "double_click", "right_click", "scroll", "drag",
              "key", "type", "clipboard", "move_window", "wait", "read", "assert",
              "call", "if", "end")
FLOW_VERBS = ("call", "read_table", "write_table", "wait_file", "confirm", "if", "end")
BANG_VERBS = ("click", "double_click", "right_click", "drag", "key", "type")
POINTER_VERBS = ("click", "double_click", "right_click", "drag")


# --------------------------------------------------------------------------- values

@dataclass(frozen=True)
class Lit:
    text: str


@dataclass(frozen=True)
class Var:
    name: str
    column: str | None = None

    def __str__(self):
        return "{" + self.name + (f".{self.column}" if self.column else "") + "}"


@dataclass(frozen=True)
class Template:
    """A flow-only composite such as ``{run_dir}/summary.xlsx``."""
    text: str

    def vars(self) -> list[str]:
        return [m.group(1) for m in TEMPLATE_VAR.finditer(self.text)]


def _unquote(tok: str) -> str:
    return re.sub(r"\\(.)", r"\1", tok[1:-1])


def parse_value(tok: str, *, allow_template=False, allow_number=False):
    if len(tok) >= 2 and tok[0] == '"' and tok[-1] == '"':
        return Lit(_unquote(tok))
    m = VAR_RE.match(tok)
    if m:
        return Var(m.group(1), m.group(2))
    if allow_number and re.fullmatch(r"-?\d+(\.\d+)?", tok):
        return Lit(tok)
    if allow_template and "{" in tok and "secret:" not in tok:
        return Template(tok)
    raise GrammarError(f'bad value {tok!r} (expected "literal" or {{name}})')


def _param(tok: str) -> Var:
    m = VAR_RE.match(tok)
    if not m or m.group(2):
        raise GrammarError(f"expected {{name}}, got {tok!r}")
    return Var(m.group(1))


def _ref(tok: str, kind: str | tuple[str, ...]) -> str:
    kinds = (kind,) if isinstance(kind, str) else kind
    if not REF_RE.match(tok) or tok.split(".")[0] not in kinds:
        raise GrammarError(f"expected {'/'.join(kinds)} id, got {tok!r}")
    return tok


# ----------------------------------------------------------------------- conditions

@dataclass(frozen=True)
class Atom:
    kind: str                      # see parse_condition / parse_flow_condition
    subject: object = None         # element id, Var, column name ...
    op: str | None = None
    value: object = None
    extra: dict = field(default_factory=dict, compare=False)


@dataclass(frozen=True)
class Cond:
    atoms: tuple[Atom, ...]

    def elements(self) -> list[str]:
        return [a.subject for a in self.atoms if a.kind in ("elem_state", "elem_cmp")]

    def vars(self) -> list[str]:
        out = []
        for a in self.atoms:
            for x in (a.subject, a.value, a.extra.get("in"), a.extra.get("file")):
                if isinstance(x, Var):
                    out.append(x.name)
                elif isinstance(x, Template):
                    out.extend(x.vars())
            rows = a.extra.get("rows")
            if isinstance(rows, Cond):
                out.extend(rows.vars())
        return out


def _split_and(toks: list[str]) -> list[list[str]]:
    parts, cur = [], []
    for t in toks:
        if t == "and":
            parts.append(cur)
            cur = []
        else:
            cur.append(t)
    parts.append(cur)
    if any(not p for p in parts):
        raise GrammarError("empty condition around 'and'")
    return parts


def parse_condition(s: str | list[str]) -> Cond:
    """Card conditions (DESIGN 6)."""
    toks = tokenize(s) if isinstance(s, str) else s
    if not toks:
        raise GrammarError("empty condition")
    if "or" in toks:
        raise GrammarError("'or' is not supported; only 'and'")
    atoms = []
    for p in _split_and(toks):
        if p[0] == "focus":
            if len(p) != 4 or p[1] != "value" or p[2] != "==":
                raise GrammarError("expected: focus value == <value>")
            atoms.append(Atom("focus_cmp", None, "==", parse_value(p[3])))
        elif REF_RE.match(p[0]):
            elem = _ref(p[0], "ELEM")
            if len(p) == 2 and p[1] in ("visible", "hidden"):
                atoms.append(Atom("elem_state", elem, p[1]))
            elif len(p) == 4 and p[1] in ("text", "value") and p[2] in ("==", "contains"):
                atoms.append(Atom("elem_cmp", elem, p[2], parse_value(p[3]), {"attr": p[1]}))
            else:
                raise GrammarError(f"bad element condition: {' '.join(p)}")
        elif p[0].startswith("{"):
            var = _param(p[0])
            if len(p) != 3 or p[1] not in ("==", "contains"):
                raise GrammarError(f"bad variable condition: {' '.join(p)}")
            atoms.append(Atom("var_cmp", var, p[1], parse_value(p[2])))
        else:
            raise GrammarError(f"bad condition: {' '.join(p)}")
    return Cond(tuple(atoms))


def _column(tok: str) -> str:
    if tok.startswith('"') and tok.endswith('"') and len(tok) >= 2:
        return _unquote(tok)
    if tok.startswith("{") or not tok:
        raise GrammarError(f"expected a column name, got {tok!r}")
    return tok


def parse_row_condition(toks: list[str]) -> Cond:
    """Row conditions used by where / rows (DESIGN 19.3)."""
    atoms = []
    for p in _split_and(toks):
        if len(p) != 3:
            raise GrammarError(f"bad row condition: {' '.join(p)}")
        col = _column(p[0])
        if p[1] == "in":
            m = VAR_RE.match(p[2])
            if not m or not m.group(2):
                raise GrammarError("expected: <column> in {table.column}")
            atoms.append(Atom("row_in", col, "in", Var(m.group(1), m.group(2))))
        elif p[1] in ("==", "!=", "contains"):
            atoms.append(Atom("row_cmp", col, p[1], parse_value(p[2], allow_number=True)))
        else:
            raise GrammarError(f"bad row operator {p[1]!r}")
    return Cond(tuple(atoms))


def parse_flow_condition(s: str | list[str]) -> Cond:
    toks = tokenize(s) if isinstance(s, str) else list(s)
    if not toks:
        raise GrammarError("empty condition")
    atoms, i, n = [], 0, len(toks)
    while i < n:
        if toks[i] == "step":
            if i + 2 >= n or not toks[i + 1].isdigit() or toks[i + 2] != "succeeded":
                raise GrammarError("expected: step <N> succeeded")
            atoms.append(Atom("step_ok", int(toks[i + 1])))
            i += 3
        elif toks[i].startswith("{"):
            subj = parse_value(toks[i], allow_template=True)
            if isinstance(subj, Lit):
                raise GrammarError("condition must start with a variable")
            nxt = toks[i + 1] if i + 1 < n else ""
            if nxt in ("empty", "not_empty"):
                atoms.append(Atom("var_empty", subj, nxt))
                i += 2
            elif nxt == "rows" and i + 3 < n and toks[i + 2] in (">", "==", "<") \
                    and re.fullmatch(r"\d+", toks[i + 3]):
                atoms.append(Atom("var_rows", subj, toks[i + 2], int(toks[i + 3])))
                i += 4
            elif nxt == "rows":
                try:
                    c = toks.index("column", i + 2)
                except ValueError:
                    raise GrammarError("expected: {file} rows <row condition> column <col> all == <value>")
                if c + 4 >= n or toks[c + 2:c + 4] != ["all", "=="]:
                    raise GrammarError("expected: column <col> all == <value>")
                atoms.append(Atom("table_all", subj, "==", parse_value(toks[c + 4], allow_number=True),
                                  {"rows": parse_row_condition(toks[i + 2:c]), "column": _column(toks[c + 1])}))
                i = c + 5
            elif nxt in ("==", "contains") and i + 2 < n:
                atoms.append(Atom("var_cmp", subj, nxt, parse_value(toks[i + 2], allow_number=True)))
                i += 3
            else:
                raise GrammarError(f"bad flow condition near {toks[i]!r}")
        else:
            raise GrammarError(f"bad flow condition near {toks[i]!r}")
        if i < n:
            if toks[i] != "and":
                raise GrammarError(f"expected 'and', got {toks[i]!r}")
            i += 1
            if i >= n:
                raise GrammarError("dangling 'and'")
    return Cond(tuple(atoms))


# ---------------------------------------------------------------------------- steps

@dataclass
class Step:
    verb: str
    bang: bool = False
    raw: str = ""
    target: str | None = None        # element / app / recipe id
    target2: str | None = None       # drag ... to X, move_window ... away_from X
    arg: object = None               # Var for type/clipboard, key combo, direction ...
    count: float | None = None       # scroll times / wait seconds
    mode: str | None = None          # shown|gone, text|value
    args: dict = field(default_factory=dict)   # call arguments
    out: Var | None = None           # -> {var}
    cond: Cond | None = None         # assert / if / where / rows
    then: Step | None = None         # if ... then <step>
    column: str | None = None        # write_table set <column>
    value: object = None             # write_table set ... = <value>
    text: str | None = None          # confirm "..."

    def elements(self) -> list[str]:
        out = [t for t in (self.target, self.target2) if t and t.startswith("ELEM.")]
        if self.cond:
            out.extend(self.cond.elements())
        if self.then:
            out.extend(self.then.elements())
        return out

    def leaf(self) -> Step:
        return self.then if self.verb == "if" and self.then else self


def _split_verb(tok: str) -> tuple[str, bool]:
    return (tok[:-1], True) if tok.endswith("!") else (tok, False)


def _seconds(tok: str) -> float:
    m = re.fullmatch(r"(\d+(?:\.\d+)?)s", tok)
    if not m:
        raise GrammarError(f"expected a duration like 5s, got {tok!r}")
    return float(m.group(1))


def _call(toks: list[str], raw: str, *, flow: bool) -> Step:
    if len(toks) < 2:
        raise GrammarError("call needs a recipe id")
    st = Step("call", raw=raw, target=_ref(toks[1], "RCP"))
    rest = toks[2:]
    if len(rest) >= 2 and rest[-2] == "->":
        st.out = _param(rest[-1])
        rest = rest[:-2]
    for t in rest:
        if "=" not in t or t.startswith('"'):
            raise GrammarError(f"call arguments must be name=value, got {t!r}")
        k, v = t.split("=", 1)
        if not NAME_RE.match(k):
            raise GrammarError(f"bad argument name {k!r}")
        if k in st.args:
            raise GrammarError(f"duplicate argument {k!r}")
        if flow:
            st.args[k] = parse_value(v, allow_template=True) if v else Lit("")
        else:
            # Cards may only forward parameters: a literal here could end up in `type`.
            st.args[k] = _param(v)
    return st


def parse_step(s: str, *, _nested=False) -> Step:
    """Parse one card step."""
    if not isinstance(s, str) or not s.strip():
        raise GrammarError("step must be a non-empty string")
    raw = s.strip()
    toks = tokenize(raw)
    verb, bang = _split_verb(toks[0])
    if verb not in CARD_VERBS:
        raise GrammarError(f"unknown verb {toks[0]!r}")
    if bang and verb not in BANG_VERBS:
        raise GrammarError(f"'!' is not allowed on {verb}")
    a = toks[1:]

    def need(n, usage):
        if len(a) != n:
            raise GrammarError(f"usage: {usage}")

    st = Step(verb, bang, raw)
    if verb == "open":
        need(1, "open <APP id>")
        st.target = _ref(a[0], "APP")
    elif verb == "goto":
        need(1, "goto <screen id>")
        st.target = _ref(a[0], "ELEM")
    elif verb in ("click", "double_click", "right_click"):
        need(1, f"{verb} <element>")
        st.target = _ref(a[0], "ELEM")
    elif verb == "scroll":
        need(3, "scroll <element> up|down <times>")
        st.target = _ref(a[0], "ELEM")
        if a[1] not in ("up", "down") or not a[2].isdigit() or not 1 <= int(a[2]) <= 50:
            raise GrammarError("usage: scroll <element> up|down <times 1-50>")
        st.arg, st.count = a[1], int(a[2])
    elif verb == "drag":
        need(3, "drag <element> to <element>")
        if a[1] != "to":
            raise GrammarError("usage: drag <element> to <element>")
        st.target, st.target2 = _ref(a[0], "ELEM"), _ref(a[2], "ELEM")
    elif verb == "key":
        need(1, "key <combo>")
        if not KEY_RE.match(a[0]):
            raise GrammarError(f"bad key combo {a[0]!r}")
        st.arg = a[0]
    elif verb in ("type", "clipboard"):
        need(1, f"{verb} {{param}}")
        st.arg = _param(a[0])        # literals are rejected on purpose
    elif verb == "move_window":
        need(3, "move_window <element> away_from <element>")
        if a[1] != "away_from":
            raise GrammarError("usage: move_window <element> away_from <element>")
        st.target, st.target2 = _ref(a[0], "ELEM"), _ref(a[2], "ELEM")
    elif verb == "wait":
        need(3, "wait <element> shown|gone <N>s")
        if a[1] not in ("shown", "gone"):
            raise GrammarError("usage: wait <element> shown|gone <N>s")
        st.target, st.mode, st.count = _ref(a[0], "ELEM"), a[1], _seconds(a[2])
        if st.count > 600:
            raise GrammarError("wait is limited to 600s")
    elif verb == "read":
        need(4, "read <element> text|value -> {var}")
        if a[1] not in ("text", "value") or a[2] != "->":
            raise GrammarError("usage: read <element> text|value -> {var}")
        st.target, st.mode, st.out = _ref(a[0], "ELEM"), a[1], _param(a[3])
    elif verb == "assert":
        st.cond = parse_condition(a)
    elif verb == "call":
        st = _call(toks, raw, flow=False)
    elif verb == "if":
        if _nested:
            raise GrammarError("'if' cannot be nested")
        if "then" not in a:
            raise GrammarError("usage: if <condition> then <single action>")
        k = a.index("then")
        st.cond = parse_condition(a[:k])
        inner = parse_step(" ".join(a[k + 1:]), _nested=True)
        if inner.verb in ("if", "call"):
            raise GrammarError("the action after 'then' cannot be if or call")
        st.then = inner
    elif verb == "end":
        need(0, "end")
    return st


def parse_flow_step(s: str, *, _nested=False) -> Step:
    """Parse one flow step: only 7 verbs, no clicking or locating (DESIGN 19.3)."""
    if not isinstance(s, str) or not s.strip():
        raise GrammarError("step must be a non-empty string")
    raw = s.strip()
    toks = tokenize(raw)
    verb = toks[0]
    if verb not in FLOW_VERBS:
        raise GrammarError(f"flows only allow {', '.join(FLOW_VERBS)}; got {verb!r}")
    a = toks[1:]
    st = Step(verb, raw=raw)
    if verb == "call":
        st = _call(toks, raw, flow=True)
    elif verb == "read_table":
        if len(a) < 3 or a[-2] != "->":
            raise GrammarError("usage: read_table {file} [where <row condition>] -> {var}")
        st.arg = parse_value(a[0], allow_template=True)
        st.out = _param(a[-1])
        mid = a[1:-2]
        if mid:
            if mid[0] != "where":
                raise GrammarError("usage: read_table {file} [where <row condition>] -> {var}")
            st.cond = parse_row_condition(mid[1:])
    elif verb == "write_table":
        if len(a) < 6 or a[1] != "rows" or "set" not in a:
            raise GrammarError("usage: write_table {file} rows <row condition> set <column> = <value>")
        k = len(a) - 1 - a[::-1].index("set")
        if a[k + 2:k + 3] != ["="] or len(a) != k + 4:
            raise GrammarError("usage: write_table {file} rows <row condition> set <column> = <value>")
        st.arg = parse_value(a[0], allow_template=True)
        st.cond = parse_row_condition(a[2:k])
        st.column = _column(a[k + 1])
        st.value = parse_value(a[k + 3], allow_number=True)
    elif verb == "wait_file":
        if len(a) != 2:
            raise GrammarError("usage: wait_file {path} <N>s")
        st.arg, st.count = parse_value(a[0], allow_template=True), _seconds(a[1])
    elif verb == "confirm":
        if len(a) != 1 or not (a[0].startswith('"') and a[0].endswith('"')):
            raise GrammarError('usage: confirm "<message>"')
        st.text = _unquote(a[0])
    elif verb == "if":
        if _nested:
            raise GrammarError("'if' cannot be nested")
        if "then" not in a:
            raise GrammarError("usage: if <condition> then <single action>")
        k = a.index("then")
        st.cond = parse_flow_condition(a[:k])
        inner = parse_flow_step(" ".join(a[k + 1:]), _nested=True)
        if inner.verb in ("if", "call"):
            raise GrammarError("the action after 'then' cannot be if or call")
        st.then = inner
    elif verb == "end":
        if a:
            raise GrammarError("usage: end")
    return st


# ------------------------------------------------------------------------- locators

@dataclass(frozen=True)
class Locator:
    method: str                    # ax | text | coord | vision
    raw: str
    attrs: dict = field(default_factory=dict, compare=False)
    text: str | None = None
    position: str = "self"
    elem: str | None = None        # coord anchor
    x: float = 0.0
    y: float = 0.0

    @property
    def uses_ui_text(self) -> bool:
        """True when the locator depends on UI language (needs applies.lang)."""
        return self.method == "text" or (self.method == "ax" and ("name" in self.attrs or "value" in self.attrs))


def parse_locator(s: str) -> Locator:
    if not isinstance(s, str) or not s.strip():
        raise GrammarError("locator must be a non-empty string")
    raw = s.strip()
    toks = tokenize(raw)
    m, a = toks[0], toks[1:]
    if m == "ax":
        attrs = {}
        for t in a:
            if "=" not in t:
                raise GrammarError(f"ax expects key=value, got {t!r}")
            k, v = t.split("=", 1)
            if k not in ("role", "name", "id", "value", "parent", "pick") or k in attrs:
                raise GrammarError(f"bad or duplicate ax attribute {k!r}")
            if v.startswith('"') and v.endswith('"') and len(v) >= 2:
                v = _unquote(v)
            if not v:
                raise GrammarError(f"ax {k}= is empty")
            if k == "parent":
                _ref(v, "ELEM")
            if k == "pick" and v not in ("first", "last") and not (v.isdigit() and int(v) >= 1):
                raise GrammarError("pick must be first, last or a number >= 1")
            attrs[k] = v
        if not (set(attrs) & {"role", "name", "id", "value"}):
            raise GrammarError("ax needs at least one of role/name/id/value")
        return Locator("ax", raw, attrs)
    if m == "text":
        if not a or not (a[0].startswith('"') and a[0].endswith('"')) or len(a) > 2:
            raise GrammarError('usage: text "<text>" [self|right_of|left_of|above|below]')
        pos = a[1] if len(a) == 2 else "self"
        if pos not in ("self", "right_of", "left_of", "above", "below"):
            raise GrammarError(f"bad text position {pos!r}")
        return Locator("text", raw, text=_unquote(a[0]), position=pos)
    if m == "coord":
        if len(a) != 3 or not all(re.fullmatch(r"\d+(\.\d+)?%", t) for t in a[1:]):
            raise GrammarError("usage: coord <element> <x%> <y%>")
        x, y = float(a[1][:-1]), float(a[2][:-1])
        if not (0 <= x <= 100 and 0 <= y <= 100):
            raise GrammarError("coord percentages must be within 0-100")
        return Locator("coord", raw, elem=_ref(a[0], "ELEM"), x=x, y=y)
    if m == "vision":
        if not a:
            raise GrammarError("vision needs a description")
        return Locator("vision", raw, text=raw[len("vision"):].strip())
    raise GrammarError(f"unknown locator method {m!r}")
