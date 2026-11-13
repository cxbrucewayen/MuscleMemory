# CUA experience system · Design (v6)

**English** | [简体中文](../zh-CN/DESIGN.md)

> The English and Chinese versions are maintained together. For what the current code implements and where it deviates, see [Implementation status](./STATUS.md).

> Write what each computer-use session taught you as short cards. One set of cards has to work across systems, apps and versions; an AI has to find it quickly and a program has to be able to run it; it serves a global audience and fully supports China.
>
> - **Part 1 (sections 0–18), cards**: how to do one thing inside one app.
> - **Part 2 (section 19), flows**: chaining several apps to finish one errand of my own.
> - **Appendix A**: the Chinese–English table. The canonical form is English; the Chinese aliases are equally valid.

---

## 0. The whole picture

```
                 ┌──────────────── retrieval (section 9) ─────────────────┐
 cards/ ───────► │ scope by environment → enter by task/error/screen → bundle │
                 └───────────────────────┬────────────────────────────────┘
                                         ▼
                 directly runnable? ──yes──► kb_run executes ──fails──┐
                        │no                                            ▼
                        └────────────────────────────────► the AI executes (repairs, explores)
                                                                       │
                                               kb_propose ◄────────────┘
                                                  │ review, independent reproduction
                                                  ▼
                                               cards/
```

**One piece of experience, two ways to execute it**: an AI can read it and a program can run it. Normally the program runs it; when something breaks the AI repairs it and hands it back.

**Two layers**

```
flows/  flows (local, personal)   one errand of mine: app A → data or file → app B → app C
   │ call
   ▼
cards/  cards (publishable)       how to do one thing inside one app
```

---

## 1. Three principles

1. **The current screen is the authority; experience is a reference.** Priority: the user's instruction > the current screen > an experience card.
2. **Store methods, not handles.** A PID, window id, element token or absolute coordinate belongs to one run. A card only says how to find the thing again next time.
3. **No criterion, no experience.** "The click returned success" does not mean it worked. Every recipe needs a criterion a program can check.

---

## 2. Three dimensions: system × app × version

| Dimension | Where it lives | How it is reused |
|---|---|---|
| System | the directory (`windows/`, `android/` …) | **same-name cards**: the common card states the goal, each platform card the method |
| App | the file (`wechat.yaml`) | one file per app |
| Version | the `applies` range on the card | **@ variants**: only the fields that changed |

**A reference never names a version.** The resolver picks the card that best matches the current environment (section 8).

---

## 3. Five card types and their fields

| Type | Answers |
|---|---|
| `ENV` environment | What means does this system offer, and what are its limits? |
| `APP` application | How to recognise and launch this app, and how should it be driven? |
| `ELEM` element | Where is this screen or control, and how is it located? |
| `RCP` recipe | How is this done, and how do we confirm it worked? |
| `FAIL` pitfall | What causes this symptom, and how is it resolved? |

**Fields** (R = required, O = optional, I = inherited from the common or base card)

| Field | Chinese | ENV | APP | ELEM | RCP common | RCP platform | FAIL | Meaning |
|---|---|---|---|---|---|---|---|---|
| `id` | 编号 | R | R | R | R | R | R | see section 4 |
| `applies` | 适用 | R | R | R | R | R | R | version range, section 5 |
| `aliases` | 说法 | | R | | R | I/O | | names used for retrieval, grouped by language |
| `capabilities` `limits` `version_probe` | 能力 限制 版本获取 | R | | | | | | what the system offers, its limits, how to read versions |
| `app_id` | 标识 | | R | | | | | package name, bundle id or executable name; `open` launches it |
| `home` | 首页 | | R | | | | | the ELEM id of the main screen; navigation restarts from here |
| `preferred` | 推荐手段 | | O | | | | | |
| `purpose` | 作用 | | | R | | | | one sentence saying what it is; the AI heals by it when locators fail |
| `parent` | 所在 | | | O | | | | id of the parent screen; without it, the element is itself a screen |
| `locators` | 定位 | | | R | | | | candidate ways to locate it, section 10 |
| `params` | 参数 | | | | O | I | | parameter names, e.g. `[contact, remark]` |
| `goal` | 目标 | | | | R | I | | the success standard in one sentence; a platform card cannot change it |
| `side_effect` | 副作用 | | | | R | I (only up) | | `none` / `destructive` / `external` |
| `output` | 输出 | | | | O | I | | variables the recipe produces, e.g. `[summary]`; the platform card must give them a value |
| `requires` `steps` `check` `ends_at` | 前置 步骤 判据 结束于 | | | | | R (`requires` O) | | section 6 |
| `symptom` `conclusion` | 症状 结论 | | | | | | R | |
| `notes` | 说明 | O | O | O | O | O | O | for people and the AI only; programs do not read it |
| `evidence` `counterexample` `state` `verified` | 证据 反例 状态 验证 | R | R | R | | R | R | section 16 |

- A platform recipe without a same-name common card writes its own `aliases`, `params`, `goal` and `side_effect`.
- A card is at most 30 lines of YAML and `steps` at most 12; beyond that, split it into small recipes chained with `call`.
- References are library ids only; no links, code blocks or commands in a card.
- Evidence describes structure, not content. Names, chats and paths are always placeholders such as `<CONTACT_A>` and `<USER_HOME>`.

---

## 4. File format, directories, naming

### 4.1 File format

**A card file is standard YAML.** One file may hold several cards separated by `---`; the first document is the file header:

```yaml
format: 6          # format version, required
platform: WIN
app: WECHAT        # platform-level files write _platform
---
id: ELEM.WIN.WECHAT.REMARK_ROW
applies:
  os: WIN >=10.0
  ...
---
id: RCP.WIN.WECHAT.RENAME_REMARK
...
```

