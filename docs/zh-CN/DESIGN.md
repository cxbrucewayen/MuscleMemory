# CUA 经验系统 · 设计（v6）

[English](../en/DESIGN.md) | **简体中文**

> 把每次操作电脑的收获写成短卡片。同一套卡片要能跨系统、跨软件、跨版本使用；AI 能快速找到它，程序能直接运行它；面向全球，同时完整适配中国。
>
> - **第一部分（第 0–18 节）卡片**：某个软件里的一件事怎么做。
> - **第二部分（第 19 节）事务流程**：把多个软件串起来，办完我自己的一件事。
> - **附录 A**：中英对照表。规范形式用英文，中文别名同样有效。

---

## 0. 全貌

```
                 ┌──────────────── 检索（第 9 节）────────────────┐
 cards/ ───────► │  用环境定范围 → 从任务/报错/界面入口定位 → 经验包 │
                 └───────────────────────┬────────────────────────┘
                                         ▼
                    能直接运行？ ──是──► kb_run 程序执行 ──失败──┐
                        │否                                        ▼
                        └────────────────────────────────► AI 执行（修复、探索）
                                                                   │
                                            kb_propose 提案 ◄──────┘
                                                  │ 审核、独立复现
                                                  ▼
                                               cards/
```

**一份经验，两种执行方式**：AI 读得懂，程序跑得动。平时由程序跑，出了问题交给 AI 修，修好后再交回程序跑。

**两层结构**

```
flows/  事务流程（本地、个人）   我的一件事：A 软件 → 数据或文件 → B 软件 → C 软件
   │ call
   ▼
cards/  卡片（可公开）           某个软件里的一件事怎么做
```

---

## 1. 三条原则

1. **当前界面才是依据，经验只是参考。** 优先级：用户指令 > 当前界面 > 经验卡。
2. **存方法，不存句柄。** PID、窗口 ID、element token、绝对坐标只属于这一次运行。卡里只写"下次怎么重新找到它"。
3. **没有判据不算经验。** "点击返回成功"不等于做成了。每个配方都要有程序能检查的判据。

---

## 2. 三个维度：系统 × 软件 × 版本

| 维度 | 存在哪里 | 怎么复用 |
|---|---|---|
| 系统 | 目录（`windows/`、`android/`…） | **同名卡**：通用卡定目标，各系统卡写做法 |
| 软件 | 文件（`wechat.yaml`） | 一个软件一个文件 |
| 版本 | 卡片里的 `applies` 范围 | **@ 变体**：只写变了的字段 |

**引用时永远不写版本**，由解析器挑出与当前环境最匹配的那张卡（第 8 节）。

---

## 3. 五种卡片与字段

| 类型 | 回答 |
|---|---|
| `ENV` 环境 | 这个系统能用什么手段，有什么限制？ |
| `APP` 软件 | 怎么认出、怎么启动这个软件，该用什么方式控制？ |
| `ELEM` 元素 | 界面或控件在哪里，怎么定位？ |
| `RCP` 配方 | 一件事怎么做，怎么确认做成了？ |
| `FAIL` 坑 | 出现这个症状是什么原因，怎么解决？ |

**字段表**（必 = 必填，选 = 可选，承 = 从通用卡或基卡继承）

| 字段 | 中文 | ENV | APP | ELEM | RCP 通用 | RCP 平台 | FAIL | 含义 |
|---|---|---|---|---|---|---|---|---|
| `id` | 编号 | 必 | 必 | 必 | 必 | 必 | 必 | 见第 4 节 |
| `applies` | 适用 | 必 | 必 | 必 | 必 | 必 | 必 | 版本范围，见第 5 节 |
| `aliases` | 说法 | | 必 | | 必 | 承/选 | | 检索用的别名，按语言分组 |
| `capabilities` `limits` `version_probe` | 能力 限制 版本获取 | 必 | | | | | | 系统可用的手段、限制、怎么读版本号 |
| `app_id` | 标识 | | 必 | | | | | 包名、bundle id 或可执行文件名，`open` 用它启动软件 |
| `home` | 首页 | | 必 | | | | | 软件主界面的 ELEM id，导航找不到路时从这里重来 |
| `preferred` | 推荐手段 | | 选 | | | | | |
| `purpose` | 作用 | | | 必 | | | | 一句话说明它是什么；定位失败时 AI 靠它自愈 |
| `parent` | 所在 | | | 选 | | | | 父界面的 id；不写，表示这本身就是一个界面 |
| `locators` | 定位 | | | 必 | | | | 候选定位方式，见第 10 节 |
| `params` | 参数 | | | | 选 | 承 | | 参数名列表，如 `[contact, remark]` |
| `goal` | 目标 | | | | 必 | 承 | | 一句话写明成功标准，平台卡不能改 |
| `side_effect` | 副作用 | | | | 必 | 承（只升不降） | | `none` / `destructive` / `external` |
| `output` | 输出 | | | | 选 | 承 | | 配方产出的变量，如 `[summary]`；平台卡结束时必须让它有值 |
| `requires` `steps` `check` `ends_at` | 前置 步骤 判据 结束于 | | | | | 必（requires 选） | | 见第 6 节 |
| `symptom` `conclusion` | 症状 结论 | | | | | | 必 | |
| `notes` | 说明 | 选 | 选 | 选 | 选 | 选 | 选 | 只给人和 AI 看，程序不读 |
| `evidence` `counterexample` `state` `verified` | 证据 反例 状态 验证 | 必 | 必 | 必 | | 必 | 必 | 见第 16 节 |

