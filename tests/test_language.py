"""Version ranges, the step / condition / locator grammars, Chinese aliases, kb fmt."""

import pytest
import yaml

from musclememory.fmt import format_text
from musclememory.grammar import (
    GrammarError,
    parse_condition,
    parse_flow_condition,
    parse_flow_step,
    parse_locator,
    parse_step,
)
from musclememory.i18n import canon_doc, canon_locator, canon_step
from musclememory.versions import CLUE, MATCH, NO, Env, RangeError, match_applies, parse_applies, specificity


def applies(**kw):
    return parse_applies({"os": "WIN >=10.0", **kw})


def test_versions_compare_numerically():
    env = Env.parse({"os": "WIN 10.0.22631", "app": "WECHAT 4.10.0"})
    assert match_applies(applies(app="WECHAT >=4.9"), env)[0] == MATCH        # 4.10 > 4.9
    assert match_applies(applies(app="WECHAT >=4.0 <4.2"), env)[0] == CLUE
    assert match_applies(applies(app="WECHAT =4.10"), env)[0] == MATCH
    assert match_applies(applies(app="DINGTALK any"), env)[0] == NO
    assert match_applies(parse_applies({"os": "ANDROID >=12"}), env)[0] == NO


def test_unknown_version_and_language_are_only_clues():
    assert match_applies(applies(app="WECHAT >=4.0"), Env.parse({"os": "WIN 10.0", "app": "WECHAT unknown"}))[0] == CLUE
    zh = applies(app="WECHAT >=4.0", lang="zh-CN")
    assert match_applies(zh, Env.parse({"os": "WIN 10.0", "app": "WECHAT 4.1", "lang": "zh-CN"}))[0] == MATCH
    assert match_applies(zh, Env.parse({"os": "WIN 10.0", "app": "WECHAT 4.1", "lang": "en-US"}))[0] == CLUE


def test_specificity_prefers_narrow_ranges():
    assert specificity(applies(app="X >=4.2", lang="zh-CN")) > specificity(applies(app="X >=4.0"))
    assert specificity(applies(app="X =4.2.0")) > specificity(applies(app="X >=4.0 <4.3"))


@pytest.mark.parametrize("bad", [{"app": "X"}, {"os": "WIN 10"}, {"os": "DOS any"}, {"os": "WIN >=10", "zone": "x"}])
def test_bad_applies(bad):
    with pytest.raises(RangeError):
        parse_applies(bad if "os" in bad else {**bad})


@pytest.mark.parametrize("step", [
    "open APP.WIN.WECHAT",
    "click! ELEM.WIN.WECHAT.SEND",
    "scroll ELEM.WIN.WECHAT.LIST down 3",
    "drag ELEM.WIN.A.X to ELEM.WIN.A.Y",
    "key Ctrl+A",
    "type {remark}",
    "wait ELEM.WIN.A.X shown 5s",
    "read ELEM.WIN.A.X text -> {title}",
    "assert ELEM.WIN.A.X text == {remark} and ELEM.WIN.A.Y visible",
    "call RCP.COMMON.INPUT_TEXT text={remark} -> {out}",
    "if ELEM.WIN.A.X visible then click ELEM.WIN.A.X",
    "end",
])
def test_steps_accepted(step):
    assert parse_step(step).raw == step


@pytest.mark.parametrize("step", [
    'type "hello"',                                   # literals cannot be typed
    'clipboard "x"',
    'call RCP.WIN.A.B text="literal"',                # ... nor smuggled through a call
    "run calc.exe",                                   # no such verb
    "shell {cmd}",
    "open https://example.org",
    "click ELEM.WIN.A.X@4.2",                         # references never carry a version
    "click ЕLEM.WIN.A.X",                             # Cyrillic E homoglyph
    "if ELEM.WIN.A.X visible then if ELEM.WIN.A.Y visible then end",
    "if ELEM.WIN.A.X visible then call RCP.WIN.A.B",
    "wait! ELEM.WIN.A.X shown 5s",
    "assert ELEM.WIN.A.X visible or ELEM.WIN.A.Y visible",
    "goto RCP.WIN.A.B",
])
def test_steps_rejected(step):
    with pytest.raises((GrammarError, ValueError)):
        parse_step(step)