- **YAML for structure, strings for rules.** Steps, conditions, locators and version ranges are strings parsed by their own small grammars (sections 5, 6, 10). A parser needs one YAML library and a few simple grammars.
- **YAML pitfalls**: a value that starts with `{`, or contains `: ` or ` #`, must be quoted. `kb fmt` adds the quotes.
- **Format version**: `format` is required. The parser rejects unknown versions; `kb migrate` converts old files in bulk.
- **Canonical form**: `kb fmt` normalises key names (English), key order, indentation and quotes. It runs before submission to keep diffs clean.

### 4.2 Directories

```
cua-experience/                    # the repository
├── README.md  DESIGN.md  SKILL.md  SECURITY.md
├── cards/
│   ├── common/
│   │   ├── _common.yaml           # cross-system: common goals (input text …), common pitfalls
│   │   └── wechat.yaml            # goals WeChat shares across systems
│   ├── windows/
│   │   ├── _platform.yaml         # ENV cards, system- and driver-level pitfalls
│   │   └── wechat.yaml            # APP, ELEM, RCP, FAIL, with version variants
│   ├── android/
│   └── harmony/
├── index/                         # generated retrieval index; do not edit
├── proposals/                     # pending proposals (also the quarantine); neither the AI nor the executor reads it
├── flows/                         # local flows; .gitignore
└── runs/                          # local run records, screenshots, locks, statistics; .gitignore

~/.cua-experience/                 # the user directory, outside the repository
├── config.yaml                    # local settings: language, secret backend, busy rule, notification
└── .env                           # secrets (section 13)
```

### 4.3 Naming

**The id is the location**: `TYPE.PLATFORM.APP.NAME[@variant tag]`; platform-level cards omit the app segment.

| File | Example ids |
|---|---|
| `common/_common.yaml` | `RCP.COMMON.INPUT_TEXT` |
| `common/wechat.yaml` | `RCP.COMMON.WECHAT.RENAME_REMARK` |
| `windows/_platform.yaml` | `ENV.WIN`, `FAIL.WIN.UIPI_LOW_IL` |
| `windows/wechat.yaml` | `APP.WIN.WECHAT`, `ELEM.WIN.WECHAT.REMARK_ROW@4.2` |

- Platform codes: `COMMON` `WIN` `MAC` `LINUX` `ANDROID` `IOS` `HARMONY`.
- Ids use ASCII upper-case letters, digits and `_` only; what follows `@` is the variant tag. This prevents homoglyph spoofing (see SECURITY).
- A file over 400 lines is split by screen (for example `wechat.profile.yaml`); the id rules do not change.

---

## 5. `applies`: version ranges

```yaml
applies:
  os: WIN >=10.0.22000            # required: platform code + range
  app: WECHAT >=4.0 <4.2          # required on app cards: app segment + range
  driver: cua-driver >=0.47       # optional
  lang: zh-CN                     # optional; required on cards that depend on UI text
  display: DPI 100%               # optional
  rom: HyperOS >=1.0              # optional; Android-like platforms only
```

| Spelling | Meaning |
|---|---|
| `any` | any version, e.g. `os: any`, `app: WECHAT any` |
| `=4.1.2` | exactly this version |
| `>=4.0` | 4.0 and above |
| `>=4.0 <4.2` | from 4.0 (inclusive) to 4.2 (exclusive) |

- Versions compare numerically per segment; 4.10 is greater than 4.9.
- An optional item that is not written means no restriction.
- **Start narrow, widen with evidence.** A new card lists only the version it was verified on and is widened after it also succeeds elsewhere.

---

## 6. Step grammar (readable by AI, runnable by programs)

`steps` is a list of strings; item n is step n. Each step is **`verb object [arguments]`**. The grammar itself is the whitelist: anything outside it is rejected.

**Verbs** (Chinese aliases in appendix A)

| Verb | Form | Notes |
|---|---|---|
| `open` | `open <APP id>` | launch by the APP card's `app_id`, or bring to the foreground |
| `goto` | `goto <screen id>` | walk the navigation graph to that screen (section 11) |
| `click` `double_click` `right_click` | `click <element>` | |
| `scroll` | `scroll <element> up|down <times>` | |
| `drag` | `drag <element> to <element>` | |
| `key` | `key <combo>` | e.g. `Ctrl+A`, `Enter`, `Back` |
| `type` | `type {param}` | types into the focus; **parameters only, never fixed text** |
| `clipboard` | `clipboard {param}` | writes the clipboard; same rule |
| `move_window` | `move_window <element> away_from <element>` | moves the first window clear of the second |
| `wait` | `wait <element> shown|gone <N>s` | a timeout is a failure |
| `read` | `read <element> text|value -> {variable}` | stores the result in a variable |
| `assert` | `assert <condition>` | fails when the condition does not hold |
| `call` | `call <RCP id> name=value … [-> {variable}]` | `->` receives the callee's `output`; at most 3 levels, no cycles |
| `if` | `if <condition> then <single action>` | no nesting; the action cannot be `if` or `call` |
| `end` | `end` | jump ahead to the criteria |

**The `!` mark**: `!` after the verb (`click!`, `key!`) says the step has an external effect or cannot be undone: sending, submitting, deleting, paying, checking in. It is a confirmation point at run time. A recipe with a `!` step cannot have `side_effect: none`.

**Conditions**

```
<element> visible | <element> hidden
<element> text|value == | contains <value>
{variable} == | contains <value>
focus value == <value>               # focus is the element that currently has focus
<condition> and <condition>          # only and, no or
<value> := "literal" | {param} | {variable}
```

**Pre-conditions, criteria, end state**

- `requires`: a list of conditions that must all hold before execution. If a "screen visible" condition does not hold, the executor first runs `goto` (section 11). Requirements that cannot be written as conditions go into `notes`.
- `check`: a list of conditions that must all hold afterwards for the run to count as success.
- `ends_at`: a screen id saying where the UI rests when done.

**Design trade-off**: execution is sequential, with no jumps and no loops, so it always terminates. Retrying is the executor's job, not the card's.