- 没有同名通用卡的平台配方，要自己写全 `aliases`、`params`、`goal`、`side_effect`。
- 每张卡最多 30 行 YAML；`steps` 最多 12 步，超过就拆成小配方，用 `call` 串起来。
- 引用只用库内 id，卡里不能有链接、代码块、命令。
- 证据只写结构，不写内容。人名、聊天、路径一律用占位符，如 `<CONTACT_A>`、`<USER_HOME>`。

---

## 4. 文件格式、目录与命名

### 4.1 文件格式

**卡片文件就是标准 YAML。** 一个文件可以有多张卡，用 `---` 分隔；第一段是文件头：

```yaml
format: 6          # 格式版本，必填
platform: WIN
app: WECHAT        # 平台层的文件写 _platform
---
id: ELEM.WIN.WECHAT.REMARK_ROW
applies:
  os: WIN >=10.0
  ...
---
id: RCP.WIN.WECHAT.RENAME_REMARK
...
```

- **结构用 YAML，规则用字符串。** 步骤、条件、定位、版本范围都是字符串，由各自的小语法解析（第 5、6、10 节）。这样解析器只需要一个 YAML 库，再加几个简单的文法解析。
- **YAML 的坑**：以 `{` 开头、或者含有 `: `、` #` 的值必须加引号。`kb fmt` 会自动加。
- **格式版本**：`format` 必填。解析器遇到不认识的版本直接拒绝；格式升级时用 `kb migrate` 把旧文件批量转成新格式。
- **规范形式**：`kb fmt` 会统一键名（英文）、键的顺序、缩进和引号。提交前自动运行，保证 diff 干净。

### 4.2 目录

```
cua-experience/                    # 仓库
├── README.md  DESIGN.md  SKILL.md  SECURITY.md
├── cards/
│   ├── common/
│   │   ├── _common.yaml           # 跨系统通用：通用目标（输入文本…）、通用坑
│   │   └── wechat.yaml            # 微信在各系统共享的目标
│   ├── windows/
│   │   ├── _platform.yaml         # ENV 卡、系统级与驱动级的坑
│   │   └── wechat.yaml            # APP、ELEM、RCP、FAIL，含各版本变体
│   ├── android/
│   └── harmony/
├── index/                         # 工具生成的检索索引，不手改
├── proposals/                     # 待合并提案（同时是隔离区）；AI 和执行器都不读
├── flows/                         # 本地事务流程；.gitignore
└── runs/                          # 本地运行记录、截图、锁、统计；.gitignore

~/.cua-experience/                 # 用户目录，不在仓库里
├── config.yaml                    # 本地设置：语言、密钥后端、忙时规则、通知方式
└── .env                           # 密钥（第 13 节）
```

### 4.3 命名

**id 就是位置**：`类型.平台.软件.名称[@变体标记]`，平台层的卡省略软件段。

| 文件 | id 示例 |
|---|---|
| `common/_common.yaml` | `RCP.COMMON.INPUT_TEXT` |
| `common/wechat.yaml` | `RCP.COMMON.WECHAT.RENAME_REMARK` |
| `windows/_platform.yaml` | `ENV.WIN`、`FAIL.WIN.UIPI_LOW_IL` |
| `windows/wechat.yaml` | `APP.WIN.WECHAT`、`ELEM.WIN.WECHAT.REMARK_ROW@4.2` |

- 平台缩写：`COMMON` `WIN` `MAC` `LINUX` `ANDROID` `IOS` `HARMONY`。
- id 只能用 ASCII 大写字母、数字和 `_`，`@` 后面是变体标记。这样可以防止同形字伪装（见 SECURITY）。
- 单个文件超过 400 行时，按界面拆分（如 `wechat.profile.yaml`），id 规则不变。

---

## 5. `applies`：版本范围

```yaml
applies:
  os: WIN >=10.0.22000            # 必填：平台缩写 + 版本范围
  app: WECHAT >=4.0 <4.2          # 软件卡必填：软件段 + 版本范围
  driver: cua-driver >=0.47       # 选填
  lang: zh-CN                     # 选填；依赖界面文字的卡必填
  display: DPI 100%               # 选填
  rom: HyperOS >=1.0              # 选填；只用于 Android 类平台
```

| 写法 | 含义 |
|---|---|
| `any` | 任意版本，如 `os: any`、`app: WECHAT any` |
| `=4.1.2` | 只有这一个版本 |
| `>=4.0` | 4.0 及以上 |
| `>=4.0 <4.2` | 4.0（含）到 4.2（不含） |

- 版本按数字逐段比较，4.10 大于 4.9。
- 选填项不写，表示不限制。
- **从窄开始，有证据再放宽。** 新卡只写验证过的那个版本，以后在其他版本上也验证成功了再放宽。

---

## 6. 步骤语法（AI 读得懂，程序跑得动）

`steps` 是字符串列表，第几项就是第几步。每一步的格式是 **`动词 对象 [参数]`**。语法本身就是白名单，语法之外的写法一律拒绝。

**动词**（中文别名见附录 A）

