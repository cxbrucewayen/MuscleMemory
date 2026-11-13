# MuscleMemory · 肌肉记忆

[English](./README.md) | **简体中文**

[![CI](https://github.com/cxbrucewayen/MuscleMemory/actions/workflows/ci.yml/badge.svg)](https://github.com/cxbrucewayen/MuscleMemory/actions/workflows/ci.yml)

**每个月的发票报销，教会 AI 一次就够了。**

MuscleMemory 是给 AI 智能体的肌肉记忆：第一次由 AI 摸索着把事情办成，并把做法留成一张张可以审核的小卡片；之后由程序照着卡片直接完成；只有界面变了，AI 才重新介入。

> **项目状态：可用的基线版本（v0.1）。** 引擎已经做完并有测试：`kb` 命令行、检查器、执行器、事务流程、密钥管理、MCP 服务，都在内置的界面模拟器上跑通。**下面展示的报销卡片和 Workday 卡片目前还不在库里。** 它们说明这个项目是用来做什么的，也是我们最想和贡献者一起做出来的第一批卡片。真实设备的驱动（`adb`、`cua-driver`）已写好，但尚未验证。详见[实现状态](./docs/zh-CN/STATUS.md)。

## 一键安装

一行命令装好 `kb` 命令行、智能体技能和 MCP 服务：

```bash
pip install git+https://github.com/cxbrucewayen/MuscleMemory && kb setup
```

`kb setup` 只做三件事，改动了哪些文件都会逐条列出：

1. **经验库。** 你当前就在某个经验库里，就用它；否则把本仓库克隆到 `~/.cua-experience/library`。
2. **技能。** 把 `cua-experience` 技能复制到 `~/.claude/skills/`。系统语言是中文就装中文版，否则装英文版（也可以用 `--lang zh-CN` / `--lang en` 指定）。
3. **MCP 服务。** 在检测到的智能体客户端里注册 `musclememory`：Claude Code、Cursor、Claude Desktop。其他支持 MCP 的客户端，它会打印一段配置，粘贴进去即可。

接着选一次驱动，告诉它怎么操作你的软件：`kb setup --driver adb`（Android）或 `kb setup --driver cua`（桌面，实验性）。`kb setup --dry-run` 只预览不改动，`kb setup --uninstall` 可以把技能和 MCP 注册再移除。

访问 GitHub 不稳定时，可以先把仓库下载到本地，在仓库目录里运行 `pip install . && kb setup`，这样不需要再联网克隆。

---

## 例一：发票报销

**痛点。** 几乎每个上班族每个月都要做一遍：翻邮箱找发票、下载 PDF、打开公司 OA、上传、选项目、填类目、提交。OA 通常不开放接口，只能一下一下地点，又多又碎。

**只靠 AI 为什么不够。** AI 能替你点，但每次都从头学一遍这套 OA：截图、猜按钮、试错。慢、贵，而且每次错的地方还不一样。

**用 MuscleMemory：**

- **一个流程跨两个软件。** 邮箱客户端把发票存下来，OA 接着用这个文件，中间不用你倒手。
- **密码只存在本机。** 由执行器代为输入，AI 拿不到明文，日志里只显示 `***`。
- **提交前停下来让你核对。** 流程在提交前有一个人工检查点；“提交”这一步本身带 `!`，永远需要你点头。
- **OA 改版后不用你重新教。** 程序找不到按钮就停下，把现场交给 AI；AI 办完这一次，并提交修复，审核通过后又能由程序直接运行。

你自己这一侧，只在本机（`flows/expense-claim.flow.yaml`）：

```yaml
format: 6
id: FLOW.EXPENSE_CLAIM
aliases:
  zh: [发票报销, 报销]
  en: [expense claim]
trigger: [manual]
workdir: <你的报销文件夹>
inputs:
  subject: <发票邮件的主题关键词>
  user: <OA 用户名>
  password: "{secret:OA_PASSWORD}"            # 用 kb secret set 存在本机，AI 看不到
  project: <项目名称>
  category: 差旅费
secrets: [OA_PASSWORD]
steps:
  - call RCP.COMMON.MAIL.SAVE_INVOICE subject={subject} save_as={run_dir}/invoice.pdf -> {invoice}
  - wait_file {invoice} 30s
  - call RCP.COMMON.OA.LOGIN user={user} password={password}
  - call RCP.COMMON.OA.FILL_CLAIM invoice={invoice} project={project} category={category}
  - confirm "报销单已填好。请在 OA 里核对金额、项目和类目。确认提交吗？"
  - call RCP.COMMON.OA.SUBMIT_CLAIM
check:
  - step 6 succeeded
state: observed
verified: {count: 0, last: 2026-11-13}
```

软件这一侧是卡片，不含任何个人信息（示意，编号是虚构的）：

```yaml
id: RCP.WIN.OA.SUBMIT_CLAIM
applies:
  os: WIN >=10.0
  app: OA >=8.0
requires:
  - ELEM.WIN.OA.CLAIM_FORM visible
steps:
  - click! ELEM.WIN.OA.SUBMIT_BUTTON           # ! 表示会产生外部影响，执行前必须经你授权
  - wait ELEM.WIN.OA.SUBMITTED_NOTICE shown 15s
check:
  - ELEM.WIN.OA.SUBMITTED_NOTICE visible
ends_at: ELEM.WIN.OA.SUBMITTED_NOTICE
---
id: ELEM.WIN.OA.SUBMIT_BUTTON@9
applies:
  os: WIN >=10.0
  app: OA >=9.0
  lang: zh-CN
locators:                                      # OA 9 改版后按钮变了：只记录变化的部分
  - ax role=Button name="提交审批"
  - text "提交审批" self
evidence: on 9.0 the old button id is gone; the Button named by its label worked first try
```

**局限。** 每家公司的 OA 都不一样，这类卡片多数只适合在团队内部共享，很难放进公开库。这一点今天就能做到：经验库就是一个带 `cards/` 目录的 git 仓库，把 `KB_ROOT` 指向你们团队自己的仓库即可。一个同事修好，全组受益。

## 例二：在 Workday 上投简历

**痛点。** 在海外求职，这是公认的折磨：简历上传了，还得把姓名、电话、每段工作经历、每段教育经历重新填一遍；换一家公司，再来一遍。每家公司都有自己的 Workday 站点和账号，表单几乎一样，又总有一点不同。

**为什么它最适合开源共享。** 表单的结构不含个人信息：卡片只记录“电话”那一栏在哪里、怎么确认这一页存上了。你的简历内容只在你本机的流程文件里。所以“一个人修好，所有人受益”在这里最说得通。

**各家表单的小差异怎么处理。** 一个栏位可以保存多种定位方式，按顺序尝试；只有部分公司才有的栏位，用 `if … visible` 包起来。遇到卡片对付不了的表单，AI 办完这一次投递，并提交修复。

**这个例子还差什么。** 有两件事目前还没有建模：把浏览器里的一个网站当作一等的“软件”，以及**按公司**挑选卡片。现在的变体卡是按软件版本、界面语言、厂商系统来选的。在加上“站点”这个维度之前，各家公司的差异靠多候选定位和 `if` 条件来处理，而不是每家公司一张变体卡。

流程和卡片的写法见[英文版 README](./README.md#the-example-applying-for-jobs-on-workday)。

## 其他适合的场景

- 电商在淘宝、拼多多、抖店等多个平台同步上架同一件商品
- 把工作日志填进钉钉或飞书的日报
- Expensify、Concur 这类报销工具
- 把数据录进 SAP GUI 之类的老旧企业软件

共同点是：界面没有可用的接口，每次步骤都一样，不同版本或不同站点之间只有小差异。

---

## 它是怎么工作的

```
第一次：AI 看屏幕、摸索、完成任务   ──►  提炼成经验卡片
之后：  按当前环境查出卡片          ──►  程序直接运行（快、零 token）
坏了：  软件改版、定位失败          ──►  交给 AI 修复 ──► 提交新的经验 ──► 又能直接运行
```

| | 比喻 | 解决的问题 |
|---|---|---|
| MCP | 插座 | AI 怎么调用外部工具 |
| Skill | 说明书 | 某类任务该怎么做 |
| [Cua](https://github.com/trycua/cua) | 手 | AI 怎么看屏幕、点鼠标、敲键盘 |
| **MuscleMemory** | **熟练** | **某个软件的某个版本里，这件事具体怎么做最稳，而且越用越熟** |

它们不是竞争关系。MuscleMemory 通过 **MCP** 提供工具，用一个 **Skill** 教智能体如何使用经验库，再借助 **Cua**、**adb** 这类驱动动手操作。

## 核心特性

- **跨系统、跨软件、跨版本**：系统对应目录，软件对应文件，版本写在卡片的适用范围里。引用时不写版本，由解析器挑出最匹配的那张卡；新版本只需记录变化的部分（@ 变体）。
- **AI 读得懂，程序跑得动**：步骤使用固定的小语法。稳定的经验由 `kb run` 直接执行，不调用大模型。
- **失效能自愈**：每个元素保存多种定位方式和一句“作用”描述。全部定位失败时，执行器把结构化的交接包交给 AI；AI 完成任务后提交一个变体。
- **快速检索**：先按环境把范围缩小到几个文件，再从任务、报错、界面三个入口之一定位。相关卡片打包返回，体积可控。
- **界面导航**：没有副作用的配方构成界面之间的导航图，执行前自动走到需要的界面。
- **事务流程**：把多个软件串成一件事。支持数据传递、断点恢复和定时运行。
- **安全优先**：语法本身就是白名单，根本写不出“执行命令”“打开网址”。外部经验先进隔离区，有人复现后才能入库。无人值守只执行你亲自批准过的那一版。密码永远只流向输入框。
- **面向全球，完整支持中文**：仓库统一存英文规范形式；所有字段名、动词、关键字都有中文别名（`点击! ELEM...`、`步骤:`、`状态: 稳定`），两种写法完全等价，检索时各语言的别名都参与匹配。

## 两分钟试一下引擎

不需要任何设备。上面的报销卡片和 Workday 卡片还没有写出来，所以可以直接运行的演示用的是一个模拟的聊天软件。它走的是同一套机制：配方、`!` 确认、版本变体、交接给 AI、事务流程。

```bash
git clone https://github.com/cxbrucewayen/MuscleMemory && cd MuscleMemory
pip install -e .          # 已经运行过 kb setup 的话，这两行换成：cd ~/.cua-experience/library

export KB_ROOT=examples/demo
export KB_DRIVER=sim:examples/demo/sim/windows-4.1.yaml     # 模拟的 Windows 版“DemoChat 4.1”

kb check                                   # 检查整个库（格式、语法、安全扫描）
kb find 改备注                              # 取回这个任务的经验包；英文也行：kb find "rename remark"
kb run RCP.COMMON.DEMOCHAT.RENAME_REMARK contact=Alice remark=Boss
```

`kb run` 执行到唯一带 `!` 的步骤前会停下来问你：

```
! This step has an external effect:
  RCP.WIN.DEMOCHAT.RENAME_REMARK: key! Enter
  Allow it? [y/N] y
{ "status": "ok", "recipe": "RCP.WIN.DEMOCHAT.RENAME_REMARK", "message": "check passed", ... }
```

现在假设软件升级了。4.2 版里，备注从按钮变成了输入框：

```bash
export KB_DRIVER=sim:examples/demo/sim/windows-4.2.yaml
kb find 改备注
```

```
env: WIN 10.0.22631 / DEMOCHAT 4.2.0 / sim 0.1.0 / en-US / DPI 100%
directly runnable: no (ELEM.WIN.DEMOCHAT.REMARK_ROW@4.2 is observed, needs at least reproduced)
├─ RCP.WIN.DEMOCHAT.RENAME_REMARK               match stable
├─ ELEM.WIN.DEMOCHAT.REMARK_ROW@4.2             match observed (variant 4.2 selected)
...
```

同一个引用解析到了另一张元素卡。这个变体只被观察到一次，所以程序拒绝自己直接运行，而是交给 AI（`kb run --force ...` 可以做一次试运行）。

还可以试试：

```bash
kb symptom 点击资料卡没有反应                          # 按症状查坑
kb --lang zh-CN show RCP.WIN.DEMOCHAT.RENAME_REMARK    # 用中文显示同一张卡
kb outline                                             # 范围内每张卡一行摘要

# 一个事务流程：读 CSV，在聊天软件里发文件，再回填 CSV。
# 它会修改 work/tasks.csv，所以请在副本上运行：
cp -r examples/demo /tmp/mm-demo
kb --root /tmp/mm-demo --driver sim:/tmp/mm-demo/sim/windows-4.1.yaml flow run FLOW.WEEKLY_REPORT
```

## 接真实设备

```bash
kb --driver adb env            # Android：adb + uiautomator（指定设备写 adb:<序列号>）
kb --driver cua env            # 桌面软件：通过 cua-driver（实验性适配）
```

| 驱动 | 平台 | 状态 |
|---|---|---|
| `sim:<文件.yaml>` | 模拟 | 测试和演示在用 |
| `adb[:序列号]` | Android | 只用系统自带工具实现；尚未在 CI 里接真机验证 |
| `cua` | Windows、macOS、Linux | 实验性；按 cua-driver 公开的工具契约编写，尚未接真实驱动运行 |
| 鸿蒙（`hdc`）、iOS | | 未实现 |

默认值可以写在 `~/.cua-experience/config.yaml` 里（`driver: adb`、`lang: zh-CN`、`secret_backend: env`）。

## 给 AI 智能体用

运行 `kb setup`（见[一键安装](#一键安装)）就够了。重启客户端后，智能体就有了 `cua-experience` 技能和这些 MCP 工具：`kb_bundle`、`kb_symptom`、`kb_screen`、`kb_outline`、`kb_resolve`、`kb_goto`、`kb_run`、`kb_lock`、`kb_unlock`、`kb_type_secret`、`kb_propose`、`kb_flow`。

想手动接入也可以：用 `kb --root <经验库> mcp` 以 stdio 方式启动服务，再把技能文件交给智能体：[中文](./src/musclememory/skill/SKILL.zh-CN.md)、[English](./src/musclememory/skill/SKILL.md)。

带 `!` 的步骤：客户端支持 MCP elicitation 时，由服务直接向用户确认；不支持时，`kb_run` 什么都不执行，只返回 `!` 步骤清单和一个一次性令牌，智能体必须先问过用户才能带着令牌再调用。

## 命令一览

| 命令 | 作用 |
|---|---|
| `kb find <任务>` / `symptom <报错>` / `screen <界面特征>` / `outline` | 按任务、报错、界面检索，或列出范围内全部卡片 |
| `kb resolve <id>` / `show <id> --lang zh-CN` | 当前环境该用哪张卡 / 显示一张卡 |
| `kb run <id> 名=值 ...` / `goto <界面>` | 执行配方 / 导航到某个界面 |
| `kb check` / `fmt` / `index` / `migrate` | 检查、规范化、重建索引、升级格式 |
| `kb propose [文件]` / `merge <提案>` | 提交经验 / 维护者把审核通过的提案并入卡片库 |
| `kb secret set\|list\|rm\|check` | 密钥，存放在仓库之外 |
| `kb flow run\|resume\|approve\|list\|tick` | 事务流程；`tick` 运行到点的定时任务（交给 cron 或任务计划程序定期调用） |
| `kb setup` | 安装技能并注册 MCP 服务（`--uninstall` 撤销） |
| `kb env` / `kb mcp` | 打印环境快照 / 以 stdio 方式提供 MCP 服务 |

`--root`、`--driver`、`--env`、`--lang` 对所有命令有效；`KB_ROOT`、`KB_DRIVER`、`KB_LANG` 可设默认值。

## 和其他方案有什么不同

| | Skill | 传统 RPA | AI 记忆（如 mem0） | **MuscleMemory** |
|---|---|---|---|---|
| 记录什么 | 通用做法 | 录制的脚本 | 关于用户和对话的事实 | 具体软件、具体版本的操作经验 |
| 由谁维护 | 人手写 | 人录制 | 自动 | AI 积累，人审核 |
| 版本适配 | 无 | 无，一改版就坏 | 不适用 | 按版本范围自动匹配，失效能自愈 |
| 可信度 | 写的人说了算 | 录制时可用 | 无验证 | 有证据、有状态，独立复现后才升级 |
| 能否脱离大模型执行 | 不能 | 能 | 不能 | 稳定后能 |
| 能否共享 | 能 | 难 | 不适合 | 能，开源经验库 |

**“给每个软件写一个 Skill 不就行了？”** 规模小时可以。但软件一直在更新：同一个按钮在两个版本里定位方式不同，中文界面和英文界面也不同。手写的 Skill 无法判断哪条经验适用于当前版本、还对不对，也不能脱离大模型直接执行。MuscleMemory 解决的正是这三件事。

## 仓库结构

```
├── README.md  README.zh-CN.md  LICENSE
├── docs/
│   ├── zh-CN/         # DESIGN.md（设计规格）、SECURITY.md（安全设计）、STATUS.md（实现状态）
│   └── en/            # 同样三份文档的英文版
├── src/musclememory/  # 实现（Python，只依赖 PyYAML）
│   └── skill/         # 给智能体的技能和语法速查，中英文各一份
├── cards/             # 公开的卡片库（平台/软件.yaml）
├── index/             # 工具生成的检索索引
├── examples/demo/     # 完整的演示库：卡片、模拟软件、事务流程
├── tests/
├── proposals/         # 待审核的提案（隔离区），用到时才创建
├── flows/  runs/      # 只在本地、已加入 .gitignore：你的流程、运行记录、锁
```

从哪里读起：

| 你想 | 读 |
|---|---|
| 了解项目 | 本文件 |
| 参与开发 | [设计规格](./docs/zh-CN/DESIGN.md)，然后是[安全设计](./docs/zh-CN/SECURITY.md)和[实现状态](./docs/zh-CN/STATUS.md) |
| 贡献卡片 | 下面的“贡献经验”，然后是[语法速查](./src/musclememory/skill/REFERENCE.zh-CN.md) |
| 知道智能体被告知了什么 | [技能文件](./src/musclememory/skill/SKILL.zh-CN.md) |

所有文档都有中文和英文两个版本，同步维护。

## 安全

开源的经验库是一条**会被 AI 和程序照着执行的供应链**，所以安全是设计的前提，不是附加功能：

- **卡片是数据，不是指令。** 卡片里没有命令、没有链接、没有代码；步骤只能使用白名单中的动词，`type` 只接受参数，不接受写死的文字。
- **外部经验先进隔离区。** 经过机器检查、人工阅读、在声明的环境里**独立复现**、签名合并之后，才会被智能体读到。
- **无人值守只做你批准过的那一版。** 流程本身或它能触及的任何一张卡被修改，任务都会暂停，等你重新确认。
- **个人信息不出本机。** 流程、运行记录、截图、密钥都只留在你的电脑上；公开库拒收个人信息。
- **密码永远只流向输入框。** AI 拿不到明文，日志和交接包里一律显示为 `***`。

完整设计见[安全设计](./docs/zh-CN/SECURITY.md)。发现安全问题，请按[安全策略](./.github/SECURITY.md)私下报告，不要公开提交 issue。

## 贡献经验

1. 让你的智能体在任务结束后调用 `kb_propose`，或者照[语法速查](./src/musclememory/skill/REFERENCE.zh-CN.md)手写提案。中文、英文都可以。
2. 运行 `kb fmt && kb check`，全部通过后再提交 PR。
3. 证据里只写结构（控件、报错码、现象），**不写人名、聊天内容、本机路径、密码**，用 `<CONTACT_A>`、`<USER_HOME>` 这类占位符代替。
4. 维护者会在声明的版本和界面语言环境里独立复现。通过后以“观察”状态合并，之后随着更多人复现逐步升级。

最有价值的贡献依次是：**坑（FAIL）**、**版本变体**、**新系统上的做法**。

## 路线图

- [x] YAML 解析器、`kb fmt`、`kb check`（格式、语法、安全扫描）
- [x] 版本解析与检索（`kb resolve`、`kb_bundle`），MCP 服务
- [x] 执行器 `kb run`、交接给 AI、界面导航
- [x] 事务流程、密钥管理、定时运行（`kb flow tick`）
- [x] 第二个版本、第二个系统，已在模拟器上演示（界面语言匹配由测试覆盖）
- [ ] 在真机上验证 `cua-driver` 和 `adb` 两个驱动
- [ ] 把浏览器里的网站当作一等的软件，并支持按站点挑选卡片（Workday 这个例子需要）
- [ ] 第一批真实的卡片：一套报销、一套 Workday 投递
- [ ] 开放外部贡献：给审核者的行为摘要、独立复现流程、签名发布、Gitee 镜像
- [ ] 鸿蒙（`hdc`）与 iOS 驱动；命令行提示的中文化；卡片多了以后加语义检索

## 致谢

本项目基于 [Cua](https://github.com/trycua/cua) 的计算机使用能力构建，是独立的社区项目，与 Cua 官方无隶属关系。

文中提到的 Workday、Expensify、Concur、SAP、淘宝、拼多多、抖店、钉钉、飞书均为各自所有者的商标，这里只用来描述任务。本项目与它们没有隶属或合作关系。

## 许可证

[MIT](./LICENSE)