---

## 7. Reuse: four mechanisms

| Case | Mechanism | Example |
|---|---|---|
| Same action, different data each time | parameters | `{contact}` `{remark}` |
| One action used by other recipes | call | `call RCP.WIN.WECHAT.OPEN_PROFILE contact={contact}` |
| Same goal, another system | same-name cards | `RCP.COMMON.WECHAT.RENAME_REMARK` → `RCP.WIN.WECHAT.RENAME_REMARK` |
| Same card, another version | @ variant | `ELEM.WIN.WECHAT.REMARK_ROW` → `…REMARK_ROW@4.2` |

- **Same-name cards**: the common card has `aliases`, `params`, `goal`, `side_effect`, `output`; the platform card replaces `COMMON` in the id with the platform code and has `requires`, `steps`, `check`, `ends_at`. The platform card inherits the common fields and **cannot change `params` or `goal`**; `side_effect` can only go up. The platform card's `check` must express the common `goal`, which reviewers compare.
- **@ variants**: `X@tag` inherits every field of `X` and writes only what changed; it must write its own `applies`. Fields are replaced whole: writing `locators` replaces the entire list.
- **call**: cross-system recipes call `COMMON` ids; within one platform a platform id may be called directly. A sequence of steps that appears in two or more recipes is extracted into a small recipe.

---

## 8. Resolution: picking the one card to use

**Input**: the referenced id and the environment snapshot (system and version, app and version, driver, language, display, vendor ROM).

```
1. Swap platform   a COMMON id becomes the same-name id of the current platform; none → no method
2. Collect         the id itself plus all of its @ variants
3. Filter          keep cards whose applies fully contains the environment → "match"
4. Sort            more specific first (narrower range, more conditions) → higher state → more recently verified
5. Fall back       nothing left → take the closest version and mark it a "clue"
6. Merge           the variant overrides the base, the platform card inherits the common card → the final card
```

A version that cannot be read is written `unknown` in the snapshot, and every result is marked a "clue".

---

## 9. Retrieval: how the AI finds experience quickly

**Step 1: scope by environment (no searching needed)**

Only four files matter: `common/_common.yaml`, `common/<app>.yaml`, `<platform>/_platform.yaml`, `<platform>/<app>.yaml`. Everything else is excluded. The current app is the foreground app; if the task names an app, it is matched through the APP cards' `aliases`.

**Step 2: enter from what you have**

| What the AI has | Interface | Field matched |
|---|---|---|
| A task description | `kb_bundle(task, env)` | local flows' `aliases` first; then RCP `aliases` and names |
| An error or odd behaviour | `kb_symptom(error, env)` | FAIL `symptom`; error codes match exactly |
| Features of the current screen | `kb_screen(features, env)` | the `locators` of screen elements; returns the screen and the elements under it |
| Nothing certain | `kb_outline(env)` | every card in scope, one line each |

- **Matching order**: exact → alias → full text. Aliases in every language take part, so a Chinese question finds an English card and vice versa.
- When the top two scores are close, both are returned and the AI chooses.
- Semantic retrieval is added only when there are hundreds of cards and keywords stop being precise; the interface does not change.

**Step 3: return a bundle**

After `kb_bundle` finds a recipe it expands its `call`s, the elements its steps reference and the pitfalls its `notes` reference, resolves each, and returns:

```
bundle: rename WeChat remark
env: WIN 10.0.22631 / WECHAT 4.2.0 / cua-driver 0.47.19 / zh-CN
directly runnable: no (REMARK_ROW@4.2 is observed)
├─ RCP.WIN.WECHAT.RENAME_REMARK          match stable
├─ RCP.WIN.WECHAT.OPEN_PROFILE           match stable (called)
├─ RCP.WIN.INPUT_TEXT                    match stable (the Windows method of a common goal)
├─ ELEM.WIN.WECHAT.REMARK_ROW@4.2        match observed (4.2 variant selected)
├─ FAIL.WIN.UIPI_LOW_IL                  match stable (referenced in notes)
└─ FAIL.WIN.WECHAT.CARD_BEHIND           match stable (referenced in notes)
```

- Every card is wrapped as `<card id="…" match="…" state="…">…</card>`, with content shown in the user's language (section 14).
- **The size limit is about 2000 tokens.** Beyond it, the recipe and the cards it references directly are given in full and deeper ones as one-line summaries the AI can fetch individually.
- **A one-line summary** is `id｜summary｜state｜match/clue`, the summary being the first field present among `aliases`, `purpose`, `symptom`, `conclusion`.
- `index/` is generated: an inverted index of `aliases`, `symptom` and screen locator features, rebuilt whenever cards change.

**Interfaces**: the same functions are offered as MCP tools and on the command line.

| MCP tool | Command line |
|---|---|
| `kb_bundle` `kb_symptom` `kb_screen` `kb_outline` | `kb find` `kb symptom` `kb screen` `kb outline` |
| `kb_resolve(id, env)` | `kb resolve` |
| `kb_goto(screen, env)` | `kb goto` |
| `kb_run(id, params, env)` | `kb run` |
| `kb_lock(app, env)` / `kb_unlock` | — |
| `kb_type_secret(name)` | — |
| `kb_propose(text)` | `kb propose` |
| `kb_flow(flow, action)` | `kb flow run / resume / approve / list` |
| — | `kb check` `kb fmt` `kb migrate` `kb index` `kb secret …` `kb show --lang` |

---

## 10. Locating elements

```yaml
id: ELEM.WIN.WECHAT.REMARK_ROW
purpose:
  en: The row in the profile card that shows and edits the remark
  zh: 资料卡里显示和修改备注的那一行
parent: ELEM.WIN.WECHAT.PROFILE_CARD
locators:
  - ax role=Button parent=ELEM.WIN.WECHAT.PROFILE_CARD pick=last
  - text "备注" right_of
  - vision 资料卡中部、与"备注"同一行的可点击文字
```