| 动词 | 写法 | 说明 |
|---|---|---|
| `open` | `open <APP id>` | 按 APP 卡的 `app_id` 启动软件，或切到前台 |
| `goto` | `goto <界面 id>` | 沿导航图走到该界面（第 11 节） |
| `click` `double_click` `right_click` | `click <元素>` | |
| `scroll` | `scroll <元素> up|down <次数>` | |
| `drag` | `drag <元素> to <元素>` | |
| `key` | `key <组合键>` | 如 `Ctrl+A`、`Enter`、`Back` |
| `type` | `type {参数}` | 向当前焦点输入；**只能输入参数，不能写死文字** |
| `clipboard` | `clipboard {参数}` | 写入剪贴板；同上 |
| `move_window` | `move_window <元素> away_from <元素>` | 把前一个窗口移出后一个窗口的范围 |
| `wait` | `wait <元素> shown|gone <N>s` | 超时即失败 |
| `read` | `read <元素> text|value -> {变量}` | 结果存进变量 |
| `assert` | `assert <条件>` | 条件不成立即失败 |
| `call` | `call <RCP id> 名=值 … [-> {变量}]` | 用 `->` 接收被调配方的 `output`；嵌套最多 3 层，不允许循环 |
| `if` | `if <条件> then <单个动作>` | 不能嵌套；动作不能是 `if` 或 `call` |
| `end` | `end` | 提前跳到判据检查 |

**`!` 标记**：在动词后面加 `!`（如 `click!`、`key!`），表示这一步会产生外部影响或无法撤销，比如发送、提交、删除、付款、签到。它是运行时的确认点。有 `!` 步骤的配方，`side_effect` 不能是 `none`。

**条件**

```
<元素> visible | <元素> hidden
<元素> text|value == | contains <值>
{变量} == | contains <值>
focus value == <值>                 # focus 指当前获得焦点的元素
<条件> and <条件>                    # 只有 and，没有 or
<值> := "字面量" | {参数} | {变量}
```

**前置、判据、结束于**

- `requires`：条件列表，执行前要全部成立。其中的"某界面 visible"如果不成立，执行器会先自动 `goto` 过去（第 11 节）。无法写成条件的要求，写进 `notes`。
- `check`：条件列表，执行后要全部成立才算成功。
- `ends_at`：一个界面 id，表示做完后界面停在哪里。

**设计取舍**：只能按顺序执行，没有跳转和循环，所以一定能结束。重试由执行器统一负责，卡里不写。

---

## 7. 复用：四种机制

| 场景 | 机制 | 例子 |
|---|---|---|
| 同一个动作，每次数据不同 | 参数 | `{contact}` `{remark}` |
| 一个动作被别的配方用 | call | `call RCP.WIN.WECHAT.OPEN_PROFILE contact={contact}` |
| 同一个目标，换一个系统 | 同名卡 | `RCP.COMMON.WECHAT.RENAME_REMARK` → `RCP.WIN.WECHAT.RENAME_REMARK` |
| 同一张卡，换一个版本 | @ 变体 | `ELEM.WIN.WECHAT.REMARK_ROW` → `…REMARK_ROW@4.2` |

- **同名卡**：通用卡写 `aliases`、`params`、`goal`、`side_effect`、`output`；平台卡把 id 里的 `COMMON` 换成平台缩写，写 `requires`、`steps`、`check`、`ends_at`。平台卡继承通用卡的字段，**不能改 `params` 和 `goal`**；`side_effect` 只能升不能降。平台卡的 `check` 必须能体现通用卡的 `goal`，这一点审核时要对照检查。
- **@ 变体**：`X@标记` 继承 `X` 的全部字段，只写变了的，`applies` 必须自己写。字段整体覆盖，例如写了 `locators` 就整组替换。
- **call**：跨系统的配方调用 `COMMON` id，单一平台内可以直接调用平台 id。同一串步骤在 2 个以上配方里出现，就提取成小配方。

---

## 8. 解析：挑出要用的那一张卡

**输入**：被引用的 id，加上环境快照（系统及版本、软件及版本、驱动、语言、显示、厂商系统）。

```
1. 换平台   COMMON id 换成当前平台的同名 id；找不到 → 没有做法
2. 收集     这个 id 本身，加上它所有的 @ 变体
3. 过滤     只保留 applies 完全包含当前环境的卡 → 标为"匹配"
4. 排序     条件越具体越优先（范围越窄、写的条件越多）→ 状态越高 → 验证越近
5. 兜底     一张都没有 → 取版本最接近的一张，标为"线索"
6. 合并     变体覆盖基卡，平台卡继承通用卡 → 得到最终的卡
```

读不到的版本，在环境快照里写 `unknown`，所有结果都标为"线索"。

---

## 9. 检索：AI 怎么快速找到经验

**第一步，用环境定范围（不需要搜索）**

只看四个文件：`common/_common.yaml`、`common/<软件>.yaml`、`<平台>/_platform.yaml`、`<平台>/<软件>.yaml`，其余全部排除。当前软件由前台应用确定；如果任务描述里提到了软件，就用 APP 卡的 `aliases` 来匹配。

**第二步，从入口定位**

| AI 手上有什么 | 接口 | 匹配哪个字段 |
|---|---|---|
| 任务描述 | `kb_bundle(task, env)` | 先匹配本地流程的 `aliases`；没有命中，再匹配 RCP 的 `aliases` 和名称 |
| 报错或异常现象 | `kb_symptom(error, env)` | FAIL 的 `symptom`；错误码精确匹配 |
| 当前界面特征 | `kb_screen(features, env)` | 界面元素的 `locators`；返回该界面和它下面的元素 |
| 什么都不确定 | `kb_outline(env)` | 范围内所有卡，每张一行摘要 |

