# MuscleMemory · 肌肉记忆

[English](./README.md) | **简体中文**

[![CI](https://github.com/cxbrucewayen/MuscleMemory/actions/workflows/ci.yml/badge.svg)](https://github.com/cxbrucewayen/MuscleMemory/actions/workflows/ci.yml)

> **给 AI 智能体的肌肉记忆。** 第一次靠 AI 摸索，之后由程序照着经验直接完成；只有界面变了，AI 才重新介入。

**项目状态：可用的基线版本（v0.1）。** `kb` 命令行、检查器、解析器、执行器、事务流程、密钥管理和 MCP 服务都已实现，并在内置的界面模拟器上通过测试。真实设备的驱动已有 Android（`adb`）和桌面（`cua-driver`，实验性）两种，但还没有在本仓库的 CI 里接真机跑过。公开的卡片库目前几乎是空的：经过验证的卡片要通过提案逐步进来。哪些做了、哪些没做，见 [docs/STATUS.md](./docs/STATUS.md)。

---

## 为什么需要它

让 AI 操作电脑和手机已经可行，但每一次都是从零开始：截图、理解界面、猜按钮、试错。

- **慢、贵**：同一件事，第一百次和第一次一样费时、一样耗 token。
- **不稳定**：今天点对了，明天软件一更新就点错。
- **不积累**：踩过的坑下次还会再踩，你踩过的坑别人也要再踩一遍。

传统的 RPA 脚本跑得快，但靠人录制和维护，界面一变就坏。

**MuscleMemory 把两者结合起来：AI 负责探索和修复，经验负责复用和执行。**

```
第一次：AI 看屏幕、摸索、完成任务   ──►  提炼成经验卡片
之后：  按当前环境查出卡片          ──►  程序直接运行（快、零 token）
坏了：  软件改版、定位失败          ──►  交给 AI 修复 ──► 提交新的经验 ──► 又能直接运行
```

## 它是什么

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
- **事务流程**：把多个软件串成一件事，例如“任务清单 → 汇总 → 发给老板 → 回填清单”。支持数据传递、断点恢复和定时运行。
- **安全优先**：语法本身就是白名单，根本写不出“执行命令”“打开网址”。外部经验先进隔离区，有人复现后才能入库。无人值守只执行你亲自批准过的那一版。密码永远只流向输入框。
- **面向全球，完整支持中文**：仓库统一存英文规范形式；所有字段名、动词、关键字都有中文别名，检索时各语言的别名都参与匹配。

## 两分钟上手

不需要任何设备：演示库在一个模拟的聊天软件上运行。

```bash
git clone https://github.com/cxbrucewayen/MuscleMemory && cd MuscleMemory
pip install -e .

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

## 一张卡片

经验以卡片的形式保存，格式是标准 YAML：

```yaml
id: RCP.WIN.DEMOCHAT.RENAME_REMARK        # 类型.平台.软件.名称
applies:
  os: WIN >=10.0
  app: DEMOCHAT >=4.0
steps:
  - call RCP.WIN.DEMOCHAT.OPEN_PROFILE contact={contact}
  - click ELEM.WIN.DEMOCHAT.REMARK_ROW
  - wait ELEM.WIN.DEMOCHAT.REMARK_EDIT shown 5s
  - key Ctrl+A
  - call RCP.COMMON.INPUT_TEXT text={remark}
  - key! Enter                            # ! 表示会产生外部影响，执行前需要授权
check:
  - ELEM.WIN.DEMOCHAT.PROFILE_REMARK value == {remark}
ends_at: ELEM.WIN.DEMOCHAT.PROFILE_CARD
state: stable
```

同一句“改备注”，在不同环境下得到不同的做法：

| 当前环境 | 使用的经验 |
|---|---|
| Windows + DemoChat 4.1 | Windows 配方 + 备注行的基础定位 |
| Windows + DemoChat 4.2 | Windows 配方 + 备注行的 `@4.2` 变体 |
| Android + DemoChat 5.0 | 还没有配方 → AI 探索，完成后贡献 `RCP.ANDROID.DEMOCHAT.RENAME_REMARK` |

卡片也可以全用中文写（`点击! ELEM...`、`步骤:`、`状态: 稳定`），两种写法完全等价，`kb fmt` 会统一转成规范形式。

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

把 MCP 服务注册到你的智能体，例如：

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

再把 [`SKILL.md`](./SKILL.md)（[英文版](./docs/en/SKILL.md)）交给它。工具有：`kb_bundle`、`kb_symptom`、`kb_screen`、`kb_outline`、`kb_resolve`、`kb_goto`、`kb_run`、`kb_lock`、`kb_unlock`、`kb_type_secret`、`kb_propose`、`kb_flow`。

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

**“给每个软件写一个 Skill 不就行了？”** 规模小时可以。但软件一直在更新：同一个按钮在 4.1 和 4.2 里定位方式不同，中文界面和英文界面也不同。手写的 Skill 无法判断哪条经验适用于当前版本、还对不对，也不能脱离大模型直接执行。MuscleMemory 解决的正是这三件事。

## 仓库结构

```
├── README.md  README.zh-CN.md
├── DESIGN.md          # 设计规格：卡片格式、步骤语法、解析、检索、执行、事务流程
├── SECURITY.md        # 安全设计：投毒、注入、泄露、无人值守劫持的防御
├── SKILL.md           # 给 AI 智能体的技能
├── docs/en/           # 以上三份文档的英文翻译
├── docs/STATUS.md     # 这个基线实现了什么、与设计有哪些出入、还缺什么
├── src/musclememory/  # 实现（Python，只依赖 PyYAML）
├── cards/             # 公开的卡片库（平台/软件.yaml）
├── index/             # 工具生成的检索索引
├── examples/demo/     # 完整的演示库：卡片、模拟软件、事务流程
├── tests/
├── proposals/         # 待审核的提案（隔离区），用到时才创建
├── flows/  runs/      # 只在本地、已加入 .gitignore：你的流程、运行记录、锁
```

从哪里读起：想了解项目读本文件；想参与开发先读 `DESIGN.md` 再读 `SECURITY.md`；想贡献经验看下面的“贡献经验”；AI 智能体读 `SKILL.md`。

## 安全

开源的经验库是一条**会被 AI 和程序照着执行的供应链**，所以安全是设计的前提，不是附加功能：

- **卡片是数据，不是指令。** 卡片里没有命令、没有链接、没有代码；步骤只能使用白名单中的动词，`type` 只接受参数，不接受写死的文字。
- **外部经验先进隔离区。** 经过机器检查、人工阅读、在声明的环境里**独立复现**、签名合并之后，才会被智能体读到。
- **无人值守只做你批准过的那一版。** 流程本身或它能触及的任何一张卡被修改，任务都会暂停，等你重新确认。
- **个人信息不出本机。** 流程、运行记录、截图、密钥都只留在你的电脑上；公开库拒收个人信息。
- **密码永远只流向输入框。** AI 拿不到明文，日志和交接包里一律显示为 `***`。

完整设计见 [`SECURITY.md`](./SECURITY.md)。发现安全问题，请通过本仓库的 GitHub“Report a vulnerability”私下报告，不要公开提交 issue。

## 贡献经验

1. 让你的智能体在任务结束后调用 `kb_propose`，或者照 `DESIGN.md` 的格式手写提案。中文、英文都可以。
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
- [ ] 第一个真实软件的完整经验：Windows + cua-driver；在真机上验证各驱动
- [ ] 一批经过验证的种子卡片
- [ ] 开放外部贡献：给审核者的行为摘要、独立复现流程、签名发布、Gitee 镜像
- [ ] 鸿蒙（`hdc`）与 iOS 驱动；命令行提示的中文化；卡片多了以后加语义检索

## 致谢

本项目基于 [Cua](https://github.com/trycua/cua) 的计算机使用能力构建，是独立的社区项目，与 Cua 官方无隶属关系。

## 许可证

计划采用 MIT；许可证文件尚未添加。
