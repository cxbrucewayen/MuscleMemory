"""`kb setup`: install the agent skill and register the MCP server in one step.

What it does, and nothing more:
  1. picks (or creates) a card library and records it in ~/.cua-experience/config.yaml
  2. copies the skill, in the chosen language, into the agent's skills folder
  3. registers `kb mcp` with the agent clients it finds

Every file it changes is listed in its output, existing JSON configs are backed
up next to themselves, and `kb setup --uninstall` reverses steps 2 and 3.
"""

from __future__ import annotations

import json
import locale
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from .cards import load_config, user_home

REPO_URL = "https://github.com/cxbrucewayen/MuscleMemory"
SKILL_NAME = "cua-experience"
SERVER_NAME = "musclememory"
CLIENTS = ("claude-code", "cursor", "claude-desktop")

MESSAGES = {
    "library": {"en": "card library: {0}", "zh": "经验库：{0}"},
    "library_cloned": {"en": "card library: cloned to {0}", "zh": "经验库：已克隆到 {0}"},
    "library_empty": {"en": "card library: created an empty one at {0} (could not clone {1}; "
                            "clone it there later to get the public cards)",
                      "zh": "经验库：已在 {0} 建立空库（无法克隆 {1}；之后把它克隆到这个目录即可获得公开卡片）"},
    "config": {"en": "settings: wrote {0}", "zh": "设置：已写入 {0}"},
    "skill": {"en": "skill: installed {0} ({1})", "zh": "技能：已安装到 {0}（{1}）"},
    "skill_removed": {"en": "skill: removed {0}", "zh": "技能：已删除 {0}"},
    "mcp_ok": {"en": "MCP: registered `{1}` with {0}", "zh": "MCP：已在 {0} 中注册 `{1}`"},
    "mcp_file": {"en": "MCP: registered `{1}` in {0}", "zh": "MCP：已写入 {0}（`{1}`）"},
    "mcp_removed": {"en": "MCP: removed `{1}` from {0}", "zh": "MCP：已从 {0} 移除 `{1}`"},
    "mcp_failed": {"en": "MCP: could not register with {0}: {1}", "zh": "MCP：在 {0} 中注册失败：{1}"},
    "mcp_bad_json": {"en": "MCP: {0} is not valid JSON; left untouched", "zh": "MCP：{0} 不是合法的 JSON，未改动"},
    "manual": {"en": "For any other MCP client, add this server to its configuration:",
               "zh": "其他支持 MCP 的客户端，把下面这段加进它的配置即可："},
    "manual_skill": {"en": "and give the agent the skill file: {0}", "zh": "再把这个技能文件交给智能体：{0}"},
    "none_found": {"en": "No supported agent client was detected (looked for: {0}).",
                   "zh": "没有检测到已支持的智能体客户端（查找了：{0}）。"},
    "driver_hint": {"en": "next: choose a driver, e.g. `kb setup --driver adb` or `--driver cua`; "
                          "try the demo with `kb --root {0}/examples/demo --driver sim:{0}/examples/demo/sim/windows-4.1.yaml find \"rename remark\"`",
                    "zh": "下一步：选一个驱动，例如 `kb setup --driver adb` 或 `--driver cua`；"
                          "想先试演示：`kb --root {0}/examples/demo --driver sim:{0}/examples/demo/sim/windows-4.1.yaml find 改备注`"},
    "restart": {"en": "Restart the agent client so it loads the new skill and MCP server.",
                "zh": "重启智能体客户端，让它加载新的技能和 MCP 服务。"},
    "dry": {"en": "(dry run: nothing was changed)", "zh": "（演练模式：没有做任何改动）"},
}


def detect_lang(explicit: str | None = None) -> str:
    """'zh-CN' for Chinese users, otherwise 'en'."""
    cand = explicit or load_config().get("lang") or os.environ.get("KB_LANG")
    if not cand:
        cand = os.environ.get("LC_ALL") or os.environ.get("LANG") or ""
        if not cand:
            try:
                cand = locale.getlocale()[0] or ""
            except (ValueError, TypeError):
                cand = ""
    return "zh-CN" if str(cand).lower().startswith(("zh", "chinese")) else "en"