**Candidate forms**

| Method | Form | Usable by |
|---|---|---|
| `ax` accessibility | `ax [role=] [name=] [id=] [value=] [parent=<element>] [pick=first|last|N]` | programs, AI |
| `text` | `text "<text>" [self|right_of|left_of|above|below]` | programs, AI |
| `coord` | `coord <element> <x%> <y%>` (percentage position relative to an element) | programs, AI; last resort |
| `vision` | `vision <description>` | AI or a vision model only |

**How `ax` attributes map per platform**

| Library | Windows UIA | macOS AX | Android | iOS XCUITest | HarmonyOS |
|---|---|---|---|---|---|
| role | ControlType | Role | class | elementType | type |
| name | Name | Title / Description | text / content-desc | label | text |
| id | AutomationId | Identifier | resource-id | identifier | id |
| value | Value | Value | text | value | text |

- **Try candidates in order** and note which one worked; they are ordered from most to least stable.
- **Prefer the language-independent `id`.** A card with candidates that contain UI text (`text`, or `ax` with `name=`) must write `applies.lang`.
- **When all fail, heal by `purpose`**: the AI searches the current screen by that sentence and proposes a new @ variant.
- **A screen element** is an ELEM without `parent`; if its `locators` find something, we are on that screen.

---

## 11. Navigation between screens

A recipe's `requires` often says "be on this screen". Navigation gets there from wherever the UI is, so recipes do not need a pile of "go home, then click here" steps.

**The navigation graph needs no new fields**

- **Nodes**: screen elements (ELEM without `parent`).
- **Edges**: a recipe that satisfies all four conditions is recognised as a navigation recipe:
  1. `side_effect: none` and no `!` step
  2. no `params`
  3. exactly one "screen visible" in `requires`
  4. an `ends_at`

**What `goto <screen>` does**

```
1. Identify the current screen   which screen element's locators can be found
2. Find the shortest path        breadth-first search on the graph
3. Execute in order              run the navigation recipes along the path, checking each check
4. No path                       restart the app, return to the APP's home, search again from there
5. Still none                    hand over to the AI
```

- Before running a recipe, the executor runs `goto` automatically when a screen condition in `requires` does not hold.
- Navigation recipes are ordinary recipes: version matching, variants and healing all apply.
- Navigation recipes cannot have side effects, so `goto` never sends a message or changes data (see SECURITY).

```yaml
id: RCP.WIN.WECHAT.MAIN_TO_CONTACTS
applies:
  os: WIN >=10.0
  app: WECHAT >=4.0
aliases:
  en: [open contacts]
  zh: [打开通讯录]
goal:
  en: Go from the main window to the contacts page
  zh: 从主界面进入通讯录
side_effect: none
requires:
  - ELEM.WIN.WECHAT.MAIN visible
steps:
  - click ELEM.WIN.WECHAT.NAV_CONTACTS
  - wait ELEM.WIN.WECHAT.CONTACTS shown 5s
check:
  - ELEM.WIN.WECHAT.CONTACTS visible
ends_at: ELEM.WIN.WECHAT.CONTACTS
evidence: 4 runs passed check
counterexample: none known on 4.x
state: stable
verified: {count: 4, last: 2026-11-12}
```

---

## 12. Execution

### 12.1 The bar for running directly

A bundle is marked "directly runnable" only when all of these hold:

1. The main recipe is `stable` and every expanded card is at least `reproduced`
2. Every card resolved as a "match"; there is no "clue"
3. Every step and criterion conforms to the grammar of section 6
4. Every element has at least one non-`vision` locator
5. Every `!` step is authorized: confirmed on the spot in an interactive run, covered by the flow file's `authorize` when unattended
6. Every secret used can be fetched (section 13)

### 12.2 The executor `kb_run`

```
1. Read the environment snapshot → resolve and expand the recipe → check the bar; if not met, hand over to the AI
2. Acquire the lock (12.4); if unavailable, apply the busy rule
3. A screen condition in requires does not hold → goto automatically; any other condition → fail
4. Execute step by step:
   - try an element's locators in order, skipping vision
   - an action without an explicit wait waits up to 5s for the element to appear
   - at a ! step, confirm or check the authorization
   - on a failed step retry once; if it fails again → hand over to the AI
5. Check check; if it does not hold → hand over to the AI
6. Release the lock; write the run record to runs/; on success add 1 to the local verification count
```

### 12.3 Handing over to the AI

The hand-off package holds: the recipe id, the environment snapshot, the failed step, the locators already tried, a structural snapshot of the current screen and the local screenshot path. **It never contains a secret's value**; secrets are shown as `***`.

On receiving it the AI first finishes the task, then submits a fix with `kb_propose`, usually an @ variant or a new locator order.

### 12.4 Concurrency and a user at the computer

**Locks**
- On one device, **one app has at most one executor at a time**, program or AI.
- When the driver cannot work in the background (it takes the mouse and focus), **the whole device has at most one executor at a time**.
- Lock files live in `runs/locks/` with a timeout and are released automatically after a crash.
- Before operating an app directly, the AI calls `kb_lock(app)`, and `kb_unlock` afterwards.

**When the user is using the computer**
- The test: keyboard or mouse input within the last 60 seconds and the target app in the foreground. The time is configurable in `config.yaml`.
- The user is in another app and the driver supports background operation → run as usual.
- Otherwise follow the flow's `when_busy`: `wait` (default; up to 30 minutes, then notify you), `skip` (skip this run), `notify` (notify you at once).
- Something you ask the AI to do yourself is not subject to the busy rule, but still obeys locks.

### 12.5 Schedules and unattended runs

A scheduled job is a flow with a single step; trigger, authorization and lock are all in the flow file, see section 19.

Successful program runs only count in local statistics and are rolled up weekly into one `update` proposal, instead of one proposal of noise per day.

---

## 13. Secrets

### 13.1 Referencing

