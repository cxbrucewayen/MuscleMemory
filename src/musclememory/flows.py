"""Flows (DESIGN 19): orchestrate recipes across apps, pass data, resume, schedule.

A flow never clicks or locates anything itself; it has seven verbs and every
app operation goes through `call`. Flows are local and personal: they are never
proposed or published.
"""

from __future__ import annotations

import csv
import datetime
import hashlib
import io
import json
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from .cards import KB, STATE_RANK, Card, load_yaml, parse_id, swap_platform
from .executor import Executor, trace_secret
from .fmt import FLOW_ORDER, dump_card, dump_doc
from .grammar import (
    SECRET_RE,
    TEMPLATE_VAR,
    GrammarError,
    Lit,
    Template,
    Var,
    parse_flow_condition,
    parse_flow_step,
    parse_step,
)
from .i18n import canon_doc
from .resolve import element_refs, recipe_refs, static_merge
from .secrets import NAME_RE as SECRET_NAME_RE
from .secrets import Secret, SecretStore

FLOW_ID = re.compile(r"^FLOW\.[A-Z0-9_]+$")
FLOW_FIELDS = set(FLOW_ORDER)
BUILTINS = ("workdir", "run_dir", "today")
RECIPIENT_PARAMS = {"contact", "contacts", "recipient", "recipients", "to", "receiver", "group", "chat",
                    "channel", "email", "phone"}
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_SCHEDULE = re.compile(r"^schedule\s+(?:(daily|weekdays|mon|tue|wed|thu|fri|sat|sun)\s+)?(\d{1,2}):(\d{2})$", re.I)
MAX_BUSY_WAIT = 30 * 60


class FlowError(Exception):
    pass


@dataclass
class Table:
    rows: list[dict]
    path: str | None = None


@dataclass
class FlowResult:
    status: str                # ok | paused | failed | skipped | deferred | confirm_required
    flow: str
    message: str = ""
    step: int | None = None
    run_dir: str | None = None
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {"status": self.status, "flow": self.flow, "message": self.message}
        if self.step is not None:
            d["step"] = self.step
        if self.run_dir:
            d["run_dir"] = self.run_dir
        if self.detail:
            d["detail"] = self.detail
        return d


# ------------------------------------------------------------------------- loading

