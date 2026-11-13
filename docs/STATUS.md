# Implementation status · 实现状态

What the v0.1 baseline implements, where it deviates from `DESIGN.md` / `SECURITY.md`, and what is still missing. English first, 中文在后。

---

## English

### Implemented and tested

| Area | Where | Notes |
|---|---|---|
| Card files, ids, headers, format version | `cards.py` | duplicate YAML keys are rejected |
| Chinese aliases → canonical English | `i18n.py` | every check runs after conversion |
| Version ranges, `applies`, environment snapshot | `versions.py` | numeric comparison per segment |
| Step, condition, locator and flow grammars | `grammar.py` | 15 card verbs, 7 flow verbs, nothing else parses |
| `kb fmt` | `fmt.py` | key names, key order, quoting; idempotent |
| `kb check` | `check.py`, `scan.py` | format, structure, grammar, language, side effects, inheritance, navigation, secrets, injection, hidden content, exfiltration, privacy, secret patterns |
| Resolution and bundles | `resolve.py` | platform swap, variants, specificity, clue fallback, merge, the "directly runnable" gate |
| Retrieval | `search.py` | `kb_bundle`, `kb_symptom`, `kb_screen`, `kb_outline`, `kb_resolve`, `kb index` |
| Executor | `executor.py` | locks, auto-`goto`, per-step retry, `!` confirmation, foreground guard, hand-off package, run records |
| Drivers | `drivers/` | simulator (tested), `adb`, `cua-driver` |
| Secrets | `secrets.py` | `.env` outside the repo with permission check, optional keychain via `keyring`, masking, static flow tracing |
| Proposals | `propose.py` | `kb_propose` as the only write path, `kb merge` for maintainers |
| Flows | `flows.py` | 7 verbs, csv/xlsx tables with backup, checkpoints, resume, `authorize`, lock hash, schedules via `kb flow tick` |
| MCP server | `mcp_server.py` | stdio, no SDK dependency, 12 tools, elicitation for `!` steps |

The test suite (`tests/`) runs the whole pipeline on the simulator, including the negative cases: forged confirmation tokens, tampered cards under an approved flow, secrets in logs, recipients outside `authorize`.

### Not verified on real devices

- **`adb` driver**: written with stock commands (`uiautomator dump`, `input`, `monkey`, `dumpsys`). Never run against a device in this repository. Non-ASCII typing needs the ADBKeyBoard IME; `clipboard` steps are unsupported.
- **`cua-driver` adapter**: written against the driver's published tool contract (contract 0.8.0, skill pack 0.47.x) and speaks MCP to `cua-driver mcp`. Never run against a live driver. The contract's element list has no automation id, so `ax id=` locators cannot match through it. App-version detection is best effort.
- **User-busy detection** (`when_busy`): only the simulator reports it. With `adb` and `cua` the user is always treated as idle.

### Where the implementation deviates or decides something the spec leaves open

1. **`ends_at`** is required for app recipes only. Platform-level recipes such as `RCP.WIN.INPUT_TEXT` are not tied to a screen.
2. **Outputs.** There is no assignment verb, so an `output` must be set by `read ... -> {x}` or `call ... -> {x}`, or carry the name of a parameter. A recipe that produces a file can declare `params: [save_as]`, `output: [save_as]`.
3. **Call arguments in cards** must be `{parameters}`. A literal could otherwise reach `type` through a call.
4. **`!`** is accepted on `click`, `double_click`, `right_click`, `drag`, `key` and `type`.
5. **Side-effect order** is `none < destructive < external`.
6. **Flow condition `step N succeeded`** is part of the grammar (the spec uses it in 19.6).
7. **Lock hash.** It covers the flow file except `lock`, `lessons` and the `verified` counter (the program updates that counter after each run), plus every card in the *static closure* of the flow's calls on the current platform: the recipes, all their variants, called recipes, elements, the app card and the app's navigation recipes. Adding a variant therefore invalidates an approval even if it would not be selected today.
8. **`authorize.files` / `recipients`.** There is no schema that says which parameter is a recipient, so an unattended run checks every argument that is an existing file against `files`, and every argument whose parameter is named like a recipient (`contact`, `recipient`, `to`, `group`, `chat`, …) against `recipients`.
9. **`!` over MCP.** With elicitation the server asks the user at each `!` step. Without it, `kb_run` / `kb_flow` return the `!` steps and a one-time token bound to the exact call. This relies on the agent asking the user, as rule 8 of the skill requires.
10. **Proposal limit.** "At most 3 per task" is counted per MCP session and reset by `kb_bundle`.
11. **`kb fmt` drops YAML comments.** Comments are not part of the data model and agents never read raw files.
12. **Local statistics** are written to `runs/stats.json`; the weekly roll-up into an `update` proposal is not implemented.

### Not implemented

- The "looks like a personal name" privacy rule, per-contributor rate limits, the reviewer behaviour summary, signed releases and the Gitee mirror (gate 2 and 3 of SECURITY)
- HarmonyOS (`hdc`) and iOS drivers; `vision` locators for programs (by design they are AI-only)
- Semantic retrieval; localised CLI messages (card content and field names are bilingual, CLI messages are English)
- Monthly maintenance automation (promotion, pruning) and `kb migrate` rules (there is only format 6)

---

## 中文

### 已实现并有测试