- **匹配顺序**：精确匹配 → 别名 → 全文。`aliases` 的所有语言都参与匹配，所以用中文问能找到英文卡，反过来也一样。
- 前两名分数接近时都返回，由 AI 挑。
- 卡片达到几百张、关键词经常查不准时，再加语义检索，接口不变。

**第三步，返回经验包**

`kb_bundle` 找到配方后，把它的 `call`、步骤里引用的元素、`notes` 里引用的坑全部展开，逐张解析，然后返回：

```
经验包: 改微信备注
环境: WIN 10.0.22631 / WECHAT 4.2.0 / cua-driver 0.47.19 / zh-CN
可直接运行: 否（REMARK_ROW@4.2 状态为 observed）
├─ RCP.WIN.WECHAT.RENAME_REMARK          匹配 stable
├─ RCP.WIN.WECHAT.OPEN_PROFILE           匹配 stable（被调用）
├─ RCP.WIN.INPUT_TEXT                    匹配 stable（通用目标的 Windows 做法）
├─ ELEM.WIN.WECHAT.REMARK_ROW@4.2        匹配 observed（已自动选中 4.2 变体）
├─ FAIL.WIN.UIPI_LOW_IL                  匹配 stable（notes 中引用）
└─ FAIL.WIN.WECHAT.CARD_BEHIND           匹配 stable（notes 中引用）
```

- 每张卡以 `<card id="…" match="…" state="…">…</card>` 包裹，内容按用户语言显示（第 14 节）。
- **体积上限约 2000 token。** 超出时，配方和它直接引用的卡给全文，更深一层的只给一行摘要，AI 需要时再单独取。
- **一行摘要**的格式是 `id｜摘要｜状态｜匹配/线索`。摘要依次取 `aliases`、`purpose`、`symptom`、`conclusion` 中第一个存在的字段。
- `index/` 由工具生成，是 `aliases`、`symptom`、界面定位特征的倒排索引。卡片有变化就重新生成。

**接口**：同一组功能同时提供 MCP 工具和命令行。

| MCP 工具 | 命令行 |
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

## 10. 元素定位

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

**候选写法**

| 方式 | 写法 | 谁能用 |
|---|---|---|
| `ax` 无障碍 | `ax [role=] [name=] [id=] [value=] [parent=<元素>] [pick=first|last|N]` | 程序、AI |
| `text` 文字 | `text "<文字>" [self|right_of|left_of|above|below]` | 程序、AI |
| `coord` 坐标 | `coord <元素> <x%> <y%>`（相对某元素的百分比位置） | 程序、AI；最后手段 |
| `vision` 视觉 | `vision <描述>` | 只有 AI 或视觉模型 |

**`ax` 属性在各平台的对应关系**

| 本库 | Windows UIA | macOS AX | Android | iOS XCUITest | HarmonyOS |
|---|---|---|---|---|---|
| role | ControlType | Role | class | elementType | type |
| name | Name | Title / Description | text / content-desc | label | text |
| id | AutomationId | Identifier | resource-id | identifier | id |
| value | Value | Value | text | value | text |

- **按顺序尝试候选**，记下这次是第几个成功的；候选按稳定性从高到低排。
- **优先用与语言无关的 `id`。** 含界面文字的候选（`text`、带 `name=` 的 `ax`），卡片必须写 `applies.lang`。
- **全部失败时用 `purpose` 自愈**：AI 按这句描述在当前界面重新寻找，找到后提交新的 @ 变体。
- **界面元素**就是没有 `parent` 的 ELEM；它的 `locators` 能找到，就说明当前处在这个界面。

---

## 11. 界面导航

配方的 `requires` 经常要求"停在某个界面"。导航负责从当前界面走过去，所以配方里不用写一堆"先回首页、再点这里"的步骤。

**导航图不需要新字段**

- **节点**：界面元素（没有 `parent` 的 ELEM）。
- **边**：同时满足以下 4 个条件的配方，自动被识别为导航配方：
  1. `side_effect: none`，且没有 `!` 步骤
  2. 没有 `params`
  3. `requires` 里恰好有一条"某界面 visible"
  4. 写了 `ends_at`

**`goto <界面>` 的过程**

```
1. 识别当前界面    看哪个界面元素的 locators 能定位到
2. 找最短路径      在导航图上做广度优先搜索
3. 依次执行        沿路径执行导航配方，每一步检查 check
4. 找不到路        重新启动软件，回到 APP 的 home，再从那里找
5. 仍然不行        交给 AI
```

- 执行器在运行配方之前，如果 `requires` 里的界面条件不成立，会自动 `goto`。
- 导航配方也是普通配方，版本适配、变体、自愈全部照常适用。
- 导航配方不能有副作用，所以 `goto` 永远不会发消息、改数据（见 SECURITY）。

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

## 12. 执行

### 12.1 能直接运行的门槛

以下全部满足，经验包才会标为"可直接运行"：