def load_flow(path: Path) -> dict:
    doc = load_yaml(Path(path).read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise FlowError("a flow file must be one YAML mapping")
    flow = canon_doc(doc)
    flow["_path"] = str(path)
    return flow


def find_flow_path(kb: KB, flow_id: str) -> Path:
    p = Path(flow_id)
    if p.suffix == ".yaml" and p.is_file():
        return p
    for path in kb.flow_files():
        try:
            if load_flow(path).get("id") == flow_id:
                return path
        except Exception:
            continue
    raise FlowError(f"no flow {flow_id!r} in {kb.flows_dir}")


def save_flow(flow: dict):
    body = {k: v for k, v in flow.items() if not k.startswith("_")}
    Path(flow["_path"]).write_text(dump_doc(body, FLOW_ORDER), encoding="utf-8", newline="\n")


def parsed_steps(flow: dict) -> list:
    return [parse_flow_step(s) for s in flow.get("steps") or []]


# -------------------------------------------------------------------- static check

def _callee_variants(kb: KB, ref: str) -> list[tuple[str, dict]]:
    """All statically known implementations of a call target: (id, merged data)."""
    parts = parse_id(ref)
    out = []
    if parts.platform == "COMMON":
        common = kb.get(ref)
        twins = [c for c in kb.cards.values() if c.type == "RCP" and not c.is_variant
                 and c.platform != "COMMON" and swap_platform(c.base_id, "COMMON") == ref]
        out.extend((t.id, static_merge(kb, t)) for t in twins)
        if common and not twins:
            out.append((common.id, dict(common.data)))
    else:
        card = kb.get(ref)
        if card:
            out.append((card.id, static_merge(kb, card)))
    return out


def _static_recipe(kb: KB, platform: str | None):
    def get(ref: str) -> dict | None:
        parts = parse_id(ref)
        if parts.platform == "COMMON" and platform:
            twin = kb.get(swap_platform(ref, platform))
            if twin:
                return static_merge(kb, twin)
        card = kb.get(ref)
        return static_merge(kb, card) if card else None
    return get


def check_flow(kb: KB, flow: dict) -> list[str]:
    errs: list[str] = []
    from . import FORMAT
    if flow.get("format") != FORMAT:
        errs.append(f"format must be {FORMAT}")
    if not isinstance(flow.get("id"), str) or not FLOW_ID.match(flow["id"]):
        errs.append("id must be FLOW.<NAME> in ASCII upper case")
    for k in flow:
        if not k.startswith("_") and k not in FLOW_FIELDS:
            errs.append(f"unknown field {k!r}")
    for k in ("aliases", "trigger", "workdir", "steps", "check", "state", "verified"):
        if k not in flow:
            errs.append(f"missing field {k!r}")
    if flow.get("state") is not None and flow.get("state") not in STATE_RANK:
        errs.append("state must be observed, reproduced, stable or recheck")
    if flow.get("when_busy", "wait") not in ("wait", "skip", "notify"):
        errs.append("when_busy must be wait, skip or notify")
    triggers = flow.get("trigger")
    for t in triggers if isinstance(triggers, list) else [triggers] if triggers else []:
        t = str(t)
        if t != "manual" and not _SCHEDULE.match(t) and not re.match(r"^file_change\s+\S+$", t):
            errs.append(f"bad trigger {t!r} (manual | schedule [daily|weekdays|Mon..Sun] HH:MM | file_change {{path}})")

    secrets = flow.get("secrets") or []
    if not isinstance(secrets, list) or not all(isinstance(s, str) and SECRET_NAME_RE.match(s) for s in secrets):
        errs.append("secrets must be a list of NAMES")
        secrets = []
    inputs = flow.get("inputs") or {}
    if not isinstance(inputs, dict):
        errs.append("inputs must be a mapping")
        inputs = {}
    secret_vars = {}
    for name, value in inputs.items():
        m = SECRET_RE.match(str(value))
        if m:
            secret_vars[name] = m.group(1)
            if m.group(1) not in secrets:
                errs.append(f"input {name!r} uses undeclared secret {m.group(1)}")
        elif "{secret:" in str(value):
            errs.append(f"input {name!r}: a secret must be the whole value, written {{secret:NAME}}")
    for key in ("steps", "check", "authorize", "workdir", "aliases", "trigger", "lessons"):
        if "{secret:" in json.dumps(flow.get(key), ensure_ascii=False, default=str):
            errs.append(f"{key}: secrets may only be bound in inputs")

    known = set(inputs) | set(BUILTINS)
    tables: set[str] = set()

    def use(v, where, *, table_ok=False, secret_ok=False):
        names = [v.name] if isinstance(v, Var) else v.vars() if isinstance(v, Template) else []
        for n in names:
            if n not in known:
                errs.append(f"{where}: {{{n}}} has no value yet")
            if n in secret_vars and not secret_ok:
                errs.append(f"{where}: secret {{{n}}} may only be passed to a recipe parameter")
            if n in tables and not table_ok:
                errs.append(f"{where}: {{{n}}} is a table and cannot be used as text")

    def path_ok(v, where):
        text = inputs.get(v.name) if isinstance(v, Var) and v.name in inputs else getattr(v, "text", None)
        if isinstance(v, Var) and v.name not in inputs:
            return                              # produced by a recipe; checked at run time
        if not isinstance(text, str) or not text.startswith(("{workdir}", "{run_dir}")):
            errs.append(f"{where}: file paths must start with {{workdir}} or {{run_dir}}")

    def cond_use(cond, where):
        for a in cond.atoms:
            for x in (a.subject, a.value):
                use(x, where, table_ok=True)
            if a.kind == "row_in" and isinstance(a.value, Var) and a.value.name not in tables:
                errs.append(f"{where}: {{{a.value.name}}} is not a table")
            if a.kind == "table_all":
                path_ok(a.subject, where)
                cond_use(a.extra["rows"], where)

    steps = flow.get("steps")
    if not isinstance(steps, list) or not steps:
        errs.append("steps must be a non-empty list")
        steps = []
    call_steps = set()
    for i, raw in enumerate(steps, 1):
        where = f"step {i}"
        try:
            st = parse_flow_step(raw)
        except (GrammarError, ValueError) as e:
            errs.append(f"{where}: {e}")
            continue
        if st.cond is not None and st.verb == "if":
            cond_use(st.cond, where)
        leaf = st.leaf()
        if leaf.verb == "call":
            call_steps.add(i)
            impls = _callee_variants(kb, leaf.target)
            if not impls:
                errs.append(f"{where}: recipe {leaf.target} does not exist yet (explore it, then propose the card)")
            for cid, data in impls:
                want = sorted(data.get("params") or [])
                if want != sorted(leaf.args):
                    errs.append(f"{where}: {cid} takes parameters {want}, got {sorted(leaf.args)}")
                if leaf.out is not None and not data.get("output"):
                    errs.append(f"{where}: {cid} declares no output to receive with ->")
            for pname, v in leaf.args.items():
                use(v, where, secret_ok=isinstance(v, Var))
                if isinstance(v, Var) and v.name in secret_vars:
                    for cid, _ in impls:
                        plat = parse_id(cid).platform
                        errs.extend(f"{where}: {p}" for p in trace_secret(_static_recipe(kb, plat), leaf.target, pname))
        elif leaf.verb in ("read_table", "write_table", "wait_file"):
            use(leaf.arg, where)
            path_ok(leaf.arg, where)
            if leaf.cond is not None:
                cond_use(leaf.cond, where)
            if leaf.verb == "write_table":
                use(leaf.value, where)
        if leaf.out is not None:
            if leaf.out.name in BUILTINS or leaf.out.name in secret_vars:
                errs.append(f"{where}: cannot assign to {{{leaf.out.name}}}")
            known.add(leaf.out.name)
            if leaf.verb == "read_table":
                tables.add(leaf.out.name)

    checks = flow.get("check")
    if not isinstance(checks, list) or not checks:
        errs.append("check must be a non-empty list of conditions")
    for i, raw in enumerate(checks if isinstance(checks, list) else [], 1):
        try:
            cond = parse_flow_condition(raw)
        except (GrammarError, ValueError) as e:
            errs.append(f"check {i}: {e}")
            continue
        cond_use(cond, f"check {i}")
        for a in cond.atoms:
            if a.kind == "step_ok" and not 1 <= a.subject <= len(steps):
                errs.append(f"check {i}: there is no step {a.subject}")

    auth = flow.get("authorize")
    if auth is not None:
        if not isinstance(auth, dict) or set(auth) - {"unattended", "files", "recipients"}:
            errs.append("authorize may only contain unattended, files and recipients")
        else:
            for n in auth.get("unattended") or []:
                if n not in call_steps:
                    errs.append(f"authorize.unattended: step {n} is not a call step")
            for k in ("files", "recipients"):
                if not all(isinstance(x, str) for x in auth.get(k) or []):
                    errs.append(f"authorize.{k} must be a list of text")
    v = flow.get("verified")
    if v is not None and not (isinstance(v, dict) and isinstance(v.get("count"), int)):
        errs.append("verified must be {count: N, last: YYYY-MM-DD}")
    return errs


def check_flow_file(kb: KB, path: Path) -> list[str]:
    try:
        return check_flow(kb, load_flow(path))
    except Exception as e:
        return [f"cannot load: {e}"]


# ---------------------------------------------------------------------- lock hash

def static_closure(kb: KB, ref: str, platform: str) -> list[Card]:
    """Every card that could take part in running `ref` on this platform: the
    recipe, its variants, called recipes, elements, the app card and the app's
    navigation recipes. Any change to any of them must invalidate an approval."""
    seen: dict[str, Card] = {}
    todo = [ref]
    apps_done: set = set()

    def add_family(base_id: str) -> list[Card]:
        fam = kb.family(base_id)
        for c in fam:
            seen[c.id] = c
        return fam

    while todo:
        cur = todo.pop()
        try:
            parts = parse_id(cur)
        except ValueError:
            continue
        ids = [parts.base]
        if parts.platform == "COMMON":
            ids.append(swap_platform(parts.base, platform))
        elif parts.type == "RCP":
            ids.append(swap_platform(parts.base, "COMMON"))
        for base_id in ids:
            if base_id in seen or not kb.family(base_id):
                continue
            for card in add_family(base_id):
                merged = static_merge(kb, card)
                if card.type == "RCP":
                    calls, elems, apps, _ = recipe_refs(merged)
                    todo.extend(calls + elems + apps)
                elif card.type == "ELEM":
                    todo.extend(element_refs(merged)[0])
                elif card.type == "APP" and isinstance(merged.get("home"), str):
                    todo.append(merged["home"])
                key = (card.platform, card.app)
                if card.app and card.platform != "COMMON" and key not in apps_done:
                    apps_done.add(key)
                    todo.append(f"APP.{card.platform}.{card.app}")
                    for nav in kb.by_type("RCP", card.platform, card.app):
                        m = static_merge(kb, nav)
                        if m.get("side_effect") == "none" and not m.get("params") and m.get("ends_at"):
                            todo.append(nav.base_id)
    return [seen[k] for k in sorted(seen)]


def lock_hash(kb: KB, flow: dict, platform: str) -> str:
    """sha256 over the flow (minus lock, lessons and the verified counter) and the
    canonical text of every card in the static closure of its calls."""
    body = {k: v for k, v in flow.items() if not k.startswith("_") and k not in ("lock", "lessons", "verified")}
    h = hashlib.sha256()
    h.update(dump_doc(body, FLOW_ORDER).encode("utf-8"))
    refs = []
    for raw in flow.get("steps") or []:
        try:
            st = parse_flow_step(raw).leaf()
        except (GrammarError, ValueError):
            continue
        if st.verb == "call":
            refs.append(st.target)
    cards: dict[str, Card] = {}
    for ref in refs:
        for c in static_closure(kb, ref, platform):
            cards[c.id] = c
    for cid in sorted(cards):
        h.update(b"\n--- " + cid.encode("utf-8") + b"\n")
        h.update(dump_card(cards[cid].data).encode("utf-8"))
    return "sha256:" + h.hexdigest()


def flow_bang_steps(kb: KB, flow: dict, platform: str) -> dict[int, list[str]]:
    """Which flow steps reach a `!` step: {step number: [descriptions]}."""
    out: dict[int, list[str]] = {}
    for i, raw in enumerate(flow.get("steps") or [], 1):
        try:
            st = parse_flow_step(raw).leaf()
        except (GrammarError, ValueError):
            continue
        if st.verb != "call":
            continue
        found = []
        for card in static_closure(kb, st.target, platform):
            if card.type != "RCP" or card.platform == "COMMON":
                continue
            for n, s in enumerate(static_merge(kb, card).get("steps") or [], 1):
                try:
                    if parse_step(s).leaf().bang:
                        found.append(f"{card.id} step {n}: {s}")
                except (GrammarError, ValueError):
                    pass
        if found:
            out[i] = found
    return out


# ------------------------------------------------------------------------- tables

def load_table(path: Path) -> tuple[list[str], list[dict]]:
    if path.suffix.lower() == ".xlsx":
        try:
            import openpyxl
        except ImportError:
            raise FlowError("reading .xlsx needs `pip install musclememory[xlsx]`")
        ws = openpyxl.load_workbook(path, read_only=True, data_only=True).active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return [], []
        header = [str(h) if h is not None else "" for h in rows[0]]
        return header, [{h: ("" if v is None else str(v)) for h, v in zip(header, r)} for r in rows[1:]]
    text = path.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader.fieldnames or []), [{k: (v or "") for k, v in r.items() if k is not None} for r in reader]


