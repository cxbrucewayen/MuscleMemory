# MuscleMemory

**English** | [简体中文](./README.zh-CN.md)

[![CI](https://github.com/cxbrucewayen/MuscleMemory/actions/workflows/ci.yml/badge.svg)](https://github.com/cxbrucewayen/MuscleMemory/actions/workflows/ci.yml)

> **Muscle memory for AI agents.** The first time, the AI figures a GUI task out. After that, a program replays the experience, and the AI only steps back in when something changed.

**Status: working baseline (v0.1).** The `kb` command line, the checker, the resolver, the executor, flows, secrets and an MCP server are implemented and tested against a built-in UI simulator. Real-device drivers exist for Android (`adb`) and desktop (`cua-driver`, experimental) but have not been run against real devices in this repository's CI. The public card library is still almost empty: verified cards arrive through proposals. See [docs/STATUS.md](./docs/STATUS.md) for exactly what is and is not done.

---

## Why

Computer-use agents can already operate a desktop or a phone, but every run starts from zero: take a screenshot, understand the UI, guess the button, try again.

- **Slow and expensive.** The hundredth run costs as much time and as many tokens as the first.
- **Unstable.** It clicked the right thing today; tomorrow's app update moves it.
- **Nothing accumulates.** The pitfall you hit will be hit again, by you and by everyone else.

Classic RPA scripts are fast, but people record and maintain them, and they break when the UI changes.

**MuscleMemory combines the two: the AI explores and repairs; experience is reused and executed.**

```
First time:  the AI looks, explores, finishes the task  ──►  distilled into experience cards
Afterwards:  look up the cards for this environment      ──►  a program runs them (fast, zero tokens)
When broken: the app changed, a locator fails            ──►  hand over to the AI ──► it proposes a fix ──► runs directly again
```

## What it is

| | Metaphor | Problem it solves |
|---|---|---|
| MCP | the socket | how an AI calls external tools |
| Skill | the manual | how to approach a kind of task |
| [Cua](https://github.com/trycua/cua) | the hands | how an AI sees the screen, clicks and types |
| **MuscleMemory** | **the practice** | **how exactly to do this thing in this version of this app, getting more reliable with use** |

They are not competitors. MuscleMemory exposes its tools over **MCP**, ships a **Skill** that teaches an agent how to use the library, and acts through a driver such as **Cua** or **adb**.

## Features

- **Across systems, apps and versions.** The platform is a directory, the app is a file, the version is a range on the card. A reference never names a version: the resolver picks the best-matching card, and a new version only records what changed (an `@` variant).
- **Readable by AI, runnable by programs.** Steps use a small fixed grammar. Stable experience is executed by `kb run` without calling a model.
- **Self-healing.** Each element keeps several locators and a one-line `purpose`. When all locators fail, the executor hands over to the AI with a structured package; the AI finishes the task and proposes a variant.
- **Fast retrieval.** The environment narrows the scope to a few files; then one of three entry points (task, error, screen) finds the card. Related cards come back as one bundle of bounded size.
- **Navigation.** Side-effect-free recipes form a graph between screens; the executor walks to the required screen first.
- **Flows.** Chain several apps into one errand, for example "task list → summary → send to the boss → write back". Data passing, checkpoints, resume and schedules are built in.
- **Security first.** The grammar is the whitelist: there is no way to spell "run a command" or "open a URL". External experience is quarantined until someone reproduces it. Unattended jobs only run the exact version you approved. Passwords only ever flow into an input field.
- **Global, with first-class Chinese support.** The repository stores an English canonical form; every field name, verb and keyword also has a Chinese alias, and aliases are matched in all languages.

## Try it in two minutes

No device needed: the demo library runs against a simulated chat app.

```bash
git clone https://github.com/cxbrucewayen/MuscleMemory && cd MuscleMemory
pip install -e .

export KB_ROOT=examples/demo
export KB_DRIVER=sim:examples/demo/sim/windows-4.1.yaml     # a simulated "DemoChat 4.1" on Windows

kb check                                   # validate the library (format, grammar, security scan)
kb find "rename remark"                    # the experience bundle for a task; try: kb find 改备注
kb run RCP.COMMON.DEMOCHAT.RENAME_REMARK contact=Alice remark=Boss
```

`kb run` stops before the one step marked `!` and asks you:

```
! This step has an external effect:
  RCP.WIN.DEMOCHAT.RENAME_REMARK: key! Enter
  Allow it? [y/N] y
{ "status": "ok", "recipe": "RCP.WIN.DEMOCHAT.RENAME_REMARK", "message": "check passed", ... }
```

Now pretend the app was updated. In 4.2 the remark is an edit box instead of a button:

```bash
export KB_DRIVER=sim:examples/demo/sim/windows-4.2.yaml
kb find "rename remark"
```

```
env: WIN 10.0.22631 / DEMOCHAT 4.2.0 / sim 0.1.0 / en-US / DPI 100%
directly runnable: no (ELEM.WIN.DEMOCHAT.REMARK_ROW@4.2 is observed, needs at least reproduced)
├─ RCP.WIN.DEMOCHAT.RENAME_REMARK               match stable
├─ ELEM.WIN.DEMOCHAT.REMARK_ROW@4.2             match observed (variant 4.2 selected)
...
```

The same reference resolved to a different element card, and because that variant has only been seen once, the program refuses to run it unattended and leaves it to the AI (`kb run --force ...` performs the trial run).

More to try:

```bash
kb symptom "clicks on the profile card have no effect"    # look up a pitfall
kb --lang zh-CN show RCP.WIN.DEMOCHAT.RENAME_REMARK       # the same card, shown in Chinese
kb outline                                                # one line per card in scope

# A flow that reads a CSV, sends a file in the chat app and writes the CSV back.
# It edits work/tasks.csv, so run it on a copy:
cp -r examples/demo /tmp/mm-demo
kb --root /tmp/mm-demo --driver sim:/tmp/mm-demo/sim/windows-4.1.yaml flow run FLOW.WEEKLY_REPORT
```

## One card

Experience is stored as cards in plain YAML:

```yaml
id: RCP.WIN.DEMOCHAT.RENAME_REMARK        # TYPE.PLATFORM.APP.NAME
applies:
  os: WIN >=10.0
  app: DEMOCHAT >=4.0
steps:
  - call RCP.WIN.DEMOCHAT.OPEN_PROFILE contact={contact}
  - click ELEM.WIN.DEMOCHAT.REMARK_ROW
  - wait ELEM.WIN.DEMOCHAT.REMARK_EDIT shown 5s
  - key Ctrl+A
  - call RCP.COMMON.INPUT_TEXT text={remark}
  - key! Enter                            # ! = external effect; needs authorization
check:
  - ELEM.WIN.DEMOCHAT.PROFILE_REMARK value == {remark}
ends_at: ELEM.WIN.DEMOCHAT.PROFILE_CARD
state: stable
```

The same sentence, "rename the remark", resolves differently per environment:

| Environment | What is used |
|---|---|
| Windows + DemoChat 4.1 | the Windows recipe + the base locator of the remark row |
| Windows + DemoChat 4.2 | the Windows recipe + the `@4.2` variant of the remark row |
| Android + DemoChat 5.0 | no recipe yet → the AI explores, then contributes `RCP.ANDROID.DEMOCHAT.RENAME_REMARK` |

Chinese spelling is equivalent everywhere (`点击! ELEM...`, `步骤:`, `状态: 稳定`); `kb fmt` converts to the canonical form.

## Use it with a real device

```bash
kb --driver adb env            # Android over adb + uiautomator (add :<serial> for a specific device)
kb --driver cua env            # desktop apps through cua-driver (experimental adapter)
```

| Driver | Platforms | State |
|---|---|---|
| `sim:<file.yaml>` | simulated | used by the tests and the demo |
| `adb[:serial]` | Android | implemented with stock platform tools; not yet exercised on a device in CI |
| `cua` | Windows, macOS, Linux | experimental; written against cua-driver's published tool contract, not yet run against a live driver |
| HarmonyOS (`hdc`), iOS | | not implemented |

Set a default in `~/.cua-experience/config.yaml` (`driver: adb`, `lang: zh-CN`, `secret_backend: env`).

## Use it from an AI agent

Register the MCP server with your agent, for example:

```json
{
  "mcpServers": {
    "musclememory": {
      "command": "kb",
      "args": ["--root", "/path/to/MuscleMemory", "--driver", "adb", "mcp"]
    }
  }
}
```

and give the agent [`SKILL.md`](./SKILL.md) ([English](./docs/en/SKILL.md)). The tools are `kb_bundle`, `kb_symptom`, `kb_screen`, `kb_outline`, `kb_resolve`, `kb_goto`, `kb_run`, `kb_lock`, `kb_unlock`, `kb_type_secret`, `kb_propose` and `kb_flow`.

Steps marked `!` are confirmed by the user through MCP elicitation when the client supports it. Otherwise `kb_run` performs nothing, returns the list of `!` steps with a one-time token, and the agent has to ask the user before calling again.

## Commands

| Command | What it does |
|---|---|
| `kb find <task>` / `symptom <error>` / `screen <features>` / `outline` | retrieval by task, error, screen, or everything in scope |
| `kb resolve <id>` / `show <id> --lang zh-CN` | the card that applies here / print a card |
| `kb run <id> name=value ...` / `goto <screen>` | execute a recipe / navigate |
| `kb check` / `fmt` / `index` / `migrate` | validate, canonicalise, rebuild the index, upgrade formats |
| `kb propose [file]` / `merge <proposal>` | submit experience / maintainers apply a reviewed proposal |
| `kb secret set\|list\|rm\|check` | secrets, stored outside the repository |
| `kb flow run\|resume\|approve\|list\|tick` | flows; `tick` runs due schedules (call it from cron or Task Scheduler) |
| `kb env` / `kb mcp` | print the environment snapshot / serve MCP over stdio |

`--root`, `--driver`, `--env` and `--lang` work on every command; `KB_ROOT`, `KB_DRIVER` and `KB_LANG` set defaults.

## How it differs

| | Skill | Classic RPA | AI memory (e.g. mem0) | **MuscleMemory** |
|---|---|---|---|---|
| Records | general know-how | recorded scripts | facts about users and chats | how to operate a specific app at a specific version |
| Maintained by | people | people | automatic | AI accumulates, people review |
| Version awareness | none | none; breaks on updates | n/a | matched by version range, heals on failure |
| Trust | the author's word | worked when recorded | unverified | evidence and state; promoted only after independent reproduction |
| Runs without a model | no | yes | no | yes, once stable |
| Shareable | yes | hard | not suitable | yes, an open library |

**"Why not write one Skill per app?"** That works at small scale. But apps keep changing: the same button is located differently in 4.1 and 4.2, and differently again in the Chinese and English UI. A hand-written Skill cannot tell which piece of experience applies to the current version or whether it is still right, and it cannot run without a model. Those three things are what MuscleMemory is for.

## Repository layout

```
├── README.md  README.zh-CN.md
├── DESIGN.md          # the specification (Chinese): cards, grammar, resolution, retrieval, execution, flows
├── SECURITY.md        # the security design (Chinese): poisoning, injection, leaks, unattended hijacking
├── SKILL.md           # the skill for AI agents (Chinese)
├── docs/en/           # English translations of the three documents above
├── docs/STATUS.md     # what this baseline implements, where it deviates, what is missing
├── src/musclememory/  # the implementation (Python, one dependency: PyYAML)
├── cards/             # the public card library (platform/app.yaml)
├── index/             # generated retrieval index
├── examples/demo/     # a complete demo library, simulated apps and flows
├── tests/
├── proposals/         # pending proposals (quarantine); created on demand
├── flows/  runs/      # local only, git-ignored: your flows, run records, locks
```

Where to start: this file if you are curious, `DESIGN.md` then `SECURITY.md` if you want to work on the engine, the "Contributing experience" section below if you want to add cards, `SKILL.md` if you are an AI agent.

## Security

An open experience library is a **supply chain that AIs and programs execute**, so security is a premise of the design rather than a feature added later:

- **Cards are data, not instructions.** No commands, no links, no code; steps can only use whitelisted verbs, and `type` only accepts parameters, never literal text.
- **External experience is quarantined.** Machine check, human reading, **independent reproduction** in the declared environment, then a signed merge, before any agent reads it.
- **Unattended jobs only run the version you approved.** A change to the flow or to any card it can reach pauses the job until you approve again.
- **Personal data stays on your machine.** Flows, run records, screenshots and secrets are local; personal data is rejected from the public library.
- **Passwords only flow into input fields.** The AI never sees them; logs and hand-off packages show `***`.

Full design: [`SECURITY.md`](./SECURITY.md) ([English](./docs/en/SECURITY.md)). Please report vulnerabilities privately through GitHub's "Report a vulnerability" on this repository instead of opening a public issue.

## Contributing experience

1. Let your agent call `kb_propose` when a task is done, or write a proposal by hand following `DESIGN.md`. Chinese or English are both fine.
2. Run `kb fmt && kb check`; open a pull request once both pass.
3. Evidence describes structure only (controls, error codes, symptoms). **No names, chat content, local paths or passwords**; use placeholders such as `<CONTACT_A>` and `<USER_HOME>`.
4. A maintainer reproduces the card in the declared version and UI language. It is merged as `observed` and promoted as more people reproduce it.

The most valuable contributions, in order: **pitfalls (FAIL)**, **version variants**, **recipes on a new platform**.

## Roadmap

- [x] YAML parser, `kb fmt`, `kb check` (format, grammar, security scan)
- [x] Version resolution and retrieval (`kb resolve`, `kb_bundle`), MCP server
- [x] Executor `kb run`, hand-off to the AI, navigation
- [x] Flows, secrets, schedules (`kb flow tick`)
- [x] Second version and second platform, demonstrated on the simulator (UI-language matching is covered by tests)
- [ ] First real app end to end on Windows + cua-driver; verify the adapters on real devices
- [ ] A seed library of verified cards
- [ ] External contributions: behaviour summaries for reviewers, reproduction workflow, signed releases, Gitee mirror
- [ ] HarmonyOS (`hdc`) and iOS drivers; localised CLI messages; semantic retrieval when the library grows

## Acknowledgements

MuscleMemory builds on the computer-use capabilities of [Cua](https://github.com/trycua/cua). It is an independent community project and is not affiliated with Cua.

## License

MIT is planned; no license file has been added yet.
