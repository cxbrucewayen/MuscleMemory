# Implementation status

**English** | [简体中文](../zh-CN/STATUS.md)

What the v0.1 baseline implements, where it deviates from the [design](./DESIGN.md) and the [security design](./SECURITY.md), and what is still missing.

## Implemented and tested

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
| Installer | `install.py`, `skill/` | `kb setup` installs the skill (English or Chinese) and registers the MCP server with Claude Code, Cursor and Claude Desktop; checked against the real Claude Code CLI, the other two by their config files only |

The test suite (`tests/`) runs the whole pipeline on the simulator, including the negative cases: forged confirmation tokens, tampered cards under an approved flow, secrets in logs, recipients outside `authorize`.

## Not verified on real devices

- **`adb` driver**: written with stock commands (`uiautomator dump`, `input`, `monkey`, `dumpsys`). Never run against a device in this repository. Non-ASCII typing needs the ADBKeyBoard IME; `clipboard` steps are unsupported.
- **`cua-driver` adapter**: written against the driver's published tool contract (contract 0.8.0, skill pack 0.47.x) and speaks MCP to `cua-driver mcp`. Never run against a live driver. The contract's element list has no automation id, so `ax id=` locators cannot match through it. App-version detection is best effort.
- **User-busy detection** (`when_busy`): only the simulator reports it. With `adb` and `cua` the user is always treated as idle.

## Where the implementation deviates or decides something the spec leaves open

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
12. **Repository layout.** The specification's tree shows `DESIGN.md`, `SKILL.md` and `SECURITY.md` at the root. Here the documents live under `docs/<language>/`, and the skill ships inside the Python package (`src/musclememory/skill/`) so that `kb setup` can install it; it comes with a short `REFERENCE.md` instead of pointing the agent at the full specification.
13. **Local statistics** are written to `runs/stats.json`; the weekly roll-up into an `update` proposal is not implemented.

## Not implemented

- The "looks like a personal name" privacy rule, per-contributor rate limits, the reviewer behaviour summary, signed releases and the Gitee mirror (gate 2 and 3 of SECURITY)
- **Sites inside a browser as first-class apps, and choosing cards per site.** `applies` selects by OS, app version, driver, UI language, display and vendor ROM. There is no "site" or "tenant" dimension, so the README's Workday example cannot yet have one variant per company; differences between sites are handled by ordered locators and `if … visible` guards. Adding the dimension is a change to the card format in `DESIGN.md`
- HarmonyOS (`hdc`) and iOS drivers; `vision` locators for programs (by design they are AI-only)
- Semantic retrieval; localised CLI messages (card content and field names are bilingual, CLI messages are English)
- Monthly maintenance automation (promotion, pruning) and `kb migrate` rules (there is only format 6)