1. 主配方状态是 `stable`，展开后的每一张卡至少是 `reproduced`
2. 每一张卡都解析为"匹配"，没有"线索"
3. 每一步、每个判据都符合第 6 节的语法
4. 每个元素至少有一个非 `vision` 的定位候选
5. 所有 `!` 步骤都有授权：交互运行时由用户当场确认，无人值守时看流程文件里的 `authorize`
6. 用到的密钥都能取到（第 13 节）

### 12.2 执行器 `kb_run`

```
1. 读取环境快照 → 解析配方并展开 → 检查门槛；不满足就交给 AI
2. 获取锁（12.4）；拿不到就按忙时规则处理
3. requires 里的界面条件不成立 → 自动 goto；其余条件不成立 → 失败
4. 逐步执行：
   - 元素按定位候选依次尝试，跳过 vision
   - 没写等待时间的动作，默认等元素出现 5s
   - 遇到 ! 步骤，确认或核对授权
   - 一步失败，重试 1 次；仍然失败 → 交接给 AI
5. 检查 check；不成立 → 交接给 AI
6. 释放锁；把运行记录写到 runs/；成功则本地验证次数加 1
```

### 12.3 交接给 AI

交接包内容：配方 id、环境快照、失败的步骤、已经尝试过的定位候选、当前界面结构快照、本地截图路径。**交接包里绝不包含密钥的值**，密钥一律显示为 `***`。

AI 收到后：先完成任务，再用 `kb_propose` 提交修复，通常是一个 @ 变体，或者调整定位候选的顺序。

### 12.4 并发与用户占用

**锁**
- 同一台设备上，**同一个软件同时只允许一个执行者**，不管是程序还是 AI。
- 驱动不支持后台操作时（会抢鼠标和焦点），**整台设备同时只允许一个执行者**。
- 锁文件放在 `runs/locks/`，带超时；进程崩溃后自动释放。
- AI 直接操作软件之前，先调用 `kb_lock(app)`，做完再 `kb_unlock`。

**用户正在使用电脑**
- 判断标准：最近 60 秒内有键鼠输入，并且目标软件在前台。时间可以在 `config.yaml` 里改。
- 用户在用的是别的软件，并且驱动支持后台操作 → 可以照常执行。
- 否则按流程的 `when_busy` 处理：`wait`（默认，最多等 30 分钟，然后通知你）、`skip`（跳过本次）、`notify`（立即通知你）。
- 你主动让 AI 去做的事，不受"用户占用"限制，但仍然要遵守锁。

### 12.5 定时与无人值守

定时任务就是只有一步的事务流程，触发、授权、锁定都写在流程文件里，见第 19 节。

程序执行的成功只计入本地统计，每周汇总成一条 `update` 提案，避免每天产生一条噪音。

---

## 13. 密钥

### 13.1 怎么引用

- 写法：`{secret:NAME}`，NAME 由大写字母、数字、`_` 组成，例如 `{secret:OA_PASSWORD}`。
- **只能出现在两个地方**：流程的 `inputs`，以及交互运行时传给 `kb_run` 的参数。
- **卡片里永远不出现密钥引用。** 卡片只用普通参数，比如登录配方写 `params: [user, password]`，由流程把 `password` 绑定到某个密钥。

```yaml
# 流程里
inputs:
  user: <OA 用户名>
  password: "{secret:OA_PASSWORD}"
secrets: [OA_PASSWORD]
steps:
  - call RCP.COMMON.OA.LOGIN user={user} password={password}
```

### 13.2 存在哪里

按 `config.yaml` 里的 `secret_backend` 决定（`env` / `keychain` / `auto`，默认 `auto`：先找 `.env`，找不到再找系统钥匙串）。

| 后端 | 位置 | 适合 |
|---|---|---|
| `.env` 文件 | Windows：`%USERPROFILE%\.cua-experience\.env`；macOS/Linux：`~/.cua-experience/.env` | **Windows 上推荐**，方便查看和编辑 |
| 系统钥匙串 | Windows 凭据管理器、macOS 钥匙串、Linux Secret Service | 安全性要求更高时 |

`.env` 的格式：

```
KB_SECRET_OA_PASSWORD=xxxxxx
KB_SECRET_WECHAT_PIN=xxxxxx
```

- 只读取 `KB_SECRET_` 开头的行，其余行忽略。
- **`.env` 放在仓库之外的用户目录里**，从位置上就排除了被误提交的可能。
- Android、iOS、鸿蒙设备上的操作也一样，密钥保存在控制它们的电脑上，由驱动代为输入。

**命令**

| 命令 | 作用 |
|---|---|
| `kb secret set NAME` | 隐藏输入，写入当前后端 |
| `kb secret list` | 只列出名字，不显示值 |
| `kb secret rm NAME` | 删除 |
| `kb secret check` | 检查 `.env` 的位置和文件权限（Windows 上要求只有当前用户能读） |

### 13.3 怎么使用（密钥只能流向输入框）

- **密钥的值只能流向 `type` 和 `clipboard`**；用 `clipboard` 时，执行器在粘贴后立即清空剪贴板。
- 密钥的值不能进入 `write_table`、文件、`output`、条件比较，也不能作为任何 `!` 步骤的对象。`kb check` 会顺着 `call` 追踪参数的去向。
- **AI 永远拿不到明文。** AI 执行时遇到密钥参数，调用 `kb_type_secret(NAME)`，由执行器代为输入。
- 日志、截图、交接包里一律显示为 `***`；输入密钥的那一步，执行器不截图。
- 流程必须用 `secrets` 声明要用到的密钥，这个列表计入锁定哈希；没有声明的密钥不能使用。