def save_table(path: Path, header: list[str], rows: list[dict]):
    if path.suffix.lower() == ".xlsx":
        import openpyxl
        wb = openpyxl.load_workbook(path)
        ws = wb.active
        ws.delete_rows(1, ws.max_row)
        ws.append(header)
        for r in rows:
            ws.append([r.get(h, "") for h in header])
        wb.save(path)
        return
    bom = path.read_bytes().startswith(b"\xef\xbb\xbf") if path.exists() else False
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=header, lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    path.write_text(buf.getvalue(), encoding="utf-8-sig" if bom else "utf-8", newline="")


# ------------------------------------------------------------------------- runner

class _Pause(Exception):
    def __init__(self, message, detail=None, status="paused"):
        super().__init__(message)
        self.detail = detail or {}
        self.status = status


class FlowRunner:
    def __init__(self, kb: KB, driver, *, secrets: SecretStore | None = None, confirm=None, ask=None,
                 unattended: bool = False, preapproved: bool = False, env_overrides: dict | None = None,
                 sleep=time.sleep):
        self.kb = kb
        self.driver = driver
        self.secrets = secrets or SecretStore()
        self.confirm = confirm            # callback for `!` steps
        self.ask = ask                    # callback for the `confirm` verb
        self.unattended = unattended
        self.preapproved = preapproved
        self.env_overrides = env_overrides
        self.sleep = sleep

    # --- run directories and checkpoints ---------------------------------------
    def _flow_dir(self, flow_id: str) -> Path:
        return self.kb.root / "runs" / flow_id

    def _latest(self, flow_id: str) -> dict | None:
        try:
            return json.loads((self._flow_dir(flow_id) / "latest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _save(self, st: dict):
        run_dir = Path(st["run_dir"])
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "state.json").write_text(json.dumps(st, ensure_ascii=False, indent=1, default=_ser), encoding="utf-8")
        (self._flow_dir(st["flow"]) / "latest.json").write_text(
            json.dumps({k: st[k] for k in ("flow", "run_id", "run_dir", "status", "started", "trigger")},
                       ensure_ascii=False), encoding="utf-8")

    def _notify(self, text: str):
        log = self.kb.root / "runs" / "notifications.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now().isoformat(timespec='seconds')} {text}\n")

    # --- variables --------------------------------------------------------------
    def _text(self, v, scope: dict, *, where="") -> str:
        if isinstance(v, Lit):
            return v.text
        if isinstance(v, Var):
            val = scope.get(v.name)
            if val is None:
                raise FlowError(f"{where}: {{{v.name}}} has no value")
            if isinstance(val, (Secret, Table)):
                raise FlowError(f"{where}: {{{v.name}}} cannot be used as text")
            return str(val)
        if isinstance(v, Template):
            return self._expand(v.text, scope, where)
        return "" if v is None else str(v)

    def _expand(self, text: str, scope: dict, where="") -> str:
        def sub(m):
            val = scope.get(m.group(1))
            if val is None or isinstance(val, (Secret, Table)) or m.group(2):
                raise FlowError(f"{where}: cannot expand {m.group(0)}")
            return str(val)
        return TEMPLATE_VAR.sub(sub, text)

    def _path(self, v, scope: dict, where: str) -> Path:
        p = Path(self._text(v, scope, where=where))
        if not p.is_absolute():
            p = Path(scope["workdir"]) / p
        p = p.resolve()
        for base in (Path(scope["workdir"]).resolve(), Path(scope["run_dir"]).resolve()):
            try:
                p.relative_to(base)
                return p
            except ValueError:
                pass
        raise FlowError(f"{where}: {p.name} is outside workdir and run_dir")

    def _row_match(self, cond, row: dict, scope: dict, where: str) -> bool:
        for a in cond.atoms:
            cell = str(row.get(a.subject, ""))
            if a.kind == "row_in":
                table = scope.get(a.value.name)
                if not isinstance(table, Table):
                    raise FlowError(f"{where}: {{{a.value.name}}} is not a table")
                if cell not in {str(r.get(a.value.column, "")) for r in table.rows}:
                    return False
            else:
                want = self._text(a.value, scope, where=where)
                ok = {"==": cell == want, "!=": cell != want, "contains": want in cell}[a.op]
                if not ok:
                    return False
        return True

    def _cond(self, cond, scope: dict, done: list[int], where: str) -> bool:
        for a in cond.atoms:
            if a.kind == "step_ok":
                if a.subject not in done:
                    return False
            elif a.kind == "var_empty":
                val = scope.get(a.subject.name) if isinstance(a.subject, Var) else self._text(a.subject, scope)
                empty = (not val.rows) if isinstance(val, Table) else (val is None or str(val) == "")
                if empty != (a.op == "empty"):
                    return False
            elif a.kind == "var_rows":
                val = scope.get(a.subject.name) if isinstance(a.subject, Var) else None
                n = len(val.rows) if isinstance(val, Table) else 0
                if not {">": n > a.value, "==": n == a.value, "<": n < a.value}[a.op]:
                    return False
            elif a.kind == "table_all":
                _, rows = load_table(self._path(a.subject, scope, where))
                want = self._text(a.value, scope, where=where)
                for r in rows:
                    if self._row_match(a.extra["rows"], r, scope, where) and str(r.get(a.extra["column"], "")) != want:
                        return False
            elif a.kind == "var_cmp":
                have, want = self._text(a.subject, scope, where=where), self._text(a.value, scope, where=where)
                if not (have == want if a.op == "==" else want in have):
                    return False
        return True

    # --- entry points -------------------------------------------------------------
    def run(self, flow_id: str, *, trigger: str = "manual") -> FlowResult:
        flow = load_flow(find_flow_path(self.kb, flow_id))
        errs = check_flow(self.kb, flow)
        if errs:
            return FlowResult("failed", flow.get("id", flow_id), "flow check failed: " + "; ".join(errs[:5]))
        fid = flow["id"]
        if self.unattended:
            why = self.unattended_blockers(flow)
            if why:
                self._notify(f"{fid} did not start unattended: {'; '.join(why)}")
                return FlowResult("paused", fid, "not approved for unattended running: " + "; ".join(why))
        run_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir = self._flow_dir(fid) / run_id
        n = 1
        while run_dir.exists():
            n += 1
            run_dir = self._flow_dir(fid) / f"{run_id}-{n}"
        st = {"flow": fid, "run_id": run_dir.name, "run_dir": str(run_dir), "status": "running",
              "started": time.time(), "trigger": trigger, "next": 1, "done": [], "vars": {}}
        return self._drive(flow, st)

    def resume(self, flow_id: str, *, step_done: bool = False, redo: bool = False) -> FlowResult:
        flow = load_flow(find_flow_path(self.kb, flow_id))
        fid = flow["id"]
        latest = self._latest(fid)
        if not latest:
            return FlowResult("failed", fid, "nothing to resume")
        st = json.loads((Path(latest["run_dir"]) / "state.json").read_text(encoding="utf-8"))
        if st.get("status") != "paused":
            return FlowResult("failed", fid, f"the last run is {st.get('status')}, not paused")
        if step_done:
            st["done"].append(st["next"])
            st["next"] += 1
        elif st.get("uncertain") and not redo:
            return FlowResult("paused", fid, "the paused step may already have had an external effect. Verify in the "
                              "app, then resume with step_done (it happened) or redo (it did not).", step=st["next"])
        st["status"] = "running"
        st.pop("uncertain", None)
        return self._drive(flow, st)

    def unattended_blockers(self, flow: dict) -> list[str]:
        """Why this flow may not run without the user (DESIGN 19.7)."""
        why = []
        platform = self.driver.platform()
        if flow.get("state") != "stable":
            why.append(f"flow state is {flow.get('state')}, needs stable")
        if not flow.get("lock"):
            why.append("not approved yet (kb flow approve)")
        elif flow["lock"] != lock_hash(self.kb, flow, platform):
            why.append("the flow or one of its cards changed since approval (review, then kb flow approve)")
        auth = flow.get("authorize") or {}
        for n in sorted(set(flow_bang_steps(self.kb, flow, platform)) - set(auth.get("unattended") or [])):
            why.append(f"step {n} has ! steps but is not in authorize.unattended")
        for name in flow.get("secrets") or []:
            if not self.secrets.has(name):
                why.append(f"secret {name} is not stored (kb secret set {name})")
        ex = Executor(self.kb, self.driver, env_overrides=self.env_overrides, record=False)
        from .resolve import runnable
        for st in parsed_steps(flow):
            leaf = st.leaf()
            if leaf.verb == "call":
                ok, reasons = runnable(ex.expand(leaf.target))
                if not ok:
                    why.append(f"{leaf.target} is not directly runnable ({reasons[0]})")
        return why

    # --- the loop -----------------------------------------------------------------
    def _scope(self, flow: dict, st: dict) -> dict:
        workdir = Path(str(flow["workdir"]))
        if not workdir.is_absolute():
            workdir = self.kb.root / workdir
        scope = {"workdir": str(workdir), "run_dir": st["run_dir"], "today": datetime.date.today().isoformat()}
        for name, value in (flow.get("inputs") or {}).items():
            m = SECRET_RE.match(str(value))
            scope[name] = self.secrets.handle(m.group(1)) if m else self._expand(str(value), scope, f"input {name}")
        for name, value in st["vars"].items():
            scope[name] = Table(value["__table__"], value.get("path")) if isinstance(value, dict) else value
        return scope

    def _drive(self, flow: dict, st: dict) -> FlowResult:
        fid = flow["id"]
        Path(st["run_dir"]).mkdir(parents=True, exist_ok=True)
        try:
            scope = self._scope(flow, st)
            if not Path(scope["workdir"]).is_dir():
                raise FlowError(f"workdir does not exist: set `workdir` in {Path(flow['_path']).name} to a real folder")
            steps = parsed_steps(flow)
            ended = False
            while st["next"] <= len(steps) and not ended:
                i = st["next"]
                self._save(st)
                ended = self._step(flow, steps[i - 1], i, scope, st) == "end"
                st["done"].append(i)
                st["next"] = i + 1
                st["vars"] = {k: v for k, v in scope.items()
                              if k not in BUILTINS and k not in (flow.get("inputs") or {})
                              and not isinstance(v, Secret)}
            for i, raw in enumerate(flow.get("check") or [], 1):
                if not self._cond(parse_flow_condition(raw), scope, st["done"], f"check {i}"):
                    raise _Pause(f"check {i} failed: {raw}", status="failed")
        except _Pause as p:
            st["status"] = p.status
            st["message"] = str(p)
            if p.detail.get("uncertain"):
                st["uncertain"] = True
            self._save(st)
            if self.unattended:
                self._notify(f"{fid} {p.status} at step {st['next']}: {p}")
            return FlowResult(p.status, fid, str(p), step=st["next"], run_dir=st["run_dir"], detail=p.detail)
        except (FlowError, OSError) as e:
            st["status"] = "paused"
            st["message"] = str(e)
            self._save(st)
            if self.unattended:
                self._notify(f"{fid} paused at step {st['next']}: {e}")
            return FlowResult("paused", fid, str(e), step=st["next"], run_dir=st["run_dir"])
        st["status"] = "ok"
        self._save(st)
        self._record_success(flow)
        return FlowResult("ok", fid, "check passed", run_dir=st["run_dir"])

    def _record_success(self, flow: dict):
        v = flow.get("verified") if isinstance(flow.get("verified"), dict) else {}
        count = int(v.get("count", 0)) + 1
        flow["verified"] = {"count": count, "last": datetime.date.today()}
        if flow.get("state") in ("observed", "reproduced") and not flow.get("lock"):
            flow["state"] = "stable" if count >= 3 else "reproduced" if count >= 2 else "observed"
        save_flow(flow)

    def _step(self, flow, step, i: int, scope: dict, st: dict):
        where = f"step {i}"
        v = step.verb
        if v == "end":
            return "end"
        if v == "if":
            if self._cond(step.cond, scope, st["done"], where):
                return self._step(flow, step.then, i, scope, st)
            return None
        if v == "confirm":
            if self.unattended or self.ask is None:
                raise _Pause(f"waiting for you to confirm: {step.text}", {"confirm": step.text})
            if not self.ask(step.text):
                raise _Pause("you declined the checkpoint", status="failed")
            return None
        if v == "read_table":
            path = self._path(step.arg, scope, where)
            _, rows = load_table(path)
            if step.cond is not None:
                rows = [r for r in rows if self._row_match(step.cond, r, scope, where)]
            scope[step.out.name] = Table(rows, str(path))
            return None
        if v == "write_table":
            path = self._path(step.arg, scope, where)
            backup = Path(st["run_dir"]) / "backup"
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup / f"step{i}-{path.name}")
            header, rows = load_table(path)
            value = self._text(step.value, scope, where=where)
            if step.column not in header:
                header.append(step.column)
            for r in rows:
                if self._row_match(step.cond, r, scope, where):
                    r[step.column] = value
            save_table(path, header, rows)
            return None
        if v == "wait_file":
            path = self._path(step.arg, scope, where)
            deadline = time.time() + step.count
            while not path.exists():
                if time.time() >= deadline:
                    raise _Pause(f"{path.name} did not appear within {step.count:g}s")
                self.sleep(0.5)
            return None
        if v == "call":
            return self._call(flow, step, i, scope, st)
        raise FlowError(f"{where}: unsupported verb {v}")

    def _call(self, flow, step, i: int, scope: dict, st: dict):
        where = f"step {i}"
        args = {}
        for name, val in step.args.items():
            if isinstance(val, Var) and isinstance(scope.get(val.name), Secret):
                args[name] = scope[val.name]
            else:
                args[name] = self._text(val, scope, where=where)
        auth = flow.get("authorize") or {}
        ex = Executor(self.kb, self.driver, confirm=None if self.unattended else self.confirm,
                      env_overrides=self.env_overrides, owner=f"flow:{flow['id']}")
        has_bang = bool(ex.expand(step.target).bang_steps())
        pre = self.preapproved
        if self.unattended and has_bang:
            if i not in (auth.get("unattended") or []):
                raise _Pause(f"{where} has ! steps but is not authorized for unattended running")
            files = {str(Path(self._expand(f, scope, "authorize.files")).resolve()) for f in auth.get("files") or []}
            people = {self._expand(r, scope, "authorize.recipients") for r in auth.get("recipients") or []}
            for name, val in args.items():
                if isinstance(val, Secret):
                    continue
                as_path = Path(val) if not Path(val).is_absolute() else Path(val)
                if (Path(scope["workdir"]) / as_path).is_file() or as_path.is_file():
                    real = str((as_path if as_path.is_absolute() else Path(scope["workdir"]) / as_path).resolve())
                    if real not in files:
                        raise _Pause(f"{where}: file argument {name!r} is not in authorize.files; stopping")
                elif name.lower() in RECIPIENT_PARAMS and val not in people:
                    raise _Pause(f"{where}: recipient argument {name!r} is not in authorize.recipients; stopping")
            pre = True
        res = ex.run(step.target, args, preapproved=pre, respect_busy=self.unattended)
        if res.ok:
            if step.out is not None:
                scope[step.out.name] = next(iter(res.outputs.values()))
            return None
        if res.status == "confirm_required":
            raise _Pause(f"{where} needs your confirmation for: " + "; ".join(res.bang_steps),
                         {"bang_steps": res.bang_steps}, status="confirm_required")
        detail = res.to_dict()
        detail["uncertain"] = bool((res.handoff or {}).get("uncertain") or (res.handoff or {}).get("completed_bang_steps"))
        if res.status == "busy":
            raise _Pause(f"{where}: the user is using this app", detail)
        raise _Pause(f"{where} ({step.target}) {res.status}: {res.message}. Fix or complete this step, then "
                     "`kb flow resume`.", detail)


