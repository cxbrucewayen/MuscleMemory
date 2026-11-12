"""The `kb` command line (DESIGN section 9, interface table)."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

from . import FORMAT, __version__
from .cards import KB, find_root, load_config, load_yaml, parse_id
from .check import check_kb
from .drivers import DriverError, make_driver
from .executor import Executor
from .flows import FlowError, FlowRunner, approve, find_flow_path, flow_bang_steps, list_flows, load_flow, tick
from .fmt import dump_card, format_file
from .grammar import SECRET_RE
from .i18n import FIELDS_ZH, VALUES_ZH, VERBS_ZH
from .propose import ProposalError, merge, propose
from .resolve import resolve
from .search import (guess_app, index_text, kb_bundle, kb_outline, kb_resolve, kb_screen, kb_symptom,
                     localize)
from .secrets import SecretError, SecretStore
from .versions import Env


def _lang(args) -> str:
    return args.lang or load_config().get("lang") or os.environ.get("KB_LANG") or "en"


def _driver_spec(args) -> str | None:
    return args.driver or os.environ.get("KB_DRIVER") or load_config().get("driver")


def _env_overrides(args) -> dict:
    out = {}
    if args.env:
        p = Path(args.env)
        if p.is_file():
            data = load_yaml(p.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                sys.exit(f"{p}: an environment file is a YAML mapping")
            out.update({k: str(v) for k, v in data.items()})
        else:
            for pair in args.env.split(","):
                if "=" not in pair:
                    sys.exit("--env takes a YAML file or os='WIN 10.0',app='X 1.2',lang=en-US")
                k, v = pair.split("=", 1)
                out[k.strip()] = v.strip().strip("'\"")
    return out


class Ctx:
    def __init__(self, args):
        self.args = args
        self.root = Path(args.root) if args.root else find_root()
        self.kb = KB.load(self.root)
        self.lang = _lang(args)
        self.overrides = _env_overrides(args)
        self._driver = None

    @property
    def driver(self):
        if self._driver is None:
            try:
                self._driver = make_driver(_driver_spec(self.args))
            except DriverError as e:
                sys.exit(f"error: {e}")
        return self._driver

    def has_driver(self) -> bool:
        return bool(_driver_spec(self.args))

    def env(self, app: str | None = None) -> Env:
        if self.has_driver():
            ex = Executor(self.kb, self.driver, env_overrides=self.overrides, record=False)
            return ex.env_for(app or ex.foreground_app())     # the foreground app decides the scope
        return Env.parse(self.overrides)

    def executor(self, **kw) -> Executor:
        return Executor(self.kb, self.driver, env_overrides=self.overrides, confirm=tty_confirm, **kw)


def tty_confirm(desc: str) -> bool:
    """Ask the person at the terminal. Without a terminal the answer is no."""
    if not sys.stdin.isatty():
        print(f"! step needs confirmation but there is no terminal: {desc}", file=sys.stderr)
        return False
    ans = input(f"\n! This step has an external effect:\n  {desc}\n  Allow it? [y/N] ")
    return ans.strip().lower() in ("y", "yes", "是", "好")


def _app_of(ref: str) -> str | None:
    try:
        return parse_id(ref).app
    except ValueError:
        return None


def _print_result(d: dict) -> int:
    print(json.dumps(d, ensure_ascii=False, indent=1))
    return 0 if d.get("status") == "ok" else 2


# ----------------------------------------------------------------------- commands

def cmd_find(c: Ctx, a):
    task = " ".join(a.task)
    env = c.env()
    named = guess_app(c.kb, task, Env.parse({"os": env.raw.get("os", "")}))
    if c.has_driver() and named and named != env.app:
        env = c.env(named)                # the task names another app than the foreground one
    print(kb_bundle(c.kb, task, env, c.lang))


def cmd_symptom(c: Ctx, a):
    print(kb_symptom(c.kb, " ".join(a.error), c.env(), c.lang))


def cmd_screen(c: Ctx, a):
    print(kb_screen(c.kb, a.features, c.env(), c.lang))


def cmd_outline(c: Ctx, a):
    print(kb_outline(c.kb, c.env(), c.lang))


def cmd_resolve(c: Ctx, a):
    print(kb_resolve(c.kb, a.id, c.env(_app_of(a.id)), c.lang))


def cmd_env(c: Ctx, a):
    print(json.dumps(c.env(a.app.upper() if a.app else None).to_dict(), ensure_ascii=False, indent=1))


def cmd_show(c: Ctx, a):
    card = c.kb.get(a.id)
    if card is None:
        res = resolve(c.kb, a.id, c.env(_app_of(a.id)))
        if not res.ok:
            sys.exit(f"{a.id}: {res.reason}")
        data = res.data
    else:
        data = card.data
    text = dump_card(localize(data, c.lang))
    if c.lang.lower().startswith("zh"):
        lines = []
        for line in text.splitlines():
            stripped = line.lstrip()
            pad = line[:len(line) - len(stripped)]
            key, sep, rest = stripped.partition(":")
            if sep and key in FIELDS_ZH and not stripped.startswith("- "):
                rest_s = rest.strip()
                line = f"{pad}{FIELDS_ZH[key]}:{' ' + VALUES_ZH.get(rest_s, rest_s) if rest_s else ''}"
            elif stripped.startswith("- "):
                words = stripped[2:].split(" ")
                bang = words[0].endswith("!")
                verb = words[0].rstrip("!")
                if verb in VERBS_ZH:
                    words[0] = VERBS_ZH[verb] + ("!" if bang else "")
                    line = f"{pad}- {' '.join(words)}"
            lines.append(line)
        text = "\n".join(lines) + "\n"
    print(text, end="")


def cmd_check(c: Ctx, a):
    issues = check_kb(c.kb)
    for i in issues:
        print(i)
    n = len(c.kb.cards)
    if issues:
        print(f"\n{len(issues)} problem(s) in {n} card(s)", file=sys.stderr)
        return 1
    print(f"ok: {n} card(s), {len(c.kb.flow_files())} flow(s)")
    return 0


def _targets(c: Ctx, paths) -> list[Path]:
    if paths:
        return [Path(p) for p in paths]
    out = sorted(c.kb.cards_dir.rglob("*.yaml")) if c.kb.cards_dir.is_dir() else []
    return out + c.kb.flow_files()


def cmd_fmt(c: Ctx, a):
    changed = 0
    for p in _targets(c, a.paths):
        try:
            if format_file(p, check_only=a.check):
                changed += 1
                print(("would reformat " if a.check else "reformatted ") + str(p))
        except Exception as e:
            print(f"{p}: {e}", file=sys.stderr)
            return 1
    if a.check and changed:
        return 1
    if not changed:
        print("already formatted")
    return 0


def cmd_migrate(c: Ctx, a):
    old = [cf.path for cf in c.kb.files if cf.header.get("format") not in (None, FORMAT)]
    if not old:
        print(f"all files are format {FORMAT}; nothing to migrate")
        return 0
    for p in old:
        print(f"{p}: no migration is defined to format {FORMAT} yet", file=sys.stderr)
    return 1


def cmd_index(c: Ctx, a):
    path = c.root / "index" / "index.json"
    text = index_text(c.kb)
    if a.check:
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            print("index is stale; run `kb index`", file=sys.stderr)
            return 1
        print("index is up to date")
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {path.relative_to(c.root)}")
    return 0


def _params(c: Ctx, pairs) -> dict:
    store = SecretStore()
    out = {}
    for pair in pairs:
        if "=" not in pair:
            sys.exit(f"parameters are name=value, got {pair!r}")
        k, v = pair.split("=", 1)
        m = SECRET_RE.match(v)
        try:
            out[k] = store.handle(m.group(1)) if m else v
        except SecretError as e:
            sys.exit(f"error: {e}")
    return out


def cmd_run(c: Ctx, a):
    res = c.executor().run(a.id, _params(c, a.params), require_runnable=not a.force)
    return _print_result(res.to_dict())


def cmd_goto(c: Ctx, a):
    return _print_result(c.executor().goto(a.screen).to_dict())


def cmd_propose(c: Ctx, a):
    text = sys.stdin.read() if a.file in (None, "-") else Path(a.file).read_text(encoding="utf-8")
    try:
        path, info = propose(c.kb, text)
    except ProposalError as e:
        print("proposal rejected:", file=sys.stderr)
        for p in e.problems:
            print(f"- {p}", file=sys.stderr)
        return 1
    print(f"written {path.relative_to(c.root)} ({info['kind']} {info['id']})")
    if info["dropped_fields"]:
        print(f"dropped fields not in the schema: {info['dropped_fields']}")
    return 0


def cmd_merge(c: Ctx, a):
    try:
        print(merge(c.kb, Path(a.proposal)))
    except ProposalError as e:
        for p in e.problems:
            print(p, file=sys.stderr)
        return 1
    if not a.keep:
        Path(a.proposal).unlink()
    return 0


def cmd_secret(c: Ctx, a):
    store = SecretStore()
    try:
        if a.action == "set":
            if not a.name:
                sys.exit("usage: kb secret set NAME")
            store.check_name(a.name)
            value = getpass.getpass(f"value for {a.name} (hidden): ") if sys.stdin.isatty() else sys.stdin.readline().rstrip("\n")
            if not value:
                sys.exit("empty value; nothing stored")
            store.set(a.name, value)
            print(f"stored {a.name}")
        elif a.action == "list":
            for n in store.names():
                print(n)
        elif a.action == "rm":
            if not a.name:
                sys.exit("usage: kb secret rm NAME")
            print("removed" if store.remove(a.name) else "no such secret")
        elif a.action == "check":
            problems = store.check(c.root)
            for p in problems:
                print(p)
            if problems:
                return 1
            print(f"ok: {store.env_path}")
    except SecretError as e:
        sys.exit(f"error: {e}")
    return 0


def cmd_flow(c: Ctx, a):
    if a.action == "list":
        for f in list_flows(c.kb):
            print(json.dumps(f, ensure_ascii=False, default=str))
        return 0
    store = SecretStore()
    try:
        if a.action == "tick":
            results = tick(c.kb, c.driver, secrets=store, env_overrides=c.overrides)
            for r in results:
                print(json.dumps(r.to_dict(), ensure_ascii=False))
            return 0 if all(r.status in ("ok", "deferred", "skipped") for r in results) else 2
        if not a.flow:
            sys.exit(f"usage: kb flow {a.action} <FLOW.ID>")
        if a.action == "approve":
            if not sys.stdin.isatty():
                sys.exit("approval must be given by a person at a terminal")
            flow = load_flow(find_flow_path(c.kb, a.flow))
            bangs = flow_bang_steps(c.kb, flow, c.driver.platform())
            auth = flow.get("authorize") or {}
            print(f"Flow {flow.get('id')} will be allowed to run without you. It may then perform:")
            for n in sorted(bangs):
                for d in bangs[n]:
                    print(f"  step {n}: {d}")
            print(f"  files it may send out: {auth.get('files') or []}")
            print(f"  recipients: {auth.get('recipients') or []}")
            if input("Approve exactly this version? [y/N] ").strip().lower() not in ("y", "yes", "是"):
                print("not approved")
                return 1
            lock, _ = approve(c.kb, a.flow, c.driver.platform())
            print(f"approved: {lock}")
            return 0
        runner = FlowRunner(c.kb, c.driver, secrets=store, confirm=tty_confirm, ask=tty_confirm,
                            unattended=a.unattended, env_overrides=c.overrides)
        if a.action == "run":
            res = runner.run(a.flow)
        else:
            res = runner.resume(a.flow, step_done=a.step_done, redo=a.redo)
        return _print_result(res.to_dict())
    except FlowError as e:
        sys.exit(f"error: {e}")


def cmd_mcp(c: Ctx, a):
    from .mcp_server import Server
    driver = c.driver if c.has_driver() else None
    Server(c.root, driver, lang=c.lang, env_overrides=c.overrides).serve()
    return 0


# -------------------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kb", description="MuscleMemory: experience cards for computer-use agents.")
    p.add_argument("--version", action="version", version=f"kb {__version__} (format {FORMAT})")
    p.add_argument("--root", help="library root (default: $KB_ROOT or the nearest folder containing cards/)")
    p.add_argument("--env", help="environment snapshot: a YAML file or os='WIN 10.0.22631',app='X 4.1',lang=en-US")
    p.add_argument("--driver", help="sim:<file.yaml> | adb[:serial] | cua (default: $KB_DRIVER or config.yaml)")
    p.add_argument("--lang", help="display language, e.g. en or zh-CN")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        sp = sub.add_parser(name, help=help_)
        sp.set_defaults(fn=fn)
        return sp

    add("find", cmd_find, "experience bundle for a task (kb_bundle)").add_argument("task", nargs="+")
    add("symptom", cmd_symptom, "look up a pitfall by error or symptom").add_argument("error", nargs="+")
    add("screen", cmd_screen, "identify a screen from its features").add_argument("features", nargs="+")
    add("outline", cmd_outline, "one line per card in scope")
    add("resolve", cmd_resolve, "the card that applies to an id in this environment").add_argument("id")
    add("env", cmd_env, "print the detected environment snapshot").add_argument("app", nargs="?")
    add("show", cmd_show, "print a card (use --lang zh-CN for Chinese keys)").add_argument("id")
    add("check", cmd_check, "validate the whole library")
    sp = add("fmt", cmd_fmt, "rewrite files in canonical form")
    sp.add_argument("--check", action="store_true")
    sp.add_argument("paths", nargs="*")
    add("migrate", cmd_migrate, "upgrade files from older format versions")
    add("index", cmd_index, "regenerate index/index.json").add_argument("--check", action="store_true")
    sp = add("run", cmd_run, "run a recipe with the deterministic executor")
    sp.add_argument("id")
    sp.add_argument("params", nargs="*", help="name=value (use {secret:NAME} for secrets)")
    sp.add_argument("--force", action="store_true", help="run even if not 'directly runnable' (trial runs)")
    add("goto", cmd_goto, "navigate to a screen").add_argument("screen")
    add("propose", cmd_propose, "submit a proposal (file or stdin)").add_argument("file", nargs="?")
    sp = add("merge", cmd_merge, "maintainers: apply a reviewed proposal to cards/")
    sp.add_argument("proposal")
    sp.add_argument("--keep", action="store_true", help="keep the proposal file")
    sp = add("secret", cmd_secret, "manage secrets (set | list | rm | check)")
    sp.add_argument("action", choices=["set", "list", "rm", "check"])
    sp.add_argument("name", nargs="?")
    sp = add("flow", cmd_flow, "flows: run | resume | approve | list | tick")
    sp.add_argument("action", choices=["run", "resume", "approve", "list", "tick"])
    sp.add_argument("flow", nargs="?")
    sp.add_argument("--unattended", action="store_true")
    sp.add_argument("--step-done", action="store_true", help="resume: the paused step was completed by hand/AI")
    sp.add_argument("--redo", action="store_true", help="resume: redo a step whose ! outcome was verified as not done")
    add("mcp", cmd_mcp, "serve the MCP tools over stdio")
    return p


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
        return int(args.fn(Ctx(args), args) or 0)
    except DriverError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