- Spelling: `{secret:NAME}`, NAME being upper-case letters, digits and `_`, for example `{secret:OA_PASSWORD}`.
- **It may appear in two places only**: a flow's `inputs`, and the parameters passed to `kb_run` in an interactive run.
- **Cards never contain a secret reference.** A card uses ordinary parameters, such as a login recipe with `params: [user, password]`, and the flow binds `password` to a secret.

```yaml
# in a flow
inputs:
  user: <OA user name>
  password: "{secret:OA_PASSWORD}"
secrets: [OA_PASSWORD]
steps:
  - call RCP.COMMON.OA.LOGIN user={user} password={password}
```

### 13.2 Storage

Decided by `secret_backend` in `config.yaml` (`env` / `keychain` / `auto`; the default `auto` looks in `.env` first, then the system keychain).

| Backend | Location | Suited to |
|---|---|---|
| `.env` file | Windows: `%USERPROFILE%\.cua-experience\.env`; macOS/Linux: `~/.cua-experience/.env` | **recommended on Windows**; easy to inspect and edit |
| System keychain | Windows Credential Manager, macOS Keychain, Linux Secret Service | higher security needs |

The `.env` format:

```
KB_SECRET_OA_PASSWORD=xxxxxx
KB_SECRET_WECHAT_PIN=xxxxxx
```

- Only lines beginning with `KB_SECRET_` are read; other lines are ignored.
- **`.env` lives in the user directory outside the repository**, so its location rules out an accidental commit.
- The same applies to Android, iOS and HarmonyOS devices: secrets stay on the computer that controls them and the driver types them.

**Commands**

| Command | Effect |
|---|---|
| `kb secret set NAME` | hidden input, written to the current backend |
| `kb secret list` | names only, never values |
| `kb secret rm NAME` | delete |
| `kb secret check` | check the location and permissions of `.env` (on Windows, readable by the current user only) |

### 13.3 Use (a secret only flows into an input field)

- **A secret's value may only flow into `type` and `clipboard`**; with `clipboard` the executor clears the clipboard right after pasting.
- It cannot enter `write_table`, a file, `output` or a comparison, nor be the object of any `!` step. `kb check` follows parameters through `call`.
- **The AI never gets plaintext.** When the AI executes and meets a secret parameter it calls `kb_type_secret(NAME)` and the executor types it.
- Logs, screenshots and hand-off packages show `***`; the executor takes no screenshot of the step that types a secret.
- A flow must declare the secrets it uses under `secrets`; the list is part of the lock hash and an undeclared secret cannot be used.

---

## 14. Internationalisation and China

### 14.1 Canonical form and Chinese aliases

- **The repository stores the English canonical form** throughout: field names, verbs, keywords, state values. Contributors and tools anywhere can read it directly.
- **The parser also accepts the Chinese aliases** (appendix A). A card written in Chinese is exactly equivalent to one written in English.
- `kb fmt` converts cards to the canonical form; `kb show --lang zh-CN` displays them in Chinese.
- A contributor may write entirely in Chinese; `kb propose` converts on submission.

### 14.2 Multilingual content

- `aliases` are grouped by language: `{en: [...], zh: [...]}`. At least one; public cards should have both.
- Other text fields (`purpose`, `goal`, `notes`, `conclusion`, `symptom` …) are either one string or `{en: ..., zh: ...}`. Display picks the user's language and falls back to what exists.
- **A different UI language is a different environment.** Cards that depend on UI text must write `applies.lang`; the English UI gets an @ variant (such as `REMARK_ROW@en`); do not depend on text when an `id` is available.

### 14.3 China

| Problem | Approach |
|---|---|
| Typing Chinese often goes wrong | always call `RCP.COMMON.INPUT_TEXT`; each platform uses a reliable method such as the clipboard instead of typing Chinese directly |
| Chinese Android ROMs all differ (permission dialogs, settings paths) | `applies.rom` names the vendor system: HyperOS, ColorOS, OriginOS, MagicOS; differences go into @ variants |
| HarmonyOS NEXT no longer runs Android apps | its own platform `HARMONY`, driven by hdc; Cua does not support it yet, so the driver has to be added |
| Apps common in China | WeChat, WeCom, DingTalk, Feishu (Lark), WPS and others are ordinary apps, with `aliases` in both languages |
| Unreliable access to GitHub | releases are synchronised to a Gitee mirror; the client trusts signatures only, so the mirror is just a download channel (see SECURITY) |
| Privacy compliance | data minimisation under both GDPR and the Personal Information Protection Law (see SECURITY) |

---

## 15. Complete examples

> The 4.2 UI change and the "XXAPP" in these examples are invented to demonstrate the mechanism.

**Example 1: renaming a WeChat remark (across versions)**

```yaml
# cards/common/wechat.yaml
id: RCP.COMMON.WECHAT.RENAME_REMARK
applies:
  os: any
  app: WECHAT any
aliases:
  en: [rename remark, set contact remark]
  zh: [改备注, 修改备注名, 设置备注]
params: [contact, remark]
goal:
  en: The contact is shown as {remark} in the contact list
  zh: 该联系人在联系人列表中显示为 {remark}
side_effect: external
```