---

## 14. 国际化与中国适配

### 14.1 规范形式和中文别名

- **仓库里统一存英文规范形式**，包括字段名、动词、关键字、状态值。这样全球的贡献者和工具都能直接读。
- **解析器同时接受中文别名**（附录 A）。中文写的卡和英文写的卡完全等价。
- `kb fmt` 把卡片统一转成英文规范形式；`kb show --lang zh-CN` 用中文显示。
- 贡献者可以全用中文写，`kb propose` 提交时会自动转换。

### 14.2 内容的多语言

- `aliases` 按语言分组：`{en: [...], zh: [...]}`。至少写一种，公开的卡建议中英都写。
- 其他文字字段（`purpose`、`goal`、`notes`、`conclusion`、`symptom`…）可以是一个字符串，也可以是 `{en: ..., zh: ...}`。显示时按用户语言选取，缺少时回退到已有的语言。
- **界面语言不同，就是不同的环境。** 依赖界面文字的卡必须写 `applies.lang`；英文界面用 @ 变体（如 `REMARK_ROW@en`）；能用 `id` 定位的就别依赖文字。

### 14.3 中国适配

| 问题 | 做法 |
|---|---|
| 中文输入经常出错 | 统一调用 `RCP.COMMON.INPUT_TEXT`，各平台用剪贴板等可靠方式输入，不直接打中文 |
| 国产安卓系统各不相同（权限弹窗、设置路径） | `applies.rom` 写厂商系统，如 HyperOS、ColorOS、OriginOS、MagicOS；差异用 @ 变体 |
| HarmonyOS NEXT 不再兼容安卓应用 | 单独作为平台 `HARMONY`，驱动用 hdc；Cua 目前不支持，需要自己补驱动 |
| 国内常用软件 | 微信、企业微信、钉钉、飞书、WPS 等按普通软件建卡，`aliases` 中英都写 |
| 访问 GitHub 不稳定 | 发布版本同步到 Gitee 镜像；客户端只认签名，镜像只是下载通道（见 SECURITY） |
| 隐私合规 | 同时满足 GDPR 和《个人信息保护法》的最小必要原则（见 SECURITY） |

---

## 15. 完整示例

> 示例里的 4.2 界面变化、"某 App"（XXAPP）都是虚构的，只用来演示机制。

**例一：修改微信备注（跨版本）**

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

**同一句 `call RCP.COMMON.WECHAT.RENAME_REMARK`，在不同环境下得到：**

| 当前环境 | 配方解析为 | 第 3 步的元素解析为 |
|---|---|---|
| Windows 11 + 微信 4.1 | `RCP.WIN.WECHAT.RENAME_REMARK` | `ELEM.WIN.WECHAT.REMARK_ROW` |
| Windows 11 + 微信 4.2 | `RCP.WIN.WECHAT.RENAME_REMARK` | `ELEM.WIN.WECHAT.REMARK_ROW@4.2` |
| Android 14 + 微信 8.0 | `RCP.ANDROID.WECHAT.RENAME_REMARK` | `ELEM.ANDROID.WECHAT.REMARK_ENTRY` |
| macOS + 微信 | 没有做法 → AI 探索，完成后提交 `RCP.MAC.WECHAT.RENAME_REMARK` | — |

**例二：每日签到（程序直接运行）**

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

配好一个只有一步的流程（见 19.6）后，每天由 `kb_run` 直接执行，不调用 AI。某天 App 改版、签到按钮找不到了，就交接给 AI。AI 完成签到，并提交一个 `CHECKIN_BUTTON@<新版本>` 变体。你确认新的锁定哈希之后，第二天又恢复由程序直接运行。

---

## 16. 迭代

**四种状态**（每张卡、每个变体各自计算）

```
observed 观察 ──第 2 次独立出现──► reproduced 复现 ──累计 ≥3 次 且 写得出反例──► stable 稳定
任何状态 ──版本变化 / 出现相反结果──► recheck 待复核（用之前先验证）
```

"写得出反例"是硬门槛：说不清什么时候不成立的卡，永远停在 `reproduced`。通用卡没有步骤，不计状态。

**每次运行后怎么更新**

| 情况 | 提案 |
|---|---|
| 环境匹配，照卡做成了 | `update`：验证次数加 1 |
| 照卡做失败了 | 先记现象；连续 2 次失败就标为 `recheck` |
| 在范围之外的新版本上照卡做成了 | `widen`：放宽 `applies` |
| 在新版本、新语言、新厂商系统上部分不同 | `variant`：新建 @ 变体，只写不同的字段 |
| 定位时排在后面的候选成功了 | `variant`：调整 `locators` 的顺序 |
| 第一次在某个系统上做成 | `new`：新建该平台的同名卡 |
| 同一个坑在 3 个以上软件出现 | 移到 `_platform.yaml` 或 `_common.yaml` |
| 旧版本已经没人用 | 删除旧卡，或把变体合并回基卡 |

**维护节奏**

| 频率 | 做什么 |
|---|---|
| 每次任务 | AI 最多提 3 条提案 |
| 每周 | 合并提案；汇总程序执行的统计 |
| 每月 | 升级达标的卡；删除 3 个月没被命中、且未达到 `stable` 的卡 |
| 软件或驱动升级 | 把受影响的卡标为 `recheck` |
| 每季度 | 删的卡要比加的多 |

