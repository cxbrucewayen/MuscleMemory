# Never retype your resume into Workday again

**English** | [简体中文](./README.zh-CN.md)

[![CI](https://github.com/cxbrucewayen/MuscleMemory/actions/workflows/ci.yml/badge.svg)](https://github.com/cxbrucewayen/MuscleMemory/actions/workflows/ci.yml)

**MuscleMemory is muscle memory for AI agents.** The first time, the AI works out how to get through a form or an app. It leaves that experience behind as a small, reviewable card. After that a program replays the card, and the AI only steps back in when the screen has changed.

> **Status: working baseline (v0.1).** The engine is built and tested: the `kb` command line, the checker, the executor, flows, secrets and an MCP server, all exercised against a built-in UI simulator. **The Workday and expense cards shown below do not exist in the library yet.** They show what the project is for, and they are the first cards we want to build with contributors. Real-device drivers (`adb`, `cua-driver`) are written but unverified. Details: [implementation status](./docs/en/STATUS.md).

## Install

One line installs the `kb` command, the agent skill and the MCP server:

```bash
pip install git+https://github.com/cxbrucewayen/MuscleMemory && kb setup
```

`kb setup` does three things and lists every file it touches:

1. **Card library.** Uses the library you are in, or clones this repository to `~/.cua-experience/library`.
2. **Skill.** Copies the `cua-experience` skill to `~/.claude/skills/`, in English or Chinese to match your system language (`--lang en` / `--lang zh-CN` to choose).
3. **MCP server.** Registers `musclememory` with the agent clients it finds: Claude Code, Cursor and Claude Desktop. For any other MCP client it prints the configuration block to paste.

Then pick how it reaches your apps, once: `kb setup --driver adb` (Android) or `kb setup --driver cua` (desktop, experimental). `kb setup --dry-run` shows what would change, and `kb setup --uninstall` removes the skill and the MCP registration again.

---

## The example: applying for jobs on Workday

**The pain.** You upload your résumé, and then you type it all again: name, phone, every job, every school, every date. Then you do the same at the next company, because each company runs its own Workday site with its own account and a form that is almost, but not quite, the same.

**Why an AI agent alone does not fix it.** An agent can fill the form, but it relearns the form on every application: screenshot, guess, click, retry. That is slow and costly, and it fails in a new way each time.

**With MuscleMemory:**

- **Your résumé lives in one local file.** A *flow* on your machine holds your details and the order of the pages. It is never published.
- **The form knowledge lives in shared cards.** A card says where the "Phone" field is and how to tell the page was saved. It contains no personal data, so it can be open source.
- **Small differences between companies are expected.** A field keeps several ordered ways to find it, and a field only some companies ask for is wrapped in `if … visible`.
- **When a form defeats the cards, the AI finishes that one application and proposes the fix.** Once a maintainer has reproduced it, everyone has it. One person repairs it, everyone benefits.
- **Nothing is submitted without you.** The flow stops for your review, and the submit click is marked `!`, which always needs your say-so.
- **Your password never reaches the AI.** It is stored on your machine and typed by the executor.

Your side, private and local (`flows/apply-workday.flow.yaml`):

```yaml
format: 6
id: FLOW.APPLY_WORKDAY
aliases:
  en: [apply on workday, submit job application]
trigger: [manual]
workdir: <your job search folder>
inputs:
  resume: "{workdir}/resume.pdf"
  email: <your login e-mail>
  password: "{secret:WORKDAY_PASSWORD}"       # stored with `kb secret set`, never shown to the AI
  first_name: <first name>
  last_name: <last name>
  phone: <phone>
  job1_company: <most recent employer>
  job1_title: <job title>
secrets: [WORKDAY_PASSWORD]
steps:
  - call RCP.COMMON.WORKDAY.SIGN_IN email={email} password={password}
  - call RCP.COMMON.WORKDAY.UPLOAD_RESUME file={resume}
  - call RCP.COMMON.WORKDAY.FILL_MY_INFORMATION first_name={first_name} last_name={last_name} phone={phone}
  - call RCP.COMMON.WORKDAY.ADD_EXPERIENCE company={job1_company} title={job1_title}
  - confirm "The application is filled in. Review it in the browser. Submit?"
  - call RCP.COMMON.WORKDAY.SUBMIT_APPLICATION
check:
  - step 6 succeeded
state: observed
verified: {count: 0, last: 2026-11-13}
```

The shared side, public cards with no personal data (illustrative; the ids are made up):

```yaml
id: ELEM.WIN.WORKDAY.PHONE
applies:
  os: WIN >=10.0
  app: WORKDAY any
  lang: en-US
purpose: The phone number field on the "My Information" page
parent: ELEM.WIN.WORKDAY.MY_INFORMATION
locators:                                     # tried in order; a later one working is reported back
  - ax id=phone-number
  - ax role=Edit name="Phone Number"
  - text "Phone Number" below
---
id: RCP.WIN.WORKDAY.SUBMIT_APPLICATION
applies:
  os: WIN >=10.0
  app: WORKDAY any
requires:
  - ELEM.WIN.WORKDAY.REVIEW_PAGE visible
steps:
  - click! ELEM.WIN.WORKDAY.SUBMIT_BUTTON      # ! = external effect; always needs your authorization
  - wait ELEM.WIN.WORKDAY.SUBMITTED_NOTICE shown 30s
check:
  - ELEM.WIN.WORKDAY.SUBMITTED_NOTICE visible
ends_at: ELEM.WIN.WORKDAY.SUBMITTED_NOTICE
```

**What this example still needs.** Two things are not modelled yet: a site inside a browser as a first-class "app", and choosing a card *by company*. Today a variant card is chosen by app version, UI language and vendor ROM. Until a per-site dimension is added, company differences are handled by ordered locators and `if` guards, not by per-company variants.

## A second example: expense claims on a company portal

**The pain.** Every month: find the invoice e-mail, download the PDF, open the company's approval system, upload, pick the project, pick the category, submit. The system usually has no API, so it is all clicking.

**What MuscleMemory adds:**

- **One flow across two apps.** The mail client saves the invoice; the approval system receives it.
- **The password stays on your machine.**
- **It stops before submitting** so you can check the amount, project and category.
- **When the portal is redesigned, the AI takes over once and proposes the repair.**

**The limit.** Every company's approval system is different, so these cards mostly belong in a team-internal library, not the public one. That works today: a library is just a git repository with a `cards/` folder, and `KB_ROOT` points at it.

## Also a good fit

- Expense tools such as Expensify or Concur
- Entering data into older enterprise software such as SAP GUI
- Listing the same product on several marketplaces
- Filing a daily work log in a team chat app

The pattern is the same each time: a GUI with no usable API, the same steps every time, small differences between versions or sites.

---

## How it works

```
First time:  the AI looks, explores, finishes the task  ──►  distilled into experience cards
Afterwards:  look up the cards for this environment      ──►  a program runs them (fast, zero tokens)
When broken: the app changed, a locator fails            ──►  hand over to the AI ──► it proposes a fix ──► runs directly again
```

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
- **Flows.** Chain several apps into one errand. Data passing, checkpoints, resume and schedules are built in.
- **Security first.** The grammar is the whitelist: there is no way to spell "run a command" or "open a URL". External experience is quarantined until someone reproduces it. Unattended jobs only run the exact version you approved. Passwords only ever flow into an input field.
- **Global, with first-class Chinese support.** The repository stores an English canonical form; every field name, verb and keyword also has a Chinese alias (`点击! ELEM...`, `步骤:`, `状态: 稳定`), and aliases are matched in all languages.

## Try the engine in two minutes

No device needed. The Workday and expense cards above are not written yet, so the runnable demo uses a simulated chat app. It exercises the same machinery: a recipe, a `!` confirmation, a version variant, a hand-off, and a flow.

```bash
git clone https://github.com/cxbrucewayen/MuscleMemory && cd MuscleMemory
pip install -e .          # skip both lines if you ran `kb setup`: cd ~/.cua-experience/library

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

The same reference resolved to a different element card. That variant has only been seen once, so the program refuses to run it unattended and leaves it to the AI (`kb run --force ...` performs the trial run).

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

`kb setup` (see [Install](#install)) is all it takes. After a restart the agent has the `cua-experience` skill and these MCP tools: `kb_bundle`, `kb_symptom`, `kb_screen`, `kb_outline`, `kb_resolve`, `kb_goto`, `kb_run`, `kb_lock`, `kb_unlock`, `kb_type_secret`, `kb_propose` and `kb_flow`.

To wire it up by hand instead, start the server with `kb --root <library> mcp` over stdio and give the agent the skill: [English](./src/musclememory/skill/SKILL.md), [中文](./src/musclememory/skill/SKILL.zh-CN.md).

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
| `kb setup` | install the skill and register the MCP server (`--uninstall` to undo) |
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

**"Why not write one Skill per app?"** That works at small scale. But apps keep changing: the same button is located differently in two versions, and differently again in the Chinese and English UI. A hand-written Skill cannot tell which piece of experience applies to the current version or whether it is still right, and it cannot run without a model. Those three things are what MuscleMemory is for.

## Repository layout

```
├── README.md  README.zh-CN.md  LICENSE
├── docs/
│   ├── en/            # DESIGN.md (the specification), SECURITY.md (security design), STATUS.md
│   └── zh-CN/         # the same three documents in Chinese
├── src/musclememory/  # the implementation (Python, one dependency: PyYAML)
│   └── skill/         # the agent skill and its reference sheet, in English and Chinese
├── cards/             # the public card library (platform/app.yaml)
├── index/             # generated retrieval index
├── examples/demo/     # a complete demo library, simulated apps and flows
├── tests/
├── proposals/         # pending proposals (quarantine); created on demand
├── flows/  runs/      # local only, git-ignored: your flows, run records, locks
```

Where to start:

| You want to | Read |
|---|---|
| understand the project | this file |
| work on the engine | [design](./docs/en/DESIGN.md), then [security design](./docs/en/SECURITY.md) and [status](./docs/en/STATUS.md) |
| contribute cards | "Contributing experience" below, then the [reference sheet](./src/musclememory/skill/REFERENCE.md) |
| know what an agent is told | the [skill](./src/musclememory/skill/SKILL.md) |

Every document exists in English and Chinese and the two are maintained together.

## Security

An open experience library is a **supply chain that AIs and programs execute**, so security is a premise of the design rather than a feature added later:

- **Cards are data, not instructions.** No commands, no links, no code; steps can only use whitelisted verbs, and `type` only accepts parameters, never literal text.
- **External experience is quarantined.** Machine check, human reading, **independent reproduction** in the declared environment, then a signed merge, before any agent reads it.
- **Unattended jobs only run the version you approved.** A change to the flow or to any card it can reach pauses the job until you approve again.
- **Personal data stays on your machine.** Flows, run records, screenshots and secrets are local; personal data is rejected from the public library.
- **Passwords only flow into input fields.** The AI never sees them; logs and hand-off packages show `***`.

Full design: [security design](./docs/en/SECURITY.md). To report a vulnerability, follow the [security policy](./.github/SECURITY.md): report it privately, not in a public issue.

## Contributing experience

1. Let your agent call `kb_propose` when a task is done, or write a proposal by hand following the [reference sheet](./src/musclememory/skill/REFERENCE.md). Chinese or English are both fine.
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
- [ ] Verify the `cua-driver` and `adb` adapters on real devices
- [ ] Sites inside a browser as first-class apps, and choosing cards per site (needed for the Workday example)
- [ ] The first real card sets: a Workday application, an expense claim
- [ ] External contributions: behaviour summaries for reviewers, reproduction workflow, signed releases, Gitee mirror
- [ ] HarmonyOS (`hdc`) and iOS drivers; localised CLI messages; semantic retrieval when the library grows

## Acknowledgements

MuscleMemory builds on the computer-use capabilities of [Cua](https://github.com/trycua/cua). It is an independent community project and is not affiliated with Cua.

Workday, Expensify, Concur and SAP are trademarks of their respective owners, named here only to describe the tasks. This project is not affiliated with or endorsed by any of them.

## License

[MIT](./LICENSE)