def test_conditions_and_locators():
    assert len(parse_condition('focus value == "x" and {v} contains {w}').atoms) == 2
    loc = parse_locator('ax role=Edit name="备注" parent=ELEM.WIN.A.CARD pick=last')
    assert loc.attrs["name"] == "备注" and loc.uses_ui_text
    assert not parse_locator("ax id=remark_row").uses_ui_text
    assert parse_locator('text "备注" right_of').position == "right_of"
    assert parse_locator("coord ELEM.WIN.A.CARD 50% 25%").x == 50
    assert parse_locator("vision the row next to the label").method == "vision"
    for bad in ("ax", "ax pick=first", "xpath //a", "coord ELEM.WIN.A.CARD 150% 2%", 'text "x" inside'):
        with pytest.raises(GrammarError):
            parse_locator(bad)


def test_flow_grammar_has_no_ui_verbs():
    parse_flow_step('read_table {tasks} where status == "done" and reported != "yes" -> {done}')
    parse_flow_step('write_table {tasks} rows task in {done.task} set reported = "yes"')
    parse_flow_step("call RCP.COMMON.A.B file={run_dir}/out.xlsx -> {out}")
    parse_flow_step("wait_file {run_dir}/out.xlsx 30s")
    parse_flow_step('confirm "Send it?"')
    parse_flow_condition('{tasks} rows task in {done.task} column reported all == "yes" and step 1 succeeded')
    for bad in ("{t} rows a == 1 column b all ==", "{t} rows a == 1 column b", "{t} rows", "step one succeeded"):
        with pytest.raises(GrammarError):
            parse_flow_condition(bad)
    for bad in ("click ELEM.WIN.A.X", "type {x}", "key Enter", "open APP.WIN.A", "if {x} empty then call RCP.WIN.A.B"):
        with pytest.raises(GrammarError):
            parse_flow_step(bad)


def test_chinese_aliases_are_equivalent():
    assert canon_step("点击! ELEM.WIN.A.SEND") == "click! ELEM.WIN.A.SEND"
    assert canon_step("若 ELEM.WIN.A.X 可见 则 点击 ELEM.WIN.A.X") == "if ELEM.WIN.A.X visible then click ELEM.WIN.A.X"
    assert canon_step("等待 ELEM.WIN.A.X 出现 5s") == "wait ELEM.WIN.A.X shown 5s"
    assert canon_step("读取 ELEM.WIN.A.X 文字 → {t}") == "read ELEM.WIN.A.X text -> {t}"
    assert canon_step('校验 ELEM.WIN.A.X 文字 包含 "值"') == 'assert ELEM.WIN.A.X text contains "值"'   # quoted text untouched
    assert canon_locator('无障碍 角色=Edit 名称="备注" 取=最后') == 'ax role=Edit name="备注" pick=last'
    assert canon_locator('文字 "备注" 右侧') == 'text "备注" right_of'
    doc = canon_doc({"编号": "ELEM.WIN.A.X", "适用": {"系统": "WIN >=10.0", "软件": "A 任意"}, "状态": "观察",
                     "步骤": ["输入 {x}"], "副作用": "外部"})
    assert doc == {"id": "ELEM.WIN.A.X", "applies": {"os": "WIN >=10.0", "app": "A any"}, "state": "observed",
                   "steps": ["type {x}"], "side_effect": "external"}


def test_fmt_is_canonical_and_stable():
    src = """
格式: 6
platform: WIN
app: A
---
状态: 稳定
验证: {last: 2026-11-12, count: 3}
步骤:
  - 点击 ELEM.WIN.A.X
  - 调用 RCP.COMMON.INPUT_TEXT text={remark}
参数: [remark]
目标: "{remark} is shown: yes # really"
编号: RCP.WIN.A.DO
说法: {zh: [做, 做一下], en: [do it]}
"""
    out = format_text(src)
    assert out == format_text(out)                                   # idempotent
    docs = list(yaml.safe_load_all(out))
    assert list(docs[1]) == ["id", "aliases", "params", "goal", "steps", "state", "verified"]
    assert docs[1]["steps"][0] == "click ELEM.WIN.A.X" and docs[1]["state"] == "stable"
    assert docs[1]["goal"] == "{remark} is shown: yes # really"       # quoting survived the round trip
    assert "aliases:\n  en: [do it]\n  zh: [做, 做一下]" in out
    assert "verified: {count: 3, last: 2026-11-12}" in out