```yaml
# cards/windows/wechat.yaml
id: RCP.WIN.WECHAT.RENAME_REMARK
applies:
  os: WIN >=10.0
  app: WECHAT >=4.0
  driver: cua-driver >=0.47
requires:
  - ELEM.WIN.WECHAT.MAIN visible
steps:
  - call RCP.WIN.WECHAT.OPEN_PROFILE contact={contact}
  - move_window ELEM.WIN.WECHAT.PROFILE_CARD away_from ELEM.WIN.WECHAT.MAIN
  - click ELEM.WIN.WECHAT.REMARK_ROW
  - wait ELEM.WIN.WECHAT.REMARK_EDIT shown 5s
  - key Ctrl+A
  - call RCP.COMMON.INPUT_TEXT text={remark}
  - key! Enter
check:
  - ELEM.WIN.WECHAT.PROFILE_REMARK text == {remark}
ends_at: ELEM.WIN.WECHAT.PROFILE_CARD
notes:
  zh: 需以正常用户权限运行（FAIL.WIN.UIPI_LOW_IL）；第 2 步的原因见 FAIL.WIN.WECHAT.CARD_BEHIND
evidence: 3 runs passed check
counterexample: non-friends have no remark row
state: stable
verified: {count: 3, last: 2026-11-12}
---
id: ELEM.WIN.WECHAT.REMARK_ROW@4.2
applies:
  os: WIN >=10.0
  app: WECHAT >=4.2
  lang: zh-CN
locators:
  - ax role=Edit name="备注" parent=ELEM.WIN.WECHAT.PROFILE_CARD
  - text "备注" right_of
evidence: on 4.2 the Button is gone and replaced by an Edit
state: observed
verified: {count: 1, last: 2026-11-12}
```

**The same `call RCP.COMMON.WECHAT.RENAME_REMARK` resolves per environment to:**

| Environment | The recipe resolves to | The element of step 3 resolves to |
|---|---|---|
| Windows 11 + WeChat 4.1 | `RCP.WIN.WECHAT.RENAME_REMARK` | `ELEM.WIN.WECHAT.REMARK_ROW` |
| Windows 11 + WeChat 4.2 | `RCP.WIN.WECHAT.RENAME_REMARK` | `ELEM.WIN.WECHAT.REMARK_ROW@4.2` |
| Android 14 + WeChat 8.0 | `RCP.ANDROID.WECHAT.RENAME_REMARK` | `ELEM.ANDROID.WECHAT.REMARK_ENTRY` |
| macOS + WeChat | no method → the AI explores and then proposes `RCP.MAC.WECHAT.RENAME_REMARK` | — |

**Example 2: a daily check-in (run directly by the program)**

```yaml
# cards/android/xxapp.yaml
id: RCP.ANDROID.XXAPP.DAILY_CHECKIN
applies:
  os: ANDROID >=12
  app: XXAPP >=5.0
  driver: adb
steps:
  - open APP.ANDROID.XXAPP
  - wait ELEM.ANDROID.XXAPP.HOME shown 15s
  - if ELEM.ANDROID.XXAPP.PROMO_CLOSE visible then click ELEM.ANDROID.XXAPP.PROMO_CLOSE
  - if ELEM.ANDROID.XXAPP.CHECKIN_DONE visible then end
  - click! ELEM.ANDROID.XXAPP.CHECKIN_BUTTON
  - wait ELEM.ANDROID.XXAPP.CHECKIN_DONE shown 10s
check:
  - ELEM.ANDROID.XXAPP.CHECKIN_DONE visible
ends_at: ELEM.ANDROID.XXAPP.HOME
evidence: passed check for 20 consecutive days
counterexample: home page differs when logged out
state: stable
verified: {count: 20, last: 2026-11-12}
```

With a one-step flow configured (see 19.6), `kb_run` executes this every day without calling the AI. On the day the app is redesigned and the check-in button cannot be found, the run is handed to the AI. The AI completes the check-in and proposes a `CHECKIN_BUTTON@<new version>` variant. After you approve the new lock hash, the program runs it directly again the next day.

---

## 16. Iteration

**Four states** (computed separately for each card and each variant)

```
observed ──seen independently a 2nd time──► reproduced ──≥3 in total and a counterexample can be written──► stable
any state ──version change / a contrary result──► recheck (verify before use)
```

"A counterexample can be written" is a hard requirement: a card that cannot say when it does not hold stays `reproduced` forever. Common cards have no steps and no state.

**How to update after each run**

| What happened | Proposal |
|---|---|
| The environment matched and the card worked | `update`: verification count + 1 |
| Following the card failed | note the symptom first; two consecutive failures mark it `recheck` |
| The card worked on a new version outside its range | `widen`: widen `applies` |
| Something differs on a new version, language or vendor ROM | `variant`: a new @ variant with only the differing fields |
| A later locator candidate was the one that worked | `variant`: reorder `locators` |
| The first success on a platform | `new`: the same-name card for that platform |
| The same pitfall appears in 3 or more apps | move it to `_platform.yaml` or `_common.yaml` |
| Nobody uses the old version any more | delete the old card, or fold the variant back into the base |

**Maintenance rhythm**

| How often | What |
|---|---|
| Every task | the AI proposes at most 3 items |
| Weekly | merge proposals; roll up the program's run statistics |
| Monthly | promote cards that qualify; delete cards that were not hit for 3 months and never reached `stable` |
| App or driver upgrade | mark the affected cards `recheck` |
| Quarterly | delete more cards than you add |

---

## 17. Getting started

1. **One system, one app**: Windows + cua-driver + one app. Implement the YAML parser, `kb check` and `kb fmt` first, and get "retrieve → AI executes → propose → merge" working.
2. **Navigation and program execution**: add the navigation recipes for that app and run one stable recipe with `kb_run`; then cause a failure on purpose to exercise the hand-off.
3. **A second version and a second UI language**: exercise "widen" and "@ variants".
4. **A second system**: check that same-name cards make a common goal work on both.
5. **The first flow**: chain two or three stable recipes and exercise data passing, secrets, resume, locks and unattended authorization.

Early on, watch four numbers only: retrieval precision, the success rate of following a card, the share run directly by the program, and how long a broken card takes to be fixed.

---

## 18. Deliberately not done

| Not done | Why |
|---|---|
| Exporting experience as scripts | it forks from the library and loses version matching; a script is arbitrary code and cannot be reviewed |
| Jumps and loops in steps | sequential execution plus single-step conditions always terminates; retries belong to the executor |
| A directory per version | ranges and @ variants are enough |
| Decimal confidence, success-rate formulas | state plus count is enough; finer numbers are easier to game |
| Screenshots in the library, telemetry | a leak risk, and unnecessary |
| Vector retrieval from day one | environment scoping plus alias matching is enough for a few hundred cards |
| A cloud secret service | secrets stay on the device |
| A public flow library, scripts in flows | flows contain personal information and stay local for now; de-personalised flow templates and approved local scripts can be added when needed |