---

## 17. 起步

1. **一个系统、一个软件**：Windows + cua-driver + 一个软件。先实现 YAML 解析、`kb check`、`kb fmt`，跑通"检索 → AI 执行 → 提案 → 合并"。
2. **导航和程序执行**：为这个软件补齐导航配方，用 `kb_run` 跑通一个稳定的配方；再故意制造一次失败，验证交接给 AI 的流程。
3. **第二个版本、第二种界面语言**：验证"放宽适用"和"@ 变体"。
4. **第二个系统**：验证同名卡能否让通用目标在两个系统上都跑通。
5. **第一个事务流程**：把两三个稳定的配方串起来，验证数据传递、密钥、断点恢复、锁和无人值守授权。

初期只看四个指标：查得准不准、照卡做的成功率、程序直接运行的比例、失效的卡多久被修好。

---

## 18. 刻意不做的事

| 不做 | 原因 |
|---|---|
| 把经验导出成脚本 | 会和经验库分叉，丢掉版本适配；脚本是任意代码，无法审查 |
| 步骤里的跳转和循环 | 只能顺序执行加单步条件，保证一定能结束；重试交给执行器 |
| 每个版本一个目录 | 用范围和 @ 变体表达就够了 |
| 小数置信度、成功率公式 | 状态加次数已经够用；数字越精细越容易被刷 |
| 库里存截图、遥测上报 | 有泄露风险，也没有必要 |
| 一开始就上向量检索 | 有环境定范围加别名匹配，几百张以内够用 |
| 云端密钥服务 | 密钥只留在本机 |
| 公开的流程库、流程里跑脚本 | 流程含个人信息，先只放在本地；以后需要时再加去个人化的流程模板，以及经过批准的本地脚本 |

---

# 第二部分：事务流程

## 19. 事务流程

### 19.1 为什么和卡片分开

| | 卡片 | 流程 |
|---|---|---|
| 回答 | 某个软件里一件事怎么做 | 我的一件事怎么从头办到尾 |
| 范围 | 一个软件 | 多个软件，加上文件和数据 |
| 个人信息、密钥引用 | 不允许 | 允许，只在本地 |
| 存放 | `cards/`，可公开 | `flows/`，只在本地 |
| 怎么被用 | 被调用 | 被触发（手动、定时、文件变化） |

**分工**：流程只负责编排顺序和传递数据，所有软件操作都通过 `call` 卡片完成，流程里不写任何点击和定位。所以软件改版时只需要修卡片，版本适配、导航、自愈、安全检查也全部沿用卡片的机制。

### 19.2 流程文件

一个流程一个文件：`flows/<名称>.flow.yaml`。以"任务清单 → Excel 汇总 → 微信发给老板 → 回填任务清单"为例：

```yaml
format: 6
id: FLOW.WEEKLY_REPORT
aliases:
  en: [weekly report]
  zh: [周报, 发总结给老板]
trigger: [manual, schedule Fri 16:30]
workdir: <周报文件夹>
inputs:
  tasks: "{workdir}/tasks.csv"
  boss: <老板的微信显示名>
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
lock: sha256:<流程文件 + 展开后全部卡片的哈希>
state: stable
verified: {count: 6, last: 2026-11-12}
lessons:
  - 2026-11-05 老板周五 17:00 后不看消息，定时提前到 16:30
```

**字段**

| 字段 | 中文 | 必填 | 含义 |
|---|---|---|---|
| `format` `id` | 格式 编号 | 必 | `id` 为 `FLOW.<名称>` |
| `aliases` | 说法 | 必 | `kb_bundle` 会先匹配它 |
| `trigger` | 触发 | 必 | `manual`、`schedule <时间>`、`file_change {路径}`，可以写多个 |
| `workdir` | 工作目录 | 必 | 流程能读写的唯一目录（另外还能用本次运行的 `{run_dir}`） |
| `inputs` | 输入 | 选 | 个人绑定的值：文件、联系人、文字、`{secret:NAME}` |
| `secrets` | 密钥 | 选 | 用到的密钥名称列表 |
| `when_busy` | 忙时 | 选 | `wait`（默认）/ `skip` / `notify`，见 12.4 |
| `steps` | 步骤 | 必 | 见 19.3 |
| `check` | 判据 | 必 | 整件事做成的标准 |
| `authorize` | 授权 | 选 | 无人值守时允许的 `!` 步骤序号、可发出的文件、可发给的人 |
| `lock` | 锁定 | 选 | 由 `kb flow approve` 生成；`lessons` 不计入哈希 |
| `state` `verified` | 状态 验证 | 必 | 同卡片；流程不要求写反例，累计成功 3 次以上即为 `stable` |
| `lessons` | 经验 | 选 | 这件事特有的经验，每行"日期 + 一句话"；程序不读 |

### 19.3 步骤语法

流程只有 7 个动词，**没有**点击、输入这类界面操作：

