# 实现状态

[English](../en/STATUS.md) | **简体中文**

v0.1 基线实现了什么、与[设计](./DESIGN.md)和[安全设计](./SECURITY.md)有哪些出入、还缺什么。

## 已实现并有测试

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
| 安装器 | `install.py`、`skill/` | `kb setup` 安装技能（中文或英文），并在 Claude Code、Cursor、Claude Desktop 里注册 MCP 服务；Claude Code 用真实命令行验证过，另外两个只按其配置文件格式写入 |

测试（`tests/`）在模拟器上跑通整条链路，并覆盖反面情况：伪造确认令牌、已批准流程的卡片被篡改、密钥出现在日志里、收件人不在 `authorize` 中。

## 尚未在真机上验证

- **`adb` 驱动**：用系统自带命令实现（`uiautomator dump`、`input`、`monkey`、`dumpsys`），在本仓库里没有接过真机。输入非 ASCII 文字需要设备上装有 ADBKeyBoard 输入法；不支持 `clipboard` 步骤。
- **`cua-driver` 适配**：按驱动公开的工具契约（contract 0.8.0，技能包 0.47.x）编写，通过 MCP 与 `cua-driver mcp` 通信，没有接过真实驱动。契约里的元素没有 automation id，所以 `ax id=` 定位在这个驱动上匹配不到。软件版本的读取只是尽力而为。
- **“用户正在使用电脑”的判断**（`when_busy`）：只有模拟器会上报。`adb` 和 `cua` 下始终视为用户空闲。

## 与设计有出入、或设计没写明而由实现决定的地方

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
12. **仓库结构**：设计里的目录树把 `DESIGN.md`、`SKILL.md`、`SECURITY.md` 放在根目录。这里文档放在 `docs/<语言>/` 下，技能随 Python 包发布（`src/musclememory/skill/`），这样 `kb setup` 才能安装它；技能自带一份简短的 `REFERENCE.md`，不再让智能体去读完整规格。
13. **本地统计**写在 `runs/stats.json`；每周汇总成一条 `update` 提案的功能未实现。

## 未实现

- “疑似人名”的隐私规则、新贡献者限流、给审核者的行为摘要、签名发布、Gitee 镜像（SECURITY 的闸二、闸三）
- **把浏览器里的网站当作一等的软件，以及按站点挑选卡片。** `applies` 按系统、软件版本、驱动、界面语言、显示、厂商系统来选卡，没有“站点”或“租户”这个维度，所以 README 里的 Workday 例子目前做不到每家公司一张变体卡；站点之间的差异靠多候选定位和 `if … visible` 条件处理。加这个维度需要改 `DESIGN.md` 里的卡片格式
- 鸿蒙（`hdc`）与 iOS 驱动；程序可用的 `vision` 定位（按设计它只给 AI 用）
- 语义检索；命令行提示的中文化（卡片内容和字段名是双语的，命令行提示目前只有英文）
- 每月维护的自动化（升级、清理）和 `kb migrate` 的迁移规则（目前只有格式 6）
