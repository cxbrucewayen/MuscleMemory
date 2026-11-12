"""Chinese aliases -> English canonical form (DESIGN appendix A).

The repository stores the English canonical form. The parser accepts the Chinese
aliases everywhere; every check runs *after* this conversion so that the two
spellings cannot be used to slip past a rule (SECURITY 3.1).
"""

from __future__ import annotations

import re

FIELDS = {
    "编号": "id", "适用": "applies", "说法": "aliases",
    "能力": "capabilities", "限制": "limits", "版本获取": "version_probe",
    "标识": "app_id", "首页": "home", "推荐手段": "preferred",
    "作用": "purpose", "所在": "parent", "定位": "locators",
    "参数": "params", "目标": "goal", "副作用": "side_effect",
    "输出": "output", "前置": "requires", "步骤": "steps",
    "判据": "check", "结束于": "ends_at", "症状": "symptom",
    "结论": "conclusion", "说明": "notes", "证据": "evidence",
    "反例": "counterexample", "状态": "state", "验证": "verified",
    "格式": "format", "触发": "trigger", "工作目录": "workdir",
    "输入": "inputs", "密钥": "secrets", "忙时": "when_busy",
    "授权": "authorize", "锁定": "lock", "经验": "lessons",
    "系统": "os", "软件": "app", "驱动": "driver",
    "语言": "lang", "显示": "display", "厂商系统": "rom",
    # sub-keys that the spec uses but appendix A leaves implicit
    "平台": "platform", "次数": "count", "最近": "last",
    "无人值守": "unattended", "文件": "files", "收件人": "recipients",
    "环境": "env",
}

VERBS = {
    "打开": "open", "前往": "goto", "点击": "click", "双击": "double_click",
    "右击": "right_click", "滚动": "scroll", "拖动": "drag", "按键": "key",
    "输入": "type", "写剪贴板": "clipboard", "移动窗口": "move_window",
    "等待": "wait", "读取": "read", "校验": "assert", "调用": "call",
    "若": "if", "结束": "end", "读表": "read_table", "写表": "write_table",
    "等待文件": "wait_file", "确认": "confirm",
}

# Keywords that may appear as bare tokens inside a step or condition.
STEP_KEYWORDS = {
    "可见": "visible", "不可见": "hidden", "出现": "shown", "消失": "gone",
    "文字": "text", "值": "value", "包含": "contains", "且": "and",
    "则": "then", "到": "to", "避开": "away_from", "上": "up", "下": "down",
    "焦点": "focus", "为空": "empty", "不为空": "not_empty", "行": "rows",
    "列": "column", "全部": "all", "筛选": "where", "设为": "set", "在": "in",
    "→": "->", "成功": "succeeded", "第": "step",
}

LOCATOR_METHODS = {"无障碍": "ax", "文字": "text", "坐标": "coord", "视觉": "vision"}
LOCATOR_ATTRS = {"角色": "role", "名称": "name", "取": "pick", "所在": "parent",
                 "值": "value", "编号": "id"}
LOCATOR_VALUES = {"第一": "first", "最后": "last", "本身": "self", "右侧": "right_of",
                  "左侧": "left_of", "上方": "above", "下方": "below"}

VALUES = {
    "观察": "observed", "复现": "reproduced", "稳定": "stable", "待复核": "recheck",
    "无": "none", "破坏": "destructive", "外部": "external",
    "手动": "manual", "等待": "wait", "跳过": "skip", "通知": "notify",
    "任意": "any", "未知": "unknown",
}
TRIGGER_WORDS = {"手动": "manual", "定时": "schedule", "文件变化": "file_change",
                 "每天": "daily"}
PROPOSAL_KINDS = {"更新": "update", "放宽": "widen", "变体": "variant", "新增": "new"}

# Reverse tables, used by `kb show --lang zh-CN`.
FIELDS_ZH = {}
for _zh, _en in FIELDS.items():
    FIELDS_ZH.setdefault(_en, _zh)
VERBS_ZH = {en: zh for zh, en in VERBS.items()}
VALUES_ZH = {en: zh for zh, en in VALUES.items()}