def _ser(obj):
    if isinstance(obj, Table):
        return {"__table__": obj.rows, "path": obj.path}
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    return str(obj)


# --------------------------------------------------------------- approve / schedule

def approve(kb: KB, flow_id: str, platform: str) -> tuple[str, list[str]]:
    """Compute and store the lock hash. Call only on the user's explicit request."""
    flow = load_flow(find_flow_path(kb, flow_id))
    errs = check_flow(kb, flow)
    if errs:
        raise FlowError("flow check failed: " + "; ".join(errs[:5]))
    if flow.get("state") != "stable":
        raise FlowError(f"flow state is {flow.get('state')}; it must be stable (3 successful runs) before approval")
    bangs = flow_bang_steps(kb, flow, platform)
    missing = sorted(set(bangs) - set((flow.get("authorize") or {}).get("unattended") or []))
    if missing:
        raise FlowError(f"steps {missing} have ! steps; list them in authorize.unattended yourself first")
    flow["lock"] = lock_hash(kb, flow, platform)
    save_flow(flow)
    return flow["lock"], [d for n in sorted(bangs) for d in bangs[n]]


def scheduled_time(trigger: str, now: datetime.datetime) -> datetime.datetime | None:
    """Today's firing time of a schedule trigger, if it fires today."""
    m = _SCHEDULE.match(trigger)
    if not m:
        return None
    day = (m.group(1) or "daily").lower()
    wd = now.weekday()
    if day == "weekdays" and wd > 4:
        return None
    if day in DAYS and DAYS.index(day) != wd:
        return None
    hh, mm = int(m.group(2)), int(m.group(3))
    if hh > 23 or mm > 59:
        return None
    return now.replace(hour=hh, minute=mm, second=0, microsecond=0)


