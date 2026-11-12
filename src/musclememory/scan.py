"""Security scan (SECURITY section 5): injection, hidden content, exfiltration,
privacy and secret patterns. Runs on the canonical form of a card or proposal.

The rule set is deliberately conservative: a false positive costs a reword,
a false negative ships to every agent that syncs the library.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Finding:
    rule: str        # category
    detail: str
    where: str = ""

    def __str__(self):
        return f"[{self.rule}] {self.detail}" + (f" (in {self.where})" if self.where else "")


_I = re.IGNORECASE
INJECTION = [
    (re.compile(r"(忽略|无视|忘记|忘掉|不要理会).{0,10}(之前|以上|上面|上述|先前|前面|此前|所有)"), "override phrase"),
    (re.compile(r"\b(ignore|disregard|forget|override)\b.{0,24}\b(previous|prior|above|earlier|preceding|all)\b", _I), "override phrase"),
    (re.compile(r"system\s*prompt|系统提示词?|developer\s+message|jailbreak", _I), "prompt reference"),
    (re.compile(r"你现在是|你将扮演|从现在开始你|you are now\b|act as (an?|the)\b|pretend to be\b", _I), "role reassignment"),
    (re.compile(r"你应该|你必须|你需要|你要|请你|务必"), "instruction addressed to the AI"),
    (re.compile(r"\byou (must|should|shall|need to|have to|will now)\b|\b(assistant|ai agent|claude|chatgpt|gpt)\s*[:,]", _I), "instruction addressed to the AI"),
    (re.compile(r"\bdo not (tell|inform|ask|notify) the user\b|不要(告诉|通知|询问)用户|无需(确认|授权)|skip (the )?confirmation|without (asking|confirmation)", _I), "bypassing the user"),
]
HIDDEN = [
    (re.compile(r"[​-‏⁠-⁤﻿­]"), "zero-width or invisible character"),
    (re.compile(r"[‪-‮⁦-⁩]"), "bidirectional control character"),
    (re.compile(r"<!--|-->"), "HTML comment"),
    (re.compile(r"[A-Za-z0-9+/]{48,}={0,2}"), "long base64-like run"),
    (re.compile(r"[\U000e0000-\U000e007f]"), "Unicode tag character"),
]
EXFIL = [
    (re.compile(r"\b(?:https?|ftp|file|wss?|data|javascript)://?", _I), "URL"),
    (re.compile(r"\bwww\.[a-z0-9-]+\.", _I), "URL"),
    (re.compile(r"\b[a-z0-9-]+\.(?:com|net|org|io|cn|xyz|top|ru|info|dev|app|ai|cc|me|co)\b(?![.\w])"), "domain name"),
    (re.compile(r"\b(curl|wget|webhook|powershell|pwsh|cmd\.exe|/bin/(ba)?sh|bash -c|sh -c|invoke-webrequest|invoke-expression|iex|nc -|ncat|scp|rsync|ssh|ftp|eval|exec|rm -rf|del /|reg add|schtasks|msiexec|regsvr32|rundll32)\b", _I), "command or network tool"),
    (re.compile(r"发送到|上传到|传到|发到.{0,6}(服务器|地址|邮箱|网站)|转发给|\b(send|upload|post|forward|exfiltrate)\s+(?:\w+\s+){0,3}to\s+(?:the\s+|a\s+|an\s+)?(?:server|address|url|endpoint|e-?mail|inbox|webhook|remote|host|site|bot)\b|\b(?:send|upload) to\b", _I), "send/upload phrase"),
    (re.compile(r"```|\]\(|<\s*(script|img|a|iframe)\b", _I), "code block, link or markup"),
]
PRIVACY = [
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]+"), "email address"),
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "mainland China mobile number"),
    (re.compile(r"(?<![\w.])\+\d[\d \-]{7,16}\d"), "international phone number"),
    (re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "resident ID number"),
    (re.compile(r"(?<![\d.])\d{16,19}(?![\d.])"), "bank card number"),
    (re.compile(r"[A-Za-z]:\\+Users\\+[^\\\s<>]+|/(?:home|Users)/[^/\s<>]+|\\\\[A-Za-z0-9_.-]+\\[A-Za-z0-9$_.-]+", _I), "user directory path"),
    (re.compile(r"%(USERPROFILE|APPDATA|LOCALAPPDATA|HOMEPATH)%|~/", _I), "user directory path"),
]
SECRETS = [
    (re.compile(r"\{secret:", _I), "secret reference"),
    (re.compile(r"KB_SECRET_"), "secret variable name"),
    (re.compile(r"\b(pass(word|wd)?|pwd|token|secret|api[_-]?key|密码|口令|令牌)\s*[=:：]\s*(?![{\s])\S", _I), "inline credential"),
    (re.compile(r"\b(sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{30,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})"), "known token format"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key"),
]
_IPV4 = re.compile(r"(?<![\d.])(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?![\d.])")
_LONG_RUN = re.compile(r"[A-Za-z0-9+/=_-]{28,}")
_ID_LIKE = re.compile(r"^(?:[A-Z0-9_]+\.)+[A-Z0-9_@.\-]+$")
_SCRIPTS = ("LATIN", "CYRILLIC", "GREEK")

PLACEHOLDER_RULES = [
    (re.compile(r"[A-Za-z]:\\+Users\\+[^\\\s<>\"']+", _I), "<USER_HOME>"),
    (re.compile(r"/(?:home|Users)/[^/\s<>\"']+"), "<USER_HOME>"),
    (re.compile(r"%(USERPROFILE|HOMEPATH)%", _I), "<USER_HOME>"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]+"), "<EMAIL>"),
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "<PHONE>"),
    (re.compile(r"(?<![\w.])\+\d[\d \-]{7,16}\d"), "<PHONE>"),
]


def _entropy(s: str) -> float:
    n = len(s)
    counts = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    return -sum(c / n * math.log2(c / n) for c in counts.values())


def _mixed_script(text: str) -> str | None:
    """Find a word that mixes Latin with Cyrillic/Greek letters (homoglyph spoofing)."""
    for word in re.findall(r"[^\W\d_]+", text):
        scripts = set()
        for ch in word:
            name = unicodedata.name(ch, "")
            for s in _SCRIPTS:
                if name.startswith(s):
                    scripts.add(s)
        if "LATIN" in scripts and len(scripts) > 1:
            return word
    return None


def scan_text(text: str, where: str = "", *, skip: tuple[str, ...] = ()) -> list[Finding]:
    """Scan one string. `skip` lists categories the caller validates elsewhere."""
    out: list[Finding] = []
    if not isinstance(text, str) or not text:
        return out

    def run(category, rules):
        if category in skip:
            return
        for rx, label in rules:
            m = rx.search(text)
            if m:
                out.append(Finding(category, f"{label}: {m.group(0)[:40]!r}", where))

    run("injection", INJECTION)
    run("hidden", HIDDEN)
    run("exfil", EXFIL)
    run("privacy", PRIVACY)
    run("secret", SECRETS)
    if "hidden" not in skip:
        word = _mixed_script(text)
        if word:
            out.append(Finding("hidden", f"mixed-script word (possible homoglyph): {word!r}", where))
        if any(unicodedata.category(c) == "Cc" and c not in "\n\t" for c in text):
            out.append(Finding("hidden", "control character", where))
    if "exfil" not in skip:
        for m in _IPV4.finditer(text):
            if all(int(g) <= 255 for g in m.groups()):
                out.append(Finding("exfil", f"IP address: {m.group(0)!r}", where))
                break
    if "secret" not in skip:
        for m in _LONG_RUN.finditer(text):
            run_ = m.group(0)
            if not _ID_LIKE.match(run_) and _entropy(run_) >= 4.0:
                out.append(Finding("secret", f"high-entropy string: {run_[:12]!r}...", where))
                break
    return out


def _walk(node, path: str):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk(k, f"{path}.<key>") if not isinstance(k, str) or not k.isidentifier() else ()
            yield from _walk(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, (list, tuple)):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def scan_doc(doc: dict) -> list[Finding]:
    """Scan every string of a card / proposal / bundle."""
    out: list[Finding] = []
    for path, text in _walk(doc, ""):
        top = path.split(".")[0].split("[")[0]
        if top in ("id", "update", "widen", "variant", "new"):
            continue                    # ids are validated by their own strict grammar
        # Version numbers such as 10.0.22631.1 live in applies/env; skip the IP rule there.
        # app_id (package / bundle names look like domains) is validated by `kb check`.
        skip = ("exfil",) if top in ("applies", "env", "app_id") else ()
        out.extend(scan_text(text, path, skip=skip))
    return out


def redact_placeholders(text: str) -> str:
    """Gate 1: replace well-known personal formats with placeholders."""
    for rx, repl in PLACEHOLDER_RULES:
        text = rx.sub(repl, text)
    return text


def redact_doc(node):
    if isinstance(node, dict):
        return {k: redact_doc(v) for k, v in node.items()}
    if isinstance(node, list):
        return [redact_doc(v) for v in node]
    if isinstance(node, str):
        return redact_placeholders(node)
    return node
