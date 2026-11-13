# Card and flow reference

The syntax you need to read cards, write proposals and draft flows. The full specification is `docs/en/DESIGN.md` in the project repository. Anything that is not listed here does not parse and is rejected.

## Ids

`TYPE.PLATFORM.APP.NAME[@variant]`, in ASCII upper case, digits and `_`.

| Type | Answers | Example |
|---|---|---|
| `ENV` | what this system offers, and its limits | `ENV.WIN` |
| `APP` | how to recognise and launch an app | `APP.WIN.WECHAT` |
| `ELEM` | where a screen or control is and how to locate it | `ELEM.WIN.WECHAT.REMARK_ROW` |
| `RCP` | how to do one thing and how to confirm it worked | `RCP.WIN.WECHAT.RENAME_REMARK` |
| `FAIL` | what causes a symptom and how to resolve it | `FAIL.WIN.WECHAT.CARD_BEHIND` |

- Platforms: `COMMON` `WIN` `MAC` `LINUX` `ANDROID` `IOS` `HARMONY`. Platform-level cards have no app segment (`RCP.WIN.INPUT_TEXT`).
- A `COMMON` recipe states the goal (`aliases`, `params`, `goal`, `side_effect`, `output`). The same-name platform recipe states the method (`requires`, `steps`, `check`, `ends_at`).
- `X@tag` is a variant of `X`: it inherits everything and writes only the fields that changed, plus its own `applies`.
- A reference never carries `@tag` or a version. The resolver picks the card.

## `applies`

```yaml
applies:
  os: WIN >=10.0.22000        # required: platform + range
  app: WECHAT >=4.0 <4.2      # required on app cards
  driver: cua-driver >=0.47   # optional
  lang: zh-CN                 # required when a locator depends on UI text
  display: DPI 100%           # optional
  rom: HyperOS >=1.0          # optional, Android-like platforms
```

Ranges: `any`, `=4.1.2`, `>=4.0`, `>=4.0 <4.2`. A new card lists only the version you verified, for example `=4.2.0`.

## Steps

One string per step: `verb object [arguments]`.

| Verb | Form |
|---|---|
| `open` | `open <APP id>` |
| `goto` | `goto <screen id>` |
| `click` `double_click` `right_click` | `click <element>` |
| `scroll` | `scroll <element> up|down <times>` |
| `drag` | `drag <element> to <element>` |
| `key` | `key <combo>` such as `Ctrl+A`, `Enter`, `Back` |
| `type` | `type {param}` (a parameter only, never fixed text) |
| `clipboard` | `clipboard {param}` |
| `move_window` | `move_window <element> away_from <element>` |
| `wait` | `wait <element> shown|gone <N>s` |
| `read` | `read <element> text|value -> {variable}` |
| `assert` | `assert <condition>` |
| `call` | `call <RCP id> name={param} … [-> {variable}]` (at most 3 levels deep) |
| `if` | `if <condition> then <single action>` (no nesting; the action cannot be `if` or `call`) |
| `end` | `end` (skip ahead to `check`) |

- `!` after the verb (`click!`, `key!`) marks a step with an external effect: send, submit, delete, pay, check in. A recipe with a `!` step cannot have `side_effect: none`.
- `side_effect` is `none`, `destructive` or `external`.
- At most 12 steps and 30 lines per card. Split longer recipes and chain them with `call`.

## Conditions

```
<element> visible | hidden
<element> text|value == | contains <value>
{variable} == | contains <value>
focus value == <value>
<condition> and <condition>          # there is no "or"
<value> := "literal" | {param}
```

`requires` must hold before the steps, `check` must hold after them, and `ends_at` names the screen the UI rests on.

## Locators

Tried in order, most stable first.

| Method | Form |
|---|---|
| `ax` | `ax [role=] [name=] [id=] [value=] [parent=<element>] [pick=first|last|N]` |
| `text` | `text "<text>" [self|right_of|left_of|above|below]` |
| `coord` | `coord <element> <x%> <y%>` (last resort) |
| `vision` | `vision <description>` (for you only; a program skips it) |

Prefer `id`. A card with a `text` locator, or an `ax` locator using `name=` or `value=`, must write `applies.lang`. An element without `parent` is a screen.

A recipe is a navigation recipe when it has `side_effect: none`, no `!`, no `params`, exactly one `<screen> visible` in `requires`, and an `ends_at`.

## Proposals