---

# Part 2: Flows

## 19. Flows

### 19.1 Why they are separate from cards

| | Card | Flow |
|---|---|---|
| Answers | how to do one thing inside one app | how to see one errand of mine through |
| Scope | one app | several apps, plus files and data |
| Personal data, secret references | not allowed | allowed, local only |
| Stored | `cards/`, publishable | `flows/`, local only |
| How it is used | it is called | it is triggered (manually, on a schedule, on a file change) |

**Division of labour**: a flow only orders things and passes data; every app operation goes through `call` to a card, and a flow contains no click or locator. So when an app is redesigned only the cards are repaired, and version matching, navigation, healing and security checks all reuse the cards' machinery.

### 19.2 The flow file

One file per flow: `flows/<name>.flow.yaml`. Taking "task list → Excel summary → send to the boss on WeChat → write back to the task list":

```yaml
format: 6
id: FLOW.WEEKLY_REPORT
aliases:
  en: [weekly report]
  zh: [周报, 发总结给老板]
trigger: [manual, schedule Fri 16:30]
workdir: <weekly report folder>
inputs:
  tasks: "{workdir}/tasks.csv"
  boss: <the boss's WeChat display name>
secrets: []
when_busy: wait
steps:
  - read_table {tasks} where status == "已完成" and reported != "是" -> {done}
  - if {done} empty then end
  - call RCP.COMMON.EXCEL.BUILD_SUMMARY source={tasks} save_as={run_dir}/summary.xlsx -> {summary}
  - call RCP.COMMON.WECHAT.SEND_FILE contact={boss} file={summary}
  - write_table {tasks} rows task in {done.task} set reported = "是"
check:
  - '{tasks} rows task in {done.task} column reported all == "是"'
authorize:
  unattended: [4]
  files: ["{summary}"]
  recipients: ["{boss}"]
lock: sha256:<hash of the flow file + all expanded cards>
state: stable
verified: {count: 6, last: 2026-11-12}
lessons:
  - 2026-11-05 the boss does not read messages after 17:00 on Fridays, so the schedule moved to 16:30
```

**Fields**