| 动词 | 写法 | 说明 |
|---|---|---|
| `call` | `call <RCP id> 名=值 … [-> {变量}]` | 所有软件操作都走这里 |
| `read_table` | `read_table {文件} [where <行条件>] -> {变量}` | 内置，支持 csv、xlsx |
| `write_table` | `write_table {文件} rows <行条件> set <列> = <值>` | 内置；写之前自动备份到运行目录 |
| `wait_file` | `wait_file {路径} <N>s` | 等软件导出的文件生成 |
| `confirm` | `confirm "<给用户看的话>"` | 人工检查点；无人值守时会暂停并通知你 |
| `if` | `if <条件> then <单个动作>` | 规则同卡片 |
| `end` | `end` | 提前跳到判据检查 |

**流程里可用的条件**

```
<列> == | != | contains <值>                     # 行条件，用在 where / rows 里
<列> in {变量.列}                                 # 行条件
{变量} empty | {变量} not_empty
{变量} rows > | == | < <数字>
{文件} rows <行条件> column <列> all == <值>
<条件> and <条件>
```

### 19.4 数据怎么在软件之间传

- **变量有三个来源**：`inputs`、`read_table` 的结果、`call` 用 `->` 接收的输出。内置变量有 `{workdir}`、`{run_dir}`、`{today}`。
- `{变量.列}` 取表格的一列，例如 `{done.task}`。
- **软件之间传文件靠路径**：上一个配方的 `output` 是文件路径，下一个配方的参数接收它。
- **中间产物默认写进 `{run_dir}`**，即 `runs/<流程>/<运行编号>/`。每次运行一份，方便追溯和重发。
- **配方要能被流程串起来，就得声明 `output`**：

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

### 19.5 运行：断点与恢复

```
kb flow run FLOW.WEEKLY_REPORT
  检查触发条件和忙时规则
  逐步执行：
    call → 交给 kb_run；不满足直接运行的门槛，就交给 AI
    每完成一步，写一次检查点：runs/<流程>/<运行编号>/state
  某一步失败 → 流程暂停 → AI 修好这一步（卡片的问题照常提案）
            → kb flow resume，从失败的那一步继续
  全部完成 → 检查 check
```

- **已完成的步骤不重做。** 含 `!` 的步骤（比如已经发给老板）**绝不自动重做**。
- **含 `!` 的步骤状态不确定时**（比如点了发送后程序崩溃），不重试，先由 AI 到对应软件里核实是否已经发出，再决定下一步。
- `write_table` 出错时，可以从运行目录的备份恢复。

### 19.6 定时任务就是只有一步的流程

```yaml
format: 6
id: FLOW.DAILY_CHECKIN
aliases:
  zh: [每日签到]
trigger: [schedule daily 08:10]
workdir: <签到文件夹>
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

### 19.7 流程怎么产生，怎么积累经验

```
你用一句话描述这件事 → AI 起草（每个子目标用 kb_bundle 找配方）→ 你审阅
  → 试运行（AI 执行，每一步给你看结果）→ observed → reproduced → stable
  → 你批准授权和锁定 → 程序无人值守运行
```

- **缺配方的子目标**：先写成待建的 `call`，试运行时由 AI 探索完成，同时提交卡片提案。流程里永远不写软件操作的细节。
- **需要密码的子目标**：AI 只在流程里写 `{secret:NAME}`，并提醒你用 `kb secret set NAME` 存入；AI 自己不经手密码。
- **无人值守的门槛**：流程状态为 `stable`，每个调用的配方都可直接运行，`authorize` 覆盖所有 `!` 步骤，密钥都能取到。

**经验写到哪里**

| 学到的东西 | 写到哪 |
|---|---|
| 某个软件的做法、坑、元素 | 卡片（用 `kb_propose` 提交，可公开） |
| 软件之间怎么传数据、先后顺序、这件事的特殊要求 | 流程的 `lessons`（本地） |
| 发给谁、用哪个文件 | 流程的 `inputs`（本地） |
| 密码 | `.env` 或系统钥匙串 |

判断标准只有一句：**离开这件事还有用的，写进卡片；离开这件事就没意义的，留在流程里。**

---

# 附录 A：中英对照

解析器两种写法都接受，`kb fmt` 统一转成英文。

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

**动词**

| 英文 | 中文 | 英文 | 中文 | 英文 | 中文 |
|---|---|---|---|---|---|
| `open` | 打开 | `goto` | 前往 | `click` | 点击 |
| `double_click` | 双击 | `right_click` | 右击 | `scroll` | 滚动 |
| `drag` | 拖动 | `key` | 按键 | `type` | 输入 |
| `clipboard` | 写剪贴板 | `move_window` | 移动窗口 | `wait` | 等待 |
| `read` | 读取 | `assert` | 校验 | `call` | 调用 |
| `if` | 若 | `end` | 结束 | `read_table` | 读表 |
| `write_table` | 写表 | `wait_file` | 等待文件 | `confirm` | 确认 |

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
| `ax` | 无障碍 | `coord` | 坐标 | `vision` | 视觉 |
| `role` | 角色 | `name` | 名称 | `pick` | 取 |
| `first` / `last` | 第一 / 最后 | `self` | 本身 | `right_of` / `left_of` | 右侧 / 左侧 |
| `above` / `below` | 上方 / 下方 | `observed` | 观察 | `reproduced` | 复现 |
| `stable` | 稳定 | `recheck` | 待复核 | `none` | 无 |
| `destructive` | 破坏 | `external` | 外部 | `manual` | 手动 |
| `schedule` | 定时 | `file_change` | 文件变化 | `wait` / `skip` / `notify` | 等待 / 跳过 / 通知 |