def due(flow: dict, now: datetime.datetime, last_started: float | None, root: Path) -> str | None:
    """The trigger that is due now, if any."""
    triggers = flow.get("trigger") or []
    for t in triggers if isinstance(triggers, list) else [triggers]:
        t = str(t)
        when = scheduled_time(t, now)
        if when is not None and when <= now and (last_started is None or last_started < when.timestamp()):
            return t
        if t.startswith("file_change"):
            spec = t.split(None, 1)[1]
            workdir = Path(str(flow.get("workdir", "")))
            workdir = workdir if workdir.is_absolute() else root / workdir
            p = Path(spec.replace("{workdir}", str(workdir)))
            if p.is_file() and (last_started is None or p.stat().st_mtime > last_started):
                return t
    return None


def tick(kb: KB, driver, *, secrets=None, now: datetime.datetime | None = None, env_overrides=None) -> list[FlowResult]:
    """Run every flow whose trigger is due, unattended. Call this from cron or
    Task Scheduler every few minutes."""
    now = now or datetime.datetime.now()
    out = []
    for path in kb.flow_files():
        try:
            flow = load_flow(path)
        except Exception:
            continue
        fid = flow.get("id", path.name)
        runner = FlowRunner(kb, driver, secrets=secrets, unattended=True, env_overrides=env_overrides)
        latest = runner._latest(fid)
        trig = due(flow, now, latest.get("started") if latest else None, kb.root)
        if not trig:
            continue
        if latest and latest.get("status") == "paused":
            runner._notify(f"{fid} is due but its last run is still paused; resume or fix it first")
            out.append(FlowResult("paused", fid, "previous run is still paused"))
            continue
        if driver.user_busy(None):
            mode = flow.get("when_busy", "wait")
            when = scheduled_time(trig, now)
            waited = (now - when).total_seconds() if when else 0
            if mode == "wait" and waited < MAX_BUSY_WAIT:
                out.append(FlowResult("deferred", fid, "you are using the computer; will retry on the next tick"))
                continue
            runner._notify(f"{fid} was {'skipped' if mode == 'skip' else 'not run'}: the computer was in use")
            d = runner._flow_dir(fid)
            d.mkdir(parents=True, exist_ok=True)
            (d / "latest.json").write_text(json.dumps({"flow": fid, "run_id": "", "run_dir": "", "status": "skipped",
                                                       "started": now.timestamp(), "trigger": trig}), encoding="utf-8")
            out.append(FlowResult("skipped", fid, "the computer was in use"))
            continue
        out.append(runner.run(fid, trigger=trig))
    return out


def list_flows(kb: KB) -> list[dict]:
    out = []
    for path in kb.flow_files():
        try:
            f = load_flow(path)
        except Exception as e:
            out.append({"file": path.name, "error": str(e)})
            continue
        out.append({"id": f.get("id"), "state": f.get("state"), "trigger": f.get("trigger"),
                    "approved": bool(f.get("lock")), "file": path.name})
    return out