| Field | Chinese | Required | Meaning |
|---|---|---|---|
| `format` `id` | 格式 编号 | yes | `id` is `FLOW.<NAME>` |
| `aliases` | 说法 | yes | `kb_bundle` matches these first |
| `trigger` | 触发 | yes | `manual`, `schedule <time>`, `file_change {path}`; several allowed |
| `workdir` | 工作目录 | yes | the only directory the flow may read and write (besides this run's `{run_dir}`) |
| `inputs` | 输入 | no | personal bindings: files, contacts, text, `{secret:NAME}` |
| `secrets` | 密钥 | no | the names of the secrets used |
| `when_busy` | 忙时 | no | `wait` (default) / `skip` / `notify`, see 12.4 |
| `steps` | 步骤 | yes | see 19.3 |
| `check` | 判据 | yes | the standard for the whole errand |
| `authorize` | 授权 | no | for unattended runs: the step numbers of allowed `!` steps, the files that may go out, the people they may go to |
| `lock` | 锁定 | no | produced by `kb flow approve`; `lessons` is not part of the hash |
| `state` `verified` | 状态 验证 | yes | as for cards; a flow needs no counterexample and is `stable` after 3 successes |
| `lessons` | 经验 | no | experience particular to this errand, one "date + sentence" per line; programs do not read it |

### 19.3 Step grammar

A flow has 7 verbs and **no** UI operation such as clicking or typing:

| Verb | Form | Notes |
|---|---|---|
| `call` | `call <RCP id> name=value … [-> {variable}]` | every app operation goes through here |
| `read_table` | `read_table {file} [where <row condition>] -> {variable}` | built in; csv and xlsx |
| `write_table` | `write_table {file} rows <row condition> set <column> = <value>` | built in; backs up to the run directory first |
| `wait_file` | `wait_file {path} <N>s` | wait for a file an app exports |
| `confirm` | `confirm "<text shown to the user>"` | a human checkpoint; an unattended run pauses and notifies you |
| `if` | `if <condition> then <single action>` | same rules as in cards |
| `end` | `end` | jump ahead to the criteria |

**Conditions available in flows**

```
<column> == | != | contains <value>                # row condition, used in where / rows
<column> in {variable.column}                      # row condition
{variable} empty | {variable} not_empty
{variable} rows > | == | < <number>
{file} rows <row condition> column <column> all == <value>
<condition> and <condition>
```

### 19.4 How data moves between apps

- **Variables have three sources**: `inputs`, the result of `read_table`, and the output received by `call` with `->`. Built-in variables are `{workdir}`, `{run_dir}`, `{today}`.
- `{variable.column}` takes one column of a table, for example `{done.task}`.
- **Files move between apps as paths**: the previous recipe's `output` is a file path and the next recipe's parameter receives it.
- **Intermediate products go to `{run_dir}` by default**, that is `runs/<flow>/<run id>/`, one per run, for tracing and re-sending.
- **A recipe that a flow can chain declares `output`**:

```yaml
id: RCP.COMMON.EXCEL.BUILD_SUMMARY
applies:
  os: any
  app: EXCEL any
aliases:
  en: [build summary table]
  zh: [汇总表, 做总结表]
params: [source, save_as]
output: [summary]
goal:
  en: A summary workbook is created at {save_as}; {summary} equals that path
  zh: 在 {save_as} 生成汇总表，{summary} 等于该文件路径
side_effect: none
```

### 19.5 Running: checkpoints and resume

```
kb flow run FLOW.WEEKLY_REPORT
  check the trigger and the busy rule
  step by step:
    call → handed to kb_run; if it is not directly runnable, handed to the AI
    after each step, write a checkpoint: runs/<flow>/<run id>/state
  a step fails → the flow pauses → the AI fixes that step (card problems are proposed as usual)
              → kb flow resume continues from the failed step
  all done → check check
```

- **Completed steps are not redone.** A step with `!` (for example "already sent to the boss") is **never redone automatically**.
- **When the state of a `!` step is uncertain** (for example the program crashed after clicking send), do not retry: the AI first verifies in the app whether it went out, then decides.
- When `write_table` goes wrong, restore from the backup in the run directory.

### 19.6 A scheduled job is a one-step flow

```yaml
format: 6
id: FLOW.DAILY_CHECKIN
aliases:
  zh: [每日签到]
trigger: [schedule daily 08:10]
workdir: <check-in folder>
when_busy: wait
steps:
  - call RCP.COMMON.XXAPP.DAILY_CHECKIN
check:
  - step 1 succeeded
authorize:
  unattended: [1]
lock: sha256:<…>
state: stable
verified: {count: 20, last: 2026-11-12}
```

### 19.7 How a flow comes to be, and where its experience goes

```
you describe the errand in one sentence → the AI drafts (kb_bundle finds a recipe per sub-goal) → you review
  → trial run (the AI executes and shows you each step's result) → observed → reproduced → stable
  → you approve the authorization and the lock → the program runs it unattended
```

- **A sub-goal without a recipe**: written as a pending `call`; during the trial run the AI explores it and submits a card proposal. A flow never contains the details of operating an app.
- **A sub-goal that needs a password**: the AI writes only `{secret:NAME}` in the flow and reminds you to store it with `kb secret set NAME`; the AI never handles the password.
- **The bar for unattended runs**: the flow is `stable`, every called recipe is directly runnable, `authorize` covers every `!` step, and every secret can be fetched.

**Where experience is written**

| What was learned | Where it goes |
|---|---|
| How an app works, its pitfalls and elements | a card (through `kb_propose`; publishable) |
| How data moves between apps, the order, what is special about this errand | the flow's `lessons` (local) |
| Who to send to, which file to use | the flow's `inputs` (local) |
| Passwords | `.env` or the system keychain |

The test is one sentence: **what is still useful outside this errand goes into a card; what means nothing outside it stays in the flow.**

---

# Appendix A: Chinese–English table

The parser accepts both spellings; `kb fmt` converts to English.

**Fields**

| English | Chinese | English | Chinese | English | Chinese |
|---|---|---|---|---|---|
| `id` | 编号 | `applies` | 适用 | `aliases` | 说法 |
| `capabilities` | 能力 | `limits` | 限制 | `version_probe` | 版本获取 |
| `app_id` | 标识 | `home` | 首页 | `preferred` | 推荐手段 |
| `purpose` | 作用 | `parent` | 所在 | `locators` | 定位 |
| `params` | 参数 | `goal` | 目标 | `side_effect` | 副作用 |
| `output` | 输出 | `requires` | 前置 | `steps` | 步骤 |
| `check` | 判据 | `ends_at` | 结束于 | `symptom` | 症状 |
| `conclusion` | 结论 | `notes` | 说明 | `evidence` | 证据 |
| `counterexample` | 反例 | `state` | 状态 | `verified` | 验证 |
| `format` | 格式 | `trigger` | 触发 | `workdir` | 工作目录 |
| `inputs` | 输入 | `secrets` | 密钥 | `when_busy` | 忙时 |
| `authorize` | 授权 | `lock` | 锁定 | `lessons` | 经验 |
| `os` | 系统 | `app` | 软件 | `driver` | 驱动 |
| `lang` | 语言 | `display` | 显示 | `rom` | 厂商系统 |

**Verbs**

| English | Chinese | English | Chinese | English | Chinese |
|---|---|---|---|---|---|
| `open` | 打开 | `goto` | 前往 | `click` | 点击 |
| `double_click` | 双击 | `right_click` | 右击 | `scroll` | 滚动 |
| `drag` | 拖动 | `key` | 按键 | `type` | 输入 |
| `clipboard` | 写剪贴板 | `move_window` | 移动窗口 | `wait` | 等待 |
| `read` | 读取 | `assert` | 校验 | `call` | 调用 |
| `if` | 若 | `end` | 结束 | `read_table` | 读表 |
| `write_table` | 写表 | `wait_file` | 等待文件 | `confirm` | 确认 |

**Keywords and values**

| English | Chinese | English | Chinese | English | Chinese |
|---|---|---|---|---|---|
| `visible` | 可见 | `hidden` | 不可见 | `shown` | 出现 |
| `gone` | 消失 | `text` | 文字 | `value` | 值 |
| `contains` | 包含 | `and` | 且 | `then` | 则 |
| `to` | 到 | `away_from` | 避开 | `up` / `down` | 上 / 下 |
| `focus` | 焦点 | `empty` | 为空 | `not_empty` | 不为空 |
| `rows` | 行 | `column` | 列 | `all` | 全部 |
| `where` | 筛选 | `set` | 设为 | `in` | 在 |
| `any` | 任意 | `->` | → | `unknown` | 未知 |
| `ax` | 无障碍 | `coord` | 坐标 | `vision` | 视觉 |
| `role` | 角色 | `name` | 名称 | `pick` | 取 |
| `first` / `last` | 第一 / 最后 | `self` | 本身 | `right_of` / `left_of` | 右侧 / 左侧 |
| `above` / `below` | 上方 / 下方 | `observed` | 观察 | `reproduced` | 复现 |
| `stable` | 稳定 | `recheck` | 待复核 | `none` | 无 |
| `destructive` | 破坏 | `external` | 外部 | `manual` | 手动 |
| `schedule` | 定时 | `file_change` | 文件变化 | `wait` / `skip` / `notify` | 等待 / 跳过 / 通知 |
