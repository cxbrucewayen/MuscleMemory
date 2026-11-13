# 卡片与流程速查

读卡片、写提案、起草流程时需要的全部语法。完整规格是项目仓库里的 `docs/zh-CN/DESIGN.md`。这里没有列出的写法都无法解析，会被拒绝。

## 编号

`类型.平台.软件.名称[@变体]`，只用 ASCII 大写字母、数字和 `_`。

| 类型 | 回答 | 例子 |
|---|---|---|
| `ENV` 环境 | 这个系统能用什么手段，有什么限制 | `ENV.WIN` |
| `APP` 软件 | 怎么认出、怎么启动这个软件 | `APP.WIN.WECHAT` |
| `ELEM` 元素 | 界面或控件在哪里，怎么定位 | `ELEM.WIN.WECHAT.REMARK_ROW` |
| `RCP` 配方 | 一件事怎么做，怎么确认做成了 | `RCP.WIN.WECHAT.RENAME_REMARK` |
| `FAIL` 坑 | 这个症状是什么原因，怎么解决 | `FAIL.WIN.WECHAT.CARD_BEHIND` |

- 平台：`COMMON` `WIN` `MAC` `LINUX` `ANDROID` `IOS` `HARMONY`。平台层的卡没有软件段（`RCP.WIN.INPUT_TEXT`）。
- `COMMON` 配方只写目标（`aliases`、`params`、`goal`、`side_effect`、`output`）；同名的平台配方写做法（`requires`、`steps`、`check`、`ends_at`）。
- `X@标记` 是 `X` 的变体：继承全部字段，只写变了的字段，另外必须自己写 `applies`。
- 引用时永远不带 `@标记`，也不写版本，由解析器挑卡。

## `applies` 适用范围

```yaml
applies:
  os: WIN >=10.0.22000        # 必填：平台 + 版本范围
  app: WECHAT >=4.0 <4.2      # 软件卡必填
  driver: cua-driver >=0.47   # 选填
  lang: zh-CN                 # 定位依赖界面文字时必填
  display: DPI 100%           # 选填
  rom: HyperOS >=1.0          # 选填，Android 类平台
```

范围写法：`any`、`=4.1.2`、`>=4.0`、`>=4.0 <4.2`。新卡只写验证过的版本，例如 `=4.2.0`。

## 步骤

每一步是一个字符串：`动词 对象 [参数]`。

| 动词 | 中文 | 写法 |
|---|---|---|
| `open` | 打开 | `open <APP 编号>` |
| `goto` | 前往 | `goto <界面编号>` |
| `click` `double_click` `right_click` | 点击 双击 右击 | `click <元素>` |
| `scroll` | 滚动 | `scroll <元素> up|down <次数>` |
| `drag` | 拖动 | `drag <元素> to <元素>` |
| `key` | 按键 | `key <组合键>`，如 `Ctrl+A`、`Enter`、`Back` |
| `type` | 输入 | `type {参数}`（只能是参数，不能写死文字） |
| `clipboard` | 写剪贴板 | `clipboard {参数}` |
| `move_window` | 移动窗口 | `move_window <元素> away_from <元素>` |
| `wait` | 等待 | `wait <元素> shown|gone <N>s` |
| `read` | 读取 | `read <元素> text|value -> {变量}` |
| `assert` | 校验 | `assert <条件>` |
| `call` | 调用 | `call <RCP 编号> 名={参数} … [-> {变量}]`（最多 3 层） |
| `if` | 若 | `if <条件> then <单个动作>`（不能嵌套；动作不能是 `if` 或 `call`） |
| `end` | 结束 | `end`（提前跳到 `check`） |

- 动词后加 `!`（`click!`、`key!`）表示这一步有外部影响：发送、提交、删除、付款、签到。有 `!` 步骤的配方，`side_effect` 不能是 `none`。
- `side_effect` 取 `none`、`destructive`、`external`。
- 每张卡最多 12 步、30 行。更长的拆成小配方，用 `call` 串起来。

## 条件

```
<元素> visible | hidden
<元素> text|value == | contains <值>
{变量} == | contains <值>
focus value == <值>
<条件> and <条件>                    # 没有 or
<值> := "字面量" | {参数}
```

`requires` 是执行前要成立的条件，`check` 是执行后要成立的条件，`ends_at` 是做完后界面停在哪个界面。

## 定位

按顺序尝试，最稳定的排前面。

| 方式 | 中文 | 写法 |
|---|---|---|
| `ax` | 无障碍 | `ax [role=] [name=] [id=] [value=] [parent=<元素>] [pick=first|last|N]` |
| `text` | 文字 | `text "<文字>" [self|right_of|left_of|above|below]` |
| `coord` | 坐标 | `coord <元素> <x%> <y%>`（最后手段） |
| `vision` | 视觉 | `vision <描述>`（只给你用，程序会跳过） |

优先用 `id`。用了 `text` 定位，或 `ax` 定位里带 `name=`、`value=` 的卡，必须写 `applies.lang`。没有 `parent` 的元素就是一个界面。

同时满足这几条的配方是导航配方：`side_effect: none`、没有 `!`、没有 `params`、`requires` 里恰好一条“某界面 visible”、写了 `ends_at`。

## 提案

一个 YAML 映射：`update` / `widen` / `variant` / `new` 四选一，加上运行时的 `env`，再加卡片字段。不要写 `state` 和 `verified`。

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