| 模块 | 位置 | 说明 |
|---|---|---|
| 卡片文件、id、文件头、格式版本 | `cards.py` | 拒绝重复的 YAML 键 |
| 中文别名 → 英文规范形式 | `i18n.py` | 所有检查都在转换之后进行 |
| 版本范围、`applies`、环境快照 | `versions.py` | 按数字逐段比较 |
| 步骤、条件、定位、流程四套小语法 | `grammar.py` | 卡片 15 个动词，流程 7 个，其余一律无法解析 |
| `kb fmt` | `fmt.py` | 键名、键顺序、引号；重复运行结果不变 |
| `kb check` | `check.py`、`scan.py` | 格式、结构、语法、语言、副作用、继承、导航、密钥、注入、隐藏内容、外发、隐私、密钥特征 |
| 解析与经验包 | `resolve.py` | 换平台、变体、具体度排序、线索兜底、合并、“可直接运行”门槛 |
| 检索 | `search.py` | `kb_bundle`、`kb_symptom`、`kb_screen`、`kb_outline`、`kb_resolve`、`kb index` |
| 执行器 | `executor.py` | 锁、自动 `goto`、单步重试、`!` 确认、前台软件校验、交接包、运行记录 |
| 驱动 | `drivers/` | 模拟器（有测试）、`adb`、`cua-driver` |
| 密钥 | `secrets.py` | 仓库外的 `.env` 及权限检查，可选系统钥匙串（`keyring`），脱敏，静态追踪流向 |
| 提案 | `propose.py` | `kb_propose` 是唯一写入口；维护者用 `kb merge` 合并 |
| 事务流程 | `flows.py` | 7 个动词，csv/xlsx 表格与备份，检查点，恢复，`authorize`，锁定哈希，`kb flow tick` 定时 |
| MCP 服务 | `mcp_server.py` | stdio，不依赖 SDK，12 个工具，`!` 步骤走 elicitation |

测试（`tests/`）在模拟器上跑通整条链路，并覆盖反面情况：伪造确认令牌、已批准流程的卡片被篡改、密钥出现在日志里、收件人不在 `authorize` 中。

### 尚未在真机上验证

- **`adb` 驱动**：用系统自带命令实现（`uiautomator dump`、`input`、`monkey`、`dumpsys`），在本仓库里没有接过真机。输入非 ASCII 文字需要设备上装有 ADBKeyBoard 输入法；不支持 `clipboard` 步骤。
- **`cua-driver` 适配**：按驱动公开的工具契约（contract 0.8.0，技能包 0.47.x）编写，通过 MCP 与 `cua-driver mcp` 通信，没有接过真实驱动。契约里的元素没有 automation id，所以 `ax id=` 定位在这个驱动上匹配不到。软件版本的读取只是尽力而为。
- **“用户正在使用电脑”的判断**（`when_busy`）：只有模拟器会上报。`adb` 和 `cua` 下始终视为用户空闲。

### 与设计有出入、或设计没写明而由实现决定的地方

1. **`ends_at`** 只对软件配方必填。`RCP.WIN.INPUT_TEXT` 这类平台层配方不绑定界面。
2. **输出**：语法里没有赋值动词，所以 `output` 必须由 `read ... -> {x}` 或 `call ... -> {x}` 赋值，或者与某个参数同名。产出文件的配方可以写 `params: [save_as]`、`output: [save_as]`。
3. **卡片里 `call` 的参数值**只能是 `{参数}`。否则字面量可以借调用流进 `type`。
4. **`!`** 可以加在 `click`、`double_click`、`right_click`、`drag`、`key`、`type` 上。
5. **副作用的高低**：`none < destructive < external`。
6. **流程条件 `step N succeeded`** 纳入语法（设计 19.6 的例子用到了）。
7. **锁定哈希**：覆盖流程文件（`lock`、`lessons`、`verified` 计数除外，因为程序每次成功后会更新计数），以及流程所有调用在当前平台上的**静态闭包**里的每一张卡：配方及其全部变体、被调用的配方、元素、软件卡、该软件的导航配方。所以哪怕新增的变体今天不会被选中，批准也会失效。
8. **`authorize.files` / `recipients`**：没有字段说明哪个参数是收件人，所以无人值守运行时，凡是值为现有文件的参数都要在 `files` 里，凡是参数名像收件人的（`contact`、`recipient`、`to`、`group`、`chat` 等）都要在 `recipients` 里。
9. **MCP 下的 `!`**：客户端支持 elicitation 时，服务在每个 `!` 步骤前直接问用户。不支持时，`kb_run` / `kb_flow` 返回 `!` 步骤清单和绑定本次调用的一次性令牌。这依赖智能体确实去问用户，也就是技能里的第 8 条规则。
10. **提案上限**：“每次任务最多 3 条”按 MCP 会话计数，调用 `kb_bundle` 时清零。
11. **`kb fmt` 会丢弃 YAML 注释**。注释不属于数据模型，智能体也从不读原始文件。
12. **本地统计**写在 `runs/stats.json`；每周汇总成一条 `update` 提案的功能未实现。

### 未实现

- “疑似人名”的隐私规则、新贡献者限流、给审核者的行为摘要、签名发布、Gitee 镜像（SECURITY 的闸二、闸三）
- 鸿蒙（`hdc`）与 iOS 驱动；程序可用的 `vision` 定位（按设计它只给 AI 用）
- 语义检索；命令行提示的中文化（卡片内容和字段名是双语的，命令行提示目前只有英文）
- 每月维护的自动化（升级、清理）和 `kb migrate` 的迁移规则（目前只有格式 6）