def skill_files(lang: str) -> dict[str, Path]:
    """Installed name -> packaged source, for one language."""
    base = Path(__file__).resolve().parent / "skill"
    suffix = ".zh-CN.md" if lang.lower().startswith("zh") else ".md"
    return {"SKILL.md": base / f"SKILL{suffix}", "REFERENCE.md": base / f"REFERENCE{suffix}"}


def server_command(root: Path) -> list[str]:
    """How a client starts the MCP server. Uses this interpreter, so it does
    not depend on PATH. Driver and language come from config.yaml at start-up."""
    return [sys.executable, "-m", "musclememory.cli", "--root", str(root), "mcp"]


def claude_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def claude_desktop_config() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "Claude" / "claude_desktop_config.json"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def cursor_config() -> Path:
    return Path.home() / ".cursor" / "mcp.json"


def detect_clients() -> list[str]:
    found = []
    if shutil.which("claude") or claude_dir().is_dir():
        found.append("claude-code")
    if cursor_config().parent.is_dir():
        found.append("cursor")
    if claude_desktop_config().parent.is_dir():
        found.append("claude-desktop")
    return found


class Setup:
    def __init__(self, *, lang: str | None = None, root: str | Path | None = None, driver: str | None = None,
                 clients: list[str] | None = None, skills_dir: str | Path | None = None, clone: bool = True,
                 dry_run: bool = False, run=subprocess.run):
        self.lang = detect_lang(lang)
        self.explicit_lang = lang
        self.root = Path(root).expanduser() if root else None
        self.driver = driver
        self.clients = clients
        self.skills_dir = Path(skills_dir).expanduser() if skills_dir else None
        self.clone = clone
        self.dry = dry_run
        self.run = run
        self.lines: list[str] = []

    def say(self, key: str, *args):
        short = "zh" if self.lang.startswith("zh") else "en"
        self.lines.append(MESSAGES[key][short].format(*args))

    # --- 1. library ---------------------------------------------------------------
    def library(self) -> Path:
        if self.root is None:
            here = Path.cwd().resolve()
            self.root = next((p for p in (here, *here.parents) if (p / "cards").is_dir()), None)
        if self.root is not None:
            if not self.dry:
                (self.root / "cards").mkdir(parents=True, exist_ok=True)
            self.say("library", self.root)
            return self.root
        target = user_home() / "library"
        self.root = target
        if (target / "cards").is_dir():
            self.say("library", target)
            return target
        if self.dry:
            self.say("library", target)
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        cloned = False
        if self.clone and shutil.which("git") and not target.exists():
            try:
                p = self.run(["git", "clone", "--depth", "1", REPO_URL, str(target)],
                             capture_output=True, text=True, timeout=180)
                cloned = p.returncode == 0 and (target / "cards").is_dir()
            except (OSError, subprocess.TimeoutExpired):
                cloned = False
        if cloned:
            self.say("library_cloned", target)
        else:
            (target / "cards").mkdir(parents=True, exist_ok=True)
            self.say("library_empty", target, REPO_URL)
        return target

    def write_config(self):
        path = user_home() / "config.yaml"
        data = load_config()
        data["root"] = str(self.root)
        if self.driver:
            data["driver"] = self.driver
        if self.explicit_lang:
            data["lang"] = self.lang
        if not self.dry:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=True), encoding="utf-8")
        self.say("config", path)

    # --- 2. skill -----------------------------------------------------------------
    def skill_target(self) -> Path:
        return (self.skills_dir or claude_dir() / "skills") / SKILL_NAME

    def install_skill(self) -> Path:
        target = self.skill_target()
        if not self.dry:
            target.mkdir(parents=True, exist_ok=True)
            for name, src in skill_files(self.lang).items():
                shutil.copyfile(src, target / name)
        self.say("skill", target, "中文" if self.lang.startswith("zh") else "English")
        return target

    def remove_skill(self):
        target = self.skill_target()
        marker = target / "SKILL.md"
        if marker.is_file() and f"name: {SKILL_NAME}" in marker.read_text(encoding="utf-8")[:400]:
            if not self.dry:
                shutil.rmtree(target)
            self.say("skill_removed", target)

    # --- 3. MCP -------------------------------------------------------------------
    def _json_config(self, path: Path, label: str, remove: bool):
        data = {}
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8") or "{}")
            except ValueError:
                self.say("mcp_bad_json", path)
                return
            if not isinstance(data, dict):
                self.say("mcp_bad_json", path)
                return
        servers = data.setdefault("mcpServers", {})
        if remove:
            if SERVER_NAME not in servers:
                return
            del servers[SERVER_NAME]
        else:
            cmd = server_command(self.root)
            servers[SERVER_NAME] = {"command": cmd[0], "args": cmd[1:]}
        if not self.dry:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.is_file():
                shutil.copyfile(path, path.with_suffix(path.suffix + ".bak"))
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.say("mcp_removed" if remove else "mcp_file", path, SERVER_NAME)

    def _claude_code(self, remove: bool):
        exe = shutil.which("claude")
        add = ["claude", "mcp", "add", "--scope", "user", SERVER_NAME, "--", *server_command(self.root)]
        if not exe:
            if not remove:
                self.say("mcp_failed", "Claude Code", "`claude` is not on PATH; run: " + " ".join(add))
            return
        if self.dry:
            self.say("mcp_removed" if remove else "mcp_ok", "Claude Code", SERVER_NAME)
            return
        try:
            gone = self.run([exe, "mcp", "remove", "--scope", "user", SERVER_NAME], capture_output=True, text=True, timeout=60)
            if remove:
                if gone.returncode == 0:
                    self.say("mcp_removed", "Claude Code", SERVER_NAME)
                return
            p = self.run([exe, *add[1:]], capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as e:
            self.say("mcp_failed", "Claude Code", str(e))
            return
        if p.returncode == 0:
            self.say("mcp_ok", "Claude Code", SERVER_NAME)
        else:
            self.say("mcp_failed", "Claude Code", (p.stderr or p.stdout or "").strip()[:200])

    def register(self, remove: bool = False) -> list[str]:
        clients = self.clients if self.clients is not None else detect_clients()
        for c in clients:
            if c == "claude-code":
                self._claude_code(remove)
            elif c == "cursor":
                self._json_config(cursor_config(), "Cursor", remove)
            elif c == "claude-desktop":
                self._json_config(claude_desktop_config(), "Claude Desktop", remove)
        return clients

    def manual(self, skill_path: Path):
        cmd = server_command(self.root)
        snippet = {"mcpServers": {SERVER_NAME: {"command": cmd[0], "args": cmd[1:]}}}
        self.say("manual")
        self.lines.append(json.dumps(snippet, ensure_ascii=False, indent=2))
        self.say("manual_skill", skill_path / "SKILL.md")

    # --- entry points -------------------------------------------------------------
    def install(self) -> list[str]:
        root = self.library()
        self.write_config()
        skill = self.install_skill()
        clients = self.register()
        if not clients and self.clients is None:
            self.say("none_found", ", ".join(CLIENTS))
        self.manual(skill)
        if not (self.driver or load_config().get("driver")) and (root / "examples" / "demo").is_dir():
            self.say("driver_hint", root)
        self.say("restart")
        if self.dry:
            self.say("dry")
        return self.lines

    def uninstall(self) -> list[str]:
        if self.root is None:
            self.root = Path(load_config().get("root") or user_home() / "library")
        self.remove_skill()
        self.register(remove=True)
        if self.dry:
            self.say("dry")
        return self.lines