def tokenize(s: str) -> list[str]:
    """Split on whitespace, keeping "quoted strings" and {braces} intact.

    ``name="a b"`` and ``save_as={run_dir}/out.xlsx`` each stay one token.
    Raises ValueError on an unterminated quote or brace.
    """
    tokens, cur, i, n = [], [], 0, len(s)
    while i < n:
        c = s[i]
        if c == '"':
            j = i + 1
            while j < n and s[j] != '"':
                j += 2 if s[j] == "\\" else 1
            if j >= n:
                raise ValueError("unterminated quote")
            cur.append(s[i:j + 1])
            i = j + 1
        elif c == "{":
            j = s.find("}", i)
            if j < 0:
                raise ValueError("unterminated brace")
            cur.append(s[i:j + 1])
            i = j + 1
        elif c.isspace():
            if cur:
                tokens.append("".join(cur))
                cur = []
            i += 1
        else:
            cur.append(c)
            i += 1
    if cur:
        tokens.append("".join(cur))
    return tokens


def canon_step(s: str) -> str:
    """Canonicalise one step / condition string (verbs, keywords, whitespace)."""
    if not isinstance(s, str):
        return s
    try:
        toks = tokenize(s.strip())
    except ValueError:
        return s
    if not toks:
        return s
    out = []
    for idx, t in enumerate(toks):
        if idx == 0 or (idx > 0 and out[-1] == "then"):
            bang = t.endswith("!") or t.endswith("！")
            core = t[:-1] if bang else t
            if core in VERBS:
                out.append(VERBS[core] + ("!" if bang else ""))
                continue
            if bang and t.endswith("！"):
                out.append(core + "!")
                continue
        out.append(STEP_KEYWORDS.get(t, t))
    return " ".join(out)


def canon_locator(s: str) -> str:
    if not isinstance(s, str):
        return s
    try:
        toks = tokenize(s.strip())
    except ValueError:
        return s
    if not toks:
        return s
    method = LOCATOR_METHODS.get(toks[0], toks[0])
    if method == "vision":
        rest = s.strip()[len(toks[0]):].strip()
        return f"vision {rest}".rstrip()
    out = [method]
    for t in toks[1:]:
        if "=" in t and not t.startswith('"'):
            k, v = t.split("=", 1)
            k = LOCATOR_ATTRS.get(k, k)
            v = LOCATOR_VALUES.get(v, v)
            out.append(f"{k}={v}")
        else:
            out.append(LOCATOR_VALUES.get(t, t))
    return " ".join(out)


def _canon_trigger(s):
    if not isinstance(s, str):
        return s
    return " ".join(TRIGGER_WORDS.get(t, t) for t in s.split())


def _canon_applies_value(v):
    if not isinstance(v, str):
        return v
    return " ".join(VALUES.get(t, t) for t in v.split())


_STEP_LISTS = ("steps", "requires", "check")


def canon_doc(doc):
    """Return a deep copy of a card / flow / header / proposal in canonical English."""
    if not isinstance(doc, dict):
        return doc
    out = {}
    for k, v in doc.items():
        k = FIELDS.get(k, k) if isinstance(k, str) else k
        k = PROPOSAL_KINDS.get(k, k) if isinstance(k, str) else k
        if k in _STEP_LISTS and isinstance(v, list):
            v = [canon_step(x) for x in v]
        elif k == "locators" and isinstance(v, list):
            v = [canon_locator(x) for x in v]
        elif k in ("applies", "env") and isinstance(v, dict):
            v = {FIELDS.get(kk, kk): _canon_applies_value(vv) for kk, vv in v.items()}
        elif k in ("state", "side_effect", "when_busy") and isinstance(v, str):
            v = VALUES.get(v.strip(), v.strip())
        elif k == "trigger":
            v = [_canon_trigger(x) for x in v] if isinstance(v, list) else _canon_trigger(v)
        elif k in ("verified", "authorize") and isinstance(v, dict):
            v = {FIELDS.get(kk, kk): vv for kk, vv in v.items()}
        out[k] = v
    return out


def pick_lang(value, lang: str = "en"):
    """Pick a language from a ``{en: ..., zh: ...}`` field, falling back to any."""
    if isinstance(value, dict):
        short = (lang or "en").split("-")[0].lower()
        for key in (lang, short, "en", "zh"):
            if key in value:
                return value[key]
        return next(iter(value.values()), "")
    return value


def all_langs(value) -> list[str]:
    """Flatten a possibly-multilingual text / alias field into a list of strings."""
    if value is None:
        return []
    if isinstance(value, dict):
        out = []
        for v in value.values():
            out.extend(all_langs(v))
        return out
    if isinstance(value, (list, tuple)):
        out = []
        for v in value:
            out.extend(all_langs(v))
        return out
    return [str(value)]


_CJK = re.compile(r"[㐀-鿿]")


def has_cjk(s: str) -> bool:
    return bool(_CJK.search(s or ""))