用中文写也完全等价：

```yaml
新增: FAIL.WIN.WECHAT.CARD_BEHIND
环境: {系统: WIN 10.0.22631, 软件: WECHAT 4.1.2, 驱动: cua-driver 0.47.19, 语言: zh-CN}
适用:
  系统: WIN >=10.0
  软件: WECHAT =4.1.2
症状: 点击资料卡没有反应；资料卡在主窗口后面打开
结论: 资料卡与主窗口重叠；点击前先把它移出主窗口范围，点击才会生效
证据: 出现两次；加上移动窗口后同样的点击生效
```

```yaml
update: RCP.WIN.WECHAT.RENAME_REMARK
env: {os: WIN 10.0.22631, app: WECHAT 4.1.2, driver: cua-driver 0.47.19, lang: zh-CN}
evidence: environment matched, all steps ran, check passed
```

证据只写结构：控件、报错码、现象。不写人名、聊天内容、文档正文、真实路径、密钥，用 `<CONTACT_A>`、`<USER_HOME>`、`<SECRET>` 代替。

## 事务流程

流程只在本地，属于个人。它只有 7 个动词，从不点击、从不定位。

| 动词 | 中文 | 写法 |
|---|---|---|
| `call` | 调用 | `call <RCP 编号> 名=值 … [-> {变量}]` |
| `read_table` | 读表 | `read_table {文件} [where <行条件>] -> {变量}` |
| `write_table` | 写表 | `write_table {文件} rows <行条件> set <列> = <值>` |
| `wait_file` | 等待文件 | `wait_file {路径} <N>s` |
| `confirm` | 确认 | `confirm "<给用户看的话>"` |
| `if` | 若 | `if <条件> then <单个动作>` |
| `end` | 结束 | `end` |

```
<列> == | != | contains <值>                   # 行条件
<列> in {表.列}                                # 行条件
{变量} empty | not_empty
{变量} rows > | == | < <数字>
{文件} rows <行条件> column <列> all == <值>
step <N> succeeded
<条件> and <条件>
```

```yaml
format: 6
id: FLOW.WEEKLY_REPORT
aliases:
  zh: [周报, 发总结给老板]
  en: [weekly report]
trigger: [manual, schedule Fri 16:30]
workdir: <用户的文件夹>
inputs:
  tasks: "{workdir}/tasks.csv"
  boss: <收件人的显示名>
  password: "{secret:OA_PASSWORD}"
secrets: [OA_PASSWORD]
when_busy: wait
steps:
  - read_table {tasks} where status == "已完成" and reported != "是" -> {done}
  - if {done} empty then end
  - call RCP.COMMON.EXCEL.BUILD_SUMMARY source={tasks} save_as={run_dir}/summary.xlsx -> {summary}
  - confirm "汇总表已生成，现在发出吗？"
  - call RCP.COMMON.WECHAT.SEND_FILE contact={boss} file={summary}
  - write_table {tasks} rows task in {done.task} set reported = "是"
check:
  - "{tasks} rows task in {done.task} column reported all == \"是\""
state: observed
verified: {count: 0, last: 2026-11-13}
```

- 内置变量：`{workdir}`、`{run_dir}`、`{today}`。文件必须在 `{workdir}` 或 `{run_dir}` 之下。
- 密钥写成 `{secret:NAME}`，只能作为 `inputs` 里某一项的完整取值，并且要列在 `secrets` 里。它只能传给最终流向 `type` 或 `clipboard` 的配方参数。
- `trigger`：`manual`、`schedule [daily|weekdays|Mon…Sun] HH:MM`、`file_change {路径}`。
- `authorize`（无人值守的步骤序号、可发出的文件、可发给的人）和 `lock` 由用户自己写、自己批准。你不要替用户写。

## 中英对照

两种写法完全等价，`kb fmt` 会统一转成英文。

**字段**

| 英文 | 中文 | 英文 | 中文 | 英文 | 中文 |
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

**关键字与取值**

| 英文 | 中文 | 英文 | 中文 | 英文 | 中文 |
|---|---|---|---|---|---|
| `visible` | 可见 | `hidden` | 不可见 | `shown` | 出现 |
| `gone` | 消失 | `text` | 文字 | `value` | 值 |
| `contains` | 包含 | `and` | 且 | `then` | 则 |
| `to` | 到 | `away_from` | 避开 | `up` / `down` | 上 / 下 |
| `focus` | 焦点 | `empty` | 为空 | `not_empty` | 不为空 |
| `rows` | 行 | `column` | 列 | `all` | 全部 |
| `where` | 筛选 | `set` | 设为 | `in` | 在 |
| `any` | 任意 | `->` | → | `unknown` | 未知 |
| `role` | 角色 | `name` | 名称 | `pick` | 取 |
| `first` / `last` | 第一 / 最后 | `self` | 本身 | `right_of` / `left_of` | 右侧 / 左侧 |
| `above` / `below` | 上方 / 下方 | `observed` | 观察 | `reproduced` | 复现 |
| `stable` | 稳定 | `recheck` | 待复核 | `none` | 无 |
| `destructive` | 破坏 | `external` | 外部 | `manual` | 手动 |
| `schedule` | 定时 | `file_change` | 文件变化 | `wait` / `skip` / `notify` | 等待 / 跳过 / 通知 |