One YAML mapping: one of `update` / `widen` / `variant` / `new`, the `env` you ran in, then card fields. Never write `state` or `verified`.

```yaml
variant: ELEM.WIN.WECHAT.REMARK_ROW@4.2
env: {os: WIN 10.0.22631, app: WECHAT 4.2.0, driver: cua-driver 0.47.19, lang: zh-CN}
applies:
  os: WIN >=10.0
  app: WECHAT =4.2.0
  lang: zh-CN
locators:
  - ax role=Edit name="备注" parent=ELEM.WIN.WECHAT.PROFILE_CARD
  - text "备注" right_of
evidence: original locator 1 found no Button; Edit worked on first try
```

```yaml
new: FAIL.WIN.WECHAT.CARD_BEHIND
env: {os: WIN 10.0.22631, app: WECHAT 4.1.2, driver: cua-driver 0.47.19, lang: zh-CN}
applies:
  os: WIN >=10.0
  app: WECHAT =4.1.2
symptom:
  en: Clicks on the profile card have no effect; the card opened behind the main window
  zh: 点击资料卡没有反应；资料卡在主窗口后面打开
conclusion:
  en: The card overlaps the main window; moving it clear before clicking makes clicks land
  zh: 资料卡与主窗口重叠；点击前先把它移出主窗口范围，点击才会生效
evidence: seen twice; after move_window the same click worked
```

```yaml
update: RCP.WIN.WECHAT.RENAME_REMARK
env: {os: WIN 10.0.22631, app: WECHAT 4.1.2, driver: cua-driver 0.47.19, lang: zh-CN}
evidence: environment matched, all steps ran, check passed
```

Evidence describes structure: controls, error codes, symptoms. No names, chat text, document text, real paths or secrets; use `<CONTACT_A>`, `<USER_HOME>`, `<SECRET>`.

## Flows

A flow is local and personal. It has 7 verbs and never clicks or locates anything.

| Verb | Form |
|---|---|
| `call` | `call <RCP id> name=value … [-> {variable}]` |
| `read_table` | `read_table {file} [where <row condition>] -> {variable}` |
| `write_table` | `write_table {file} rows <row condition> set <column> = <value>` |
| `wait_file` | `wait_file {path} <N>s` |
| `confirm` | `confirm "<text shown to the user>"` |
| `if` | `if <condition> then <single action>` |
| `end` | `end` |

```
<column> == | != | contains <value>            # row condition
<column> in {table.column}                     # row condition
{variable} empty | not_empty
{variable} rows > | == | < <number>
{file} rows <row condition> column <column> all == <value>
step <N> succeeded
<condition> and <condition>
```

```yaml
format: 6
id: FLOW.WEEKLY_REPORT
aliases:
  en: [weekly report]
  zh: [周报]
trigger: [manual, schedule Fri 16:30]
workdir: <the user's folder>
inputs:
  tasks: "{workdir}/tasks.csv"
  boss: <display name of the recipient>
  password: "{secret:OA_PASSWORD}"
secrets: [OA_PASSWORD]
when_busy: wait
steps:
  - read_table {tasks} where status == "done" and reported != "yes" -> {done}
  - if {done} empty then end
  - call RCP.COMMON.EXCEL.BUILD_SUMMARY source={tasks} save_as={run_dir}/summary.xlsx -> {summary}
  - confirm "The summary is ready. Send it?"
  - call RCP.COMMON.WECHAT.SEND_FILE contact={boss} file={summary}
  - write_table {tasks} rows task in {done.task} set reported = "yes"
check:
  - "{tasks} rows task in {done.task} column reported all == \"yes\""
state: observed
verified: {count: 0, last: 2026-11-13}
```

- Built-in variables: `{workdir}`, `{run_dir}`, `{today}`. Files must be under `{workdir}` or `{run_dir}`.
- A secret is written `{secret:NAME}`, only as a whole value in `inputs`, and must be listed in `secrets`. It may only be passed to a recipe parameter that ends in `type` or `clipboard`.
- `trigger`: `manual`, `schedule [daily|weekdays|Mon…Sun] HH:MM`, `file_change {path}`.
- `authorize` (unattended step numbers, files, recipients) and `lock` are the user's to write and approve. Never write them yourself.

## Chinese spelling

Every field name, verb and keyword also has a Chinese alias (`步骤`, `点击!`, `可见`, `状态: 稳定`). Both spellings are equivalent and `kb fmt` converts to English. The table is in `REFERENCE.zh-CN.md` and in appendix A of the specification.
