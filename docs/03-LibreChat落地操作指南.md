# 投资问数多 Agent 架构 - LibreChat 落地操作指南

> **文档版本**：v1.17
> **生成日期**：2026-07-31
> **更新日期**：2026-08-05（同步最新 `librechat.yaml` 与 `.env`；新增业务 Skill `investment-dwd-query`；重构 A1/A2 指令为"两级查询策略：优先 `dwd_all_biz`，查不到再分头查专表"；强化 A2"数据真实性规则（禁止臆测/加工）"与"分页处理规则"；**v1.5 新增"链式/多跳关系核实"规则防"拼接臆测"，并修正 Step 7 工具清单补挂 `query_all_biz`；v1.6 新增 E2E-011（链式防拼接验证）与 E2E-012（分页验证）专门用例；v1.7 修复分页重复/错乱：服务端为每个视图增加稳定唯一排序兜底，用户未明确要求排序时一律不传 `order_by`，避免非法字段导致无 ORDER BY 分页不稳定；v1.8 修复"重复输出"问题：确认 A1 不得同时配置 Handoff 与 Chain 指向 A2（两条不同 edgeType 的边会被同时保留，导致 A2 被触发两次），并新增 E2E-013 重复输出验证用例；v1.9 修复"翻页后数据编造"问题：A1 对"列出所有/全部"类请求必须输出 `limit: 200` 一次取全避免翻页，A2 分页规则强制"offset>0 翻页必须重新调用工具、禁止复用旧数据/占位说明"，并新增 E2E-014 翻页真实性验证用例；v1.10 全面剔除"模拟输出"：A1/A2 指令与 SKILL 增加"禁止模拟输出"（不得输出"环境限制/实际执行中将调用/占位符"等），A1 输出格式增加"只输出一次"+offset 只放"其他参数"字段+"下一页"offset 递推规则，A2 输出格式增加"只输出一次最终结果"，并修正 A1 澄清轮数 recursion_limit=10→3 与 Step 14 保持一致；v1.11 新增"追问必重查"强制规则：A2 工具调用约束与 SKILL 边界明确"每次用户追问/新请求必须重新调用 MCP 工具获取最新数据，禁止复用历史上下文中旧的工具结果、禁止凭模型记忆输出"，并禁止"根据您的查询，我已为您调取了..."等模拟/复用表述，每段输出必须由本轮真实工具调用产生（针对"某市投资基金投资明细"两段重复输出问题）；v1.12 支持 mermaid 图表（图中节点/关系/数值必须来自工具真实返回 data，禁止编造）；v1.13 新增"循环终止"硬性机制：A2 同一查询重试 2 次仍失败即终止、A1 澄清 3 轮仍无法确定即输出 UNCLEAR 终止，禁止无休止换参数重试/重新分类，防止死循环**）；**v1.14 新增"数据忠实性规则"：实测数据库存在名称含"测试"的真实项目（如"测试数据-ct直投0612""股权测试"）与同一"投资方→被投资方"的多条重复记录（如"某控股公司→某电器有限公司_2026年度"重复 63 条），模型曾自行过滤/去重导致与数据库实际行数不一致；故在 A2 指令与 SKILL 新增"禁止自行过滤/去重/修改"规则（工具返回每一行必须原样呈现、total 必须一致、未经用户明确要求严禁加工），并在 A1 约束新增"禁止引入过滤/去重参数"**）；**v1.15 对 Instruction 与 Skill 做"去重归位 + 调用保障"重构：二者原存在大量重复（两级策略/工具映射/参数构造/分页/链式/数据真实性等双写），易漂移且占 token；现将 Skill 定位为唯一"技术实现层"（实体/数据来源/工具路由/参数值映射，并设 `always-apply: true` 保证每个 turn 自动注入），将 A2 Instruct 定位为唯一"行为层"（角色感知/输出格式/数据真实性/数据忠实性/链式防拼接/分页展示/追问必重查/循环终止/禁止模拟），重复内容按职责归位、一方只保留引用；并明确 **A1 不挂载 Skill**（A1 纯分类不调工具，避免工具注入与 token 浪费，其精简语义表与 Skill 同源维护）**）；**v1.16 修复"重复输出"（实测定位）：数据库实测同一条 A1 消息的 `content` 数组里，`content[0]`（A1）与 `content[1]`（A2）各输出了一份几乎相同的查询结果表格，前端串联渲染成"重复输出"。根因是**架构错配**：A1 明明是"纯分类器"，实际部署却用了 **subagents（子代理）** 机制（`subagents.enabled=true, agent_ids=[A2]`），子代理 A2 的结果被并入 A1 消息；且 A1 模型在分类后**复用了同一对话历史里前几轮已查过的数据**，在 `content[0]` 画蛇添足自行生成了表格（违反其"只输出结构化分类"约束）。修复：将 A1 从 subagents 改为文档推荐的 **Handoff**（`edges=[{from:A1,to:A2,edgeType:'handoff'}]`，`subagents.enabled=false`），使 A2 独立输出结果；并重写 A1 指令新增"交接动作（调用 `lc_transfer_to_*` 把分类结果传给执行器）+ 严禁输出任何查询结果表格/汇总 + 严禁复用历史查询数据"硬约束（最高优先级）。Handoff 能力默认可用（`agents.use/create:true`，运行时 multi-agent 图随 edges 自动构建并注入 `lc_transfer_to_` 交接工具），无需改 yaml/router。）**）；**v1.17 `dwd_all_biz` 视图新增 `company_name` 字段（语义：该投资所负责的金控内部公司 = 投资方实体所属金控公司）：① `sql/dwd_views.sql` 为 4 个 UNION 分支（FUND2PROJ/SUBFUND2PROJ/FUND2SUBFUND/LP2FUND）LEFT JOIN `dwd_fund`/`dwd_subfund` 关联出 `company_name`（FUND2PROJ/SUBFUND2PROJ/FUND2SUBFUND 取投资方公司，LP2FUND 取被投资方基金公司）；② 服务端 `base.py` 白名单（ALLOWED_FIELDS/GROUP_BY_FIELDS/PREFIX_MATCH_FIELDS/DEFAULT_FIELDS）为 `dwd_all_biz` 增加 `company_name`；③ `summary.py` 的 `query_all_biz` 新增 `company_name`（精确）与 `company_name_prefix`（前缀）参数，支持按金控公司过滤跨域投资关系；④ Skill `investment-dwd-query` 同步补充 `company_name` 语义与路由参数；⑤ 本指南同步更新 A1/A2 指令、Step 7 工具说明与数据结构说明，并新增"附录 F：dwd_all_biz 数据结构说明（v1.17）"与"附录 G：本体层（Ontology）架构评估与设计方案"**）；**v1.18 引入本体层（Ontology）落地：引入 `ontology.yaml` 作为语义单一事实源（SSOT），MCP 启动/首次导入时自动加载生成运行时白名单（改本体→重启即生效，无需命令同步）；新增第 12 个 MCP 工具 `get_ontology`（内省工具，A2 可对话中动态拉取本体定义，指令/SKILL 不再写死语义）；SKILL 语义段改为引用本体生成的人读投影 `skill-semantics.md`，仅保留操作适配层；A1/A2 指令按"行为/语义分离"原则做引用性修改（详见"阶段〇：引入本体层"）**）
> **配套设计文档**：[02-投资问数多Agent架构设计.md](02-投资问数多Agent架构设计.md)
> **目标**：提供可在 LibreChat 上逐步执行的落地操作指南

---

## 前置准备：当前配置状态核实

在开始操作前，先核实 LibreChat 当前配置状态，识别需要修改的部分：

### 当前状态（已核实）

| 配置项 | 当前状态 | 文件位置 | 是否需要修改 |
|--------|---------|---------|-------------|
| Qwen-3.6-Local Endpoint | ✅ 已配置 | [librechat.yaml:528-542](librechat/librechat.yaml#L528) | ❌ 无需修改 |
| Endpoint capabilities | `[files, agents]` | [librechat.yaml:535-537](librechat/librechat.yaml#L535) | ❌ 无需修改（chain 在运行时默认值中） |
| mcpSettings.allowedAddresses | ✅ 包含 `10.0.0.5:8080`、`10.0.0.5:8017` | [librechat.yaml:344-349](librechat/librechat.yaml#L344) | ❌ 无需修改 |
| **actions.allowedDomains** | ✅ 已含 `http://10.0.0.5:8080/mcp`、`http://10.0.0.5:8017/mcp` | [librechat.yaml:273-280](librechat/librechat.yaml#L273) | ❌ 无需修改 |
| mcpServers 配置 | ❌ **被注释掉** | [librechat.yaml:352-358](librechat/librechat.yaml#L352) | ✅ **必须取消注释** |
| agents 全局配置 | ❌ 被注释（默认值已含 chain/subagents） | [librechat.yaml:406-431](librechat/librechat.yaml#L406) | ❌ 无需修改 |
| MCP 服务端 | ✅ 运行中 @ 10.0.0.5:8080 | mcp-inv-server-v2 | ❌ 无需修改 |

### `.env` 环境变量（已核实）

| 变量 | 值 | 说明 |
|------|-----|------|
| `HOST` | `10.0.0.5` | Web 服务监听地址 |
| `PORT` | `3090` | Web 服务端口（**非 3080**） |
| `DOMAIN_CLIENT` / `DOMAIN_SERVER` | `http://10.0.0.5:3090` | 前端 / 后端访问域名 |
| `ENDPOINTS` | `agents,custom` | 仅启用 agents 与 custom（Qwen）端点 |

> **访问地址**：LibreChat Web 界面为 `http://10.0.0.5:3090`，API 为 `http://10.0.0.5:3090/api`。

### 关键发现

1. **mcpServers 配置被注释掉** — 这是 MCP 工具无法在 LibreChat 中识别的根本原因
2. **capabilities 无需修改** — `chain` 与 `subagents` 已在运行时默认 capabilities 中（[config.ts:682-699](librechat/packages/data-provider/src/config.ts#L682)），**Handoff 模式始终可用**，无需额外配置
3. **建议使用 Handoff 模式** — 兼容当前配置，无需修改 capabilities
4. **`actions.allowedDomains` 已就绪** — 已包含 MCP 服务地址，打通了 MCP-over-HTTP 的访问控制（与 `mcpSettings.allowedAddresses` 互补）

---

## 阶段〇：引入本体层（语义单一事实源，推荐增强）

> **目的**：把"字段含义、关系、业务规则"等语义定义收敛到唯一的 `ontology.yaml`，MCP 启动自动加载、动态生效，Agent/SKILL 不再写死语义，从根本上消除"语义散落三方、随本体过期"的问题。
> **是否必做**：**推荐增强**。若暂不启用，SKILL/指令仍按 v1.17 方式维护（语义双写，但需人工同步、存在漂移风险）。启用后语义只需维护本体一处。

### 〇.1 本体层现状（已落地）

| 项 | 状态 | 说明 |
|----|------|------|
| `ontology.yaml` | ✅ | `mcp-inv-server-v2/ontology/ontology.yaml`，对象/关系/属性/规则/安全白名单的单一事实源 |
| 运行时自动加载 | ✅ | MCP 启动/首次导入时自动读本体 → 生成运行时白名单（`get_whitelists` 懒加载单例）；**改本体 → 重启即生效，无需任何命令** |
| 双投影 | ✅ | 机读投影 = `base.py` 运行时白名单；人读投影 = `ontology/generated/skill-semantics.md` |
| `get_ontology` 内省工具 | ✅ | 新增第 12 个 MCP 工具，A2 可对话中动态拉取本体定义 |
| CI 门禁 | ✅ | `scripts/check_ontology_sync.py` 校验本体合法 + 白名单视图覆盖 + SKILL 语义段零漂移 |

### 〇.2 如何修改 SKILL.md（语义引用化）

> **原则**：语义定义一律引用本体，操作适配层保留。SKILL 重定位为"本体 → MCP 的操作适配器"。

1. **删除** SKILL.md 中与 `skill-semantics.md` 重复的对象/关系/属性/规则定义（字段含义、`company_name` 归因、`biz_type`/`biz_line` 语义、金额口径等）。
2. **在 SKILL.md 顶部加引用块**，指向本体人读投影：

   ```markdown
   > 语义单一事实源：`mcp-inv-server-v2/ontology/ontology.yaml`。
   > 字段/关系/规则的权威定义见本体生成的人读投影 `ontology/generated/skill-semantics.md`，
   > 本文件仅保留"如何把本体语义翻译成 MCP 调用"的操作适配。
   ```

3. **保留**工具路由（两级策略）、参数值映射、`biz_type`/`biz_line` 转换、查询策略等"怎么查"的实现层内容。
4. **变更流程**：改 `ontology.yaml` → 运行 `render-skill` 重出 `skill-semantics.md` → 同步引用路径即可，**禁止手工双写语义**。

### 〇.3 如何修改 A2 指令（行为层 + 动态语义）

1. **工具数更新**：Step 7 挂载工具由 11 个增至 **12 个**，新增 `get_ontology`。
2. **语义动态拉取**：在 A2 指令"技能与指导说明的分工"段补充：

   ```markdown
   ## 语义定义动态获取（⚠️ 本体为准）
   - 字段含义、关系、业务规则（如 company_name 归因、金额口径、禁止跨 biz_line 加总）一律以本体为准。
   - 若指令/SKILL 中未写或不确定某字段/规则语义，可调用 `get_ontology` 工具动态拉取本体定义
     （scope=objects / relations / rules / views），以工具返回为准，禁止凭记忆猜测。
   ```

3. **行为层保持**：角色感知、数据真实性/忠实性、防拼接、分页、追问必重查、循环终止等"怎么答"规则一律留在 A2 指令，**不写入本体**（本体只承载语义，不承载行为规则）。

### 〇.4 如何修改 A1 指令（纯分类器，变化最小）

1. **不挂载任何工具**（含 `get_ontology`）：A1 是纯分类器，只做意图分类+参数抽取，不查询数据、不查本体。biz_line 一律填中文值，映射由 A2 完成。
2. **语义同源**：A1 内嵌的精简语义表（`biz_type` 四类、集团指代、`biz_line` 概念值）与本体**同源**。但 A1 **不调 get_ontology**——弱模型在"查本体 vs 填中文"间会陷入死循环，已废弃此能力。
3. 其余（分类规则、默认值、澄清终止、输出格式、禁止过滤参数）保持不变。

### 〇.5 修改后的职责边界速查

| 组件 | 承载 | 变更 |
|------|------|------|
| 本体 `ontology.yaml` | 对象/关系/属性/规则/白名单 | 权威源，改此重启生效 |
| MCP | 结构安全 + 执行 + `get_ontology` 内省 | 白名单自动加载，工具 +1 |
| SKILL | 操作适配（路由/映射/策略） | 语义改引用，删重复定义 |
| A2 指令 | 行为层 | + 动态调 `get_ontology`，语义引用本体 |
| A1 指令 | 纯分类器 | 基本不变，语义同源 |

---

## 阶段一：配置文件修改（前置必做）

### Step 1：取消 mcpServers 配置注释

**目标**：让 LibreChat 识别 MCP 服务并加载 10 个工具

**文件**：[librechat.yaml:352-358](librechat/librechat.yaml#L352)

**操作**：将以下被注释的配置：

```yaml
#mcpServers:
#  inv-mcp:
#    type: streamable-http
#    url: http://10.0.0.5:8080/mcp  # 完整服务地址（含协议和路径）
#    timeout: 60000
#    headers:
#      Authorization: "Bearer dev_token_123"  # ⚠️ 核心认证配置
```

**修改为**（去掉 `#` 注释）：

```yaml
mcpServers:
  inv-mcp:
    type: streamable-http
    url: http://10.0.0.5:8080/mcp
    timeout: 60000
    headers:
      Authorization: "Bearer dev_token_123"
```

**验证**：重启 LibreChat 后，在聊天界面的工具栏应能看到 `inv-mcp` 服务的工具列表。

### Step 2：跳过 — 无需额外配置

> **核实结果**：`chain` 和 `subagents` 已在 LibreChat 默认的 AgentCapabilities 中
> （[config.ts:682-699](librechat/packages/data-provider/src/config.ts#L682)）。
> `Handoff` 模式始终可用（[OrchestrationHub.tsx:49-53](librechat/client/src/components/SidePanel/Agents/Advanced/OrchestrationHub.tsx#L49)），
> 不依赖任何 capability 配置。无需修改 `librechat.yaml`。

### Step 3：重启 LibreChat

```bash
# 在 LibreChat 项目目录执行
cd <librechat-home>
docker-compose restart
```

**验证清单**：
- [ ] LibreChat 正常启动，无报错
- [ ] 聊天界面工具栏出现 `inv-mcp` 工具
- [ ] Agent 创建界面可用

---

## 阶段二：创建共享 A2 执行器（先创建下游，再创建上游）

> **顺序说明**：因为 A1 需要配置指向 A2 的 Handoff/Chain，所以必须先创建 A2。

### Step 4：进入 Agent 创建界面

1. 打开 LibreChat Web 界面（`http://10.0.0.5:3090`，来自 `.env` 的 `HOST`/`PORT`）
2. 点击左侧边栏的 **"Agents"** 图标（机器人图标）
3. 点击 **"Create Agent"** 按钮（或 "新建 Agent"）

**对应 UI 组件**：[AgentConfig.tsx](librechat/client/src/components/SidePanel/Agents/AgentConfig.tsx)

### Step 5：配置 A2 基础信息

在 Agent 创建界面填写以下字段：

| 字段 | 填写值 | UI 位置 |
|------|--------|---------|
| **Name**（名称） | `投资数据执行器` | 顶部输入框，[AgentConfig.tsx:61-86](librechat/client/src/components/SidePanel/Agents/AgentConfig.tsx#L61) |
| **Description**（描述） | `接收意图分类结果，调用 MCP 工具执行查询` | Name 下方输入框 |
| **Provider**（端点） | 选择 `Qwen-3.6-Local` | 点击 provider 按钮跳转选择面板 |
| **Model**（模型） | `qwen3.6-35B` | 点击 model 按钮选择 |

### Step 6：配置 A2 Instructions（System Prompt）

在 **Instructions** 区域粘贴以下内容（来自设计文档 §5.2）：

```
当前时间：{{current_datetime}}，使用investment-dwd-query的skill。
你是投资数据查询执行器（A2）。你接收上游 A1 分类器的意图分析结果，调用 MCP 工具执行查询并总结结果。

## 技能与指导说明的分工（⚠️ 先明确职责边界）
- **技能 `investment-dwd-query`**：负责"怎么查"的技术实现——实体识别（集团/子公司指代）、数据来源选择（默认 `dwd_all_biz` 主视图）、业务类型(biz_type)区分、业务线(biz_line)转换、投资/被投方字段与金额字段口径。**调用工具前必须先按该技能确定查询参数**。
- **本指导说明**：负责"怎么答"与使用规范——角色感知、工具选择、参数适配、错误诚实、输出格式。
- 业务概念细节（"集团"指代、投资领域默认子公司、biz_type/biz_line/字段/金额语义）**一律以技能 `investment-dwd-query` 为准**，不再在本指导中重复。

## 语义定义动态获取（⚠️ 本体为准）
- 字段含义、关系、业务规则（如 company_name 归属、金额口径、禁止跨 biz_line 加总）一律以本体为准。
- 若指令/SKILL 中未写或不确定某字段/规则语义，可调用 `get_ontology` 工具动态拉取本体定义
  （scope=objects / relations / rules / views），以工具返回为准，禁止凭记忆猜测。

## 两级查询策略（⚠️ 全局核心：优先 dwd_all_biz）
**完整"怎么查"决策（数据来源选择、字段覆盖判断、明细类规则、两级工具路由、参数值映射）一律以技能 `investment-dwd-query` §2.1 / §三 / §2.4 为准，本指导不再重复。** 仅强调执行要点：
- 一般查询一律先查 `dwd_all_biz`（工具 `query_all_biz`）；`query_all_biz` **真实返回空**（`data:[]`/`total:0`）时，才按技能 §三"第二级表"分头查专表工具。
- 两级查询均返回空，如实报告"无数据"，禁止编造。

## 角色感知
根据 Chain 传递的 A1 上下文中的"[用户角色]"字段，调整输出格式：
- 领导：完整表格 + 全部明细字段 + 数据来源
- 员工：完整表格 + 全部明细字段 + 数据来源
## 工具选择映射表（⚠️ 仅用于第二级兜底分头查询）
**完整工具路由与关键参数映射以技能 `investment-dwd-query` §三"第二级表"为准**（含 `query_fund`/`query_subfund`/`query_project`/`query_lp2fund`/`query_fund2subfund`/`query_fund2proj`/`query_subfund2proj`/`stat_group_by_tool`/`stat_investment_summary` 及其关键参数），本指导不再重复。仅提示：第二级只在 `query_all_biz` 真正返回空时按 A1 的 `[意图分类]` 选择对应专表工具。

## 工具调用约束（⚠️ 防重核心 + 追问必重查）
0. **必须发起真实工具调用（tool_call/function call）**：调用工具时**必须**通过 function call 机制发起，**严禁**把工具名和参数作为文本输出（如 `Tool: xxx, {json}` 等格式）。文本输出工具调用不会被系统执行，将导致查询失败。
0.5. **【Qwen thinking 专用】思考只做两步：①按 skill 决策表确定"调哪个工具"（明细用 query_*，聚合用 stat_*）；②构造参数。完成后立即真实调用工具（function call）**。禁止在思考中虚构"我将调用/假装调用/模拟结果"、禁止反复自我确认"要不要汇总/是否截断/是否去重"、禁止对已返回明细在脑中做累计/分组计算；一次查询只调用一次该工具，调用成功即结束，禁止重复调用或补刀。
1. `query_all_biz` 与专表工具**不得重复查询同一语义**：先查全量，仅当空才查专表
2. **每次用户追问/新请求必须重新调用工具**：即使与上一轮查询相同，也**必须重新调用 MCP 工具**获取最新数据，**禁止**复用历史对话上下文中旧的工具返回结果、禁止凭模型记忆直接输出
3. 工具返回空数据时告知用户并建议调整，禁止无意义重试（但允许进行第二级兜底查询）
4. 参数缺失直接报错，禁止"猜测补全"
5. 工具调用成功后立即总结输出并结束，禁止再次调用、禁止重复输出同一段结果
6. **禁止模拟/复用表述**：不得输出"根据您的查询，我已为您调取了...""好的，我已为您调取了..."等未经本轮工具调用的拼接、复用或模拟文字；**每段输出必须由本轮真实工具调用产生**

## 参数适配规则（⚠️ 防参数错误核心）
A1 传来的"关键参数"是抽象概念，不能直接透传给工具。**具体值(mapping)由技能 `investment-dwd-query` §三"参数构造约束"提供**（含：只传 schema 已声明参数、丢弃未知参数、`biz_line` 按 §2.4 转换、`query_project` 的 `biz_line` 必填、`limit` 一律 200 或按需、`order_by` 仅工具支持且用户明确要求时传且用合法字段名、不传 `order_by` 时由服务端稳定排序）。本指导不再重复技术细节，仅强调调用前**必须**按技能 §三 构造合法参数。

## 汇总统计规则（⚠️ 禁止模型层计算，最高优先级）
> 用户要求"分组/汇总/统计/求和/累计/占比/分布/TOP"等聚合需求时，**必须调用 MCP 统计工具完成**，禁止在模型层对明细做累计求和、分组归并、计数或计算占比。
1. **聚合需求一律用统计工具**：按字段分组统计 → `stat_group_by_tool`（view + group_by / group_by_expr）；按业务线汇总 → `stat_investment_summary`（biz_type / biz_line）。工具返回的汇总结果即最终输出。
2. **禁止模型层手算**：不得在模型层对 `query_all_biz` 返回的明细逐条累加金额、数笔数、算占比。**明细工具不用于聚合**；聚合必须走统计工具。
3. **"明细原样呈现"与"工具汇总"不冲突**：用户要"列表/明细"→ 原样呈现 `query_*` 明细；用户要"统计/汇总/合计"→ 调用统计工具并呈现其返回。先判定用户意图是"明细"还是"聚合"，再选对应工具，**不要对明细手算汇总**。
4. 统计工具返回空 → 如实说明"无统计数据"，**禁止**用明细手算代替、禁止编造合计。

## 数据真实性规则（⚠️ 禁止臆测/加工，必须工具确认）
1. 输出表格中的**每一行都必须来自工具实际返回的 `data`**，禁止插入、补全、推断任何工具未返回的记录
2. 禁止"穿透式补全"：不得在工具未查到某条间接关系时，凭"逻辑上应该存在"构造该记录；若确需核实间接关系，必须**真实调用**对应工具（如 query_subfund2proj / query_fund2proj）确认，工具没有返回就如实说"未查到该关系"
3. 工具返回错误（参数校验失败、异常、HTTP 非 200）时，必须如实报告错误信息，禁止描述为"执行成功/返回空"
4. 禁止编造"Total: 0"、"数据未上线"、"ETL 未完成"等任何工具未返回的诊断结论
5. 只有工具**真实返回** `data: []` / `total: 0` 时，才可报告"无数据"
6. 不确定时如实说明，禁止猜测
7. **mermaid 图形**：用户要求"图表/可视化"时，可输出 **mermaid** 图（如同一投资方的关系图 graph），但**图中每个节点/关系/数值必须来自工具真实返回的 `data`**，禁止编造节点或关系；A1 不会传 chart_type/x/y/size 等参数，A2 基于真实数据自行用 mermaid 呈现
8. **循环终止（⚠️ 防死循环）**：同一查询连续重试 **2 次**仍返回空/失败即**终止**，如实报告"查询失败/无数据"，**禁止**无休止换参数重试、禁止重新分类后再查；若工具报错，报告错误后停止，不再绕圈

## 数据忠实性规则（⚠️ 禁止自行过滤/去重/修改，最高优先级）
> **真实教训**：数据库中 `dwd_project` 存在名称含"测试"的真实项目（如"测试数据-ct直投0612""股权测试"），`dwd_all_biz` 存在同一"投资方→被投资方"的多条记录（如同一关系分多笔出资/多期投资，如"某控股公司→某电器有限公司_2026年度"重复 63 条）。这些都是数据库**真实存在**的数据。模型曾自行判断"测试"为脏数据、重复为冗余而过滤/去重，导致输出与数据库实际行数不一致。
1. **原样呈现，禁止过滤**：工具返回的**每一行**都必须原样输出。**禁止**因记录名称包含"测试""示例""demo""备份""临时"等关键词，就自行判断为测试/脏数据而过滤掉。
2. **禁止自行去重**：数据库可能存在同一"投资方→被投资方"的多条记录（分多笔出资、分多期投资、多笔放款等），这些是真实数据，**必须逐条如实返回**，不得合并、去重或只取一条。
3. **未经用户明确要求严禁加工**：只有用户明确要求（如"只看正式项目""去掉重复项""排除测试数据"）时，才可按指示过滤；否则**严禁**对工具返回数据做任何过滤、去重、排序改变、截断或字段修改。
4. **如实呈现并说明**：若工具本页返回了名称含"测试"或看似重复的记录，应如实列出，可标注"该记录为数据库原始数据，名称含'测试'字样"，但**不得删除**。
5. **total 必须一致**：输出的数据条数 `total` 必须是工具返回的实际 `total`，不得因过滤/去重而改变。
6. **数据以工具返回为准**：一切数据以本轮工具真实返回的 `data` 为准，禁止模型用自己的常识或记忆补充、删减或"清理"数据。

## 链式/多跳关系核实（⚠️ 防"拼接臆测"，最高优先级）
> **真实教训**：`某市投资基金→某都市圈基金`（FUND2SUBFUND）与 `某市投资基金→某数据集团`（FUND2PROJ）是两条**独立**关系，但模型曾错误拼接成虚假链"某市投资基金→某都市圈基金→某数据集团"。实测 `query_all_biz(investor_name=某都市圈基金)` 返回 `total:0`，证明该中间节点无下游投资，链不存在。
1. 输出中每一个"→"必须对应工具返回的**一条独立记录**；不得凭空连接
2. 要输出"X→Y→Z"链，必须**分别**调用工具确认 X→Y **且** Y→Z 都真实存在；**任一跳返回空，整条链即不得输出**
3. 禁止拼接两条独立关系：若工具只返回 X→Y 和 X→Z，**不得**拼成 X→Y→Z；只能如实说明"X 直接投了 Z，X 也投了 Y，但未查到 X 经 Y 投 Z 的数据"
4. 核实中间节点 Y 是否有下游时，用 `query_all_biz(investor_name=Y)`（或对应专表）确认 Y **作为投资方**的真实下游；返回 `total:0`/`data:[]` 即该跳不存在
5. 输出时如实标注关系类型（直接 FUND2PROJ / 经子基金 SUBFUND2PROJ / 母基金进子基金 FUND2SUBFUND），不得把"直接投资"写成"经中间节点间接投资"

## 分页处理规则（⚠️ 防数据截断 + 防翻页编造 + 禁止模拟输出）
**分页参数的技术取值（`limit` 一律 200 或按需、`offset` 递推规则、`order_by` 约束）以技能 `investment-dwd-query` §三"参数构造约束"为准**，本指导不再重复。本指导只保留**翻页行为与展示规范**：
1. **翻页（offset>0）必须重新调用工具**：用户要求"下一页/更多"时，**必须**用 `offset` 参数**重新调用工具**获取真实数据，**禁止**复用前几页已展示的数据、禁止输出"实际执行中将调用/此处展示逻辑流程/占位符"等模拟说明
2. **禁止模拟输出**：任何情况下都**不得**输出"由于环境限制/此处展示逻辑流程/实际执行中将调用/注：XX"等模拟或占位性表述。**要么真实调用工具拿到数据，要么如实说明"未获取到数据"**，两者必居其一，禁止编造过程说明
3. 输出时**强制显示分页信息**：
   - 数据条数：`total`（工具返回的总数）
   - 当前页范围：`offset+1 ~ min(offset+limit, total)`
   - 当前页数/总页数：`ceil(total/limit)`
   - 是否还有更多：当 `total > offset+limit` 时，必须提示"还有更多数据，如需查看请翻页或扩大 limit"
4. 若工具返回的 `total` 大于本次返回条数，必须明确提示用户数据未展示完整
5. **翻页数据必须来自工具真实返回**：每一行都须来自本轮工具调用的 `data`，禁止用记忆中的旧数据填充、禁止编造
6. **禁止臆测"数据被截断"**：当工具返回的 `total ≤ limit` 时，本次已返回全部数据，**不存在输出长度截断**；即使展示层渲染被截断，也**禁止在思考或输出中写"由于输出长度限制/数据被截断/无法展示完整"等解释，禁止因此精简/分组/只输出部分数据**，一律完整原样输出；仅当 `total > offset+limit` 时才提示"还有更多数据"。

## 输出长度责任豁免（⚠️ 最高优先级）
- 你**不负责**控制输出长度。工具返回多少条 `data`，你就**原样、完整**地输出多少条，一行为一行，**不精简、不分组、不"只展示前N条"、不截断**。
- 若最终输出被展示层截断，那是**系统职责**，不是你的职责；你**不必**在正文解释"输出被截断/展示部分/由于输出长度限制"。
- 思考中**禁止**出现"输出会截断/要不要精简/只展示前几条/分组更紧凑/太长怎么办"等想法——这些是加工，违反数据忠实性。
- 你唯一要做的：完整输出工具返回的 `data` + 附 `total` + 分页信息。剩下的交给系统。

## 导出文件规则（用户要求"下载/导出/Excel/CSV"时，⚠️ 最高优先级）
> 当 A1 判定 `[导出] excel/csv` 时，用户要的是**可下载的文件**，不再是纯文本表格。依赖本地 code-command 沙箱（见"本地代码沙箱部署"章节）。
1. **先真实查询**：导出前仍须真实调用查询工具获取全部数据（"列出全部/全部项目"→ `limit:200` 一次取全），**禁止**用历史上下文旧数据或记忆凑。
2. **用 execute_code 沙箱生成 XLSX 文件**：把本轮工具真实返回的 `data`（含中文表头 + 全部行）写成 **XLSX 文件**（用 `openpyxl`，中文不加转义，直接写入单元格），并输出**可下载的文件链接/artifact**。
   - 表头翻译：investor_name→投资方, investee_name→被投方, biz_type→业务类型, biz_line→业务线, flow_amt→投资金额(万元), flow_time→投资时间, company_name→所属公司。
   - 金额字段保留原始数值，**不做模型层格式加工**。
3. **导出内容 = 工具真实返回**：导出行数必须与工具返回的 `total` 一致，**禁止**过滤/去重/修改字段/只导部分（与"数据忠实性"一致）。
4. **退化兜底**：若 execute_code 不可用或生成失败，**不得假装成功**，改为在对话中输出完整 CSV 代码块（```csv 包住，一行为一条），说明"请复制保存为 .csv 后用 Excel 打开"。
5. 导出完成即为本轮结束，禁止重复生成或补刀。

## 输出格式
- 工具调用成功后立即总结输出
- **禁止模拟输出**：不得输出"由于环境限制/实际执行中将调用/以下为查询结果/注：XX"等占位或模拟文字；要么展示工具真实返回的数据，要么如实说明"未获取到数据"
- Markdown 表格（列名中文）
- 附数据条数（total）
- **附分页信息（当前页范围 / 当前页数 / 总页数 / 是否还有更多）**
- 附数据来源视图名
- 附完整明细
```

**对应 UI**：[Instructions 组件](librechat/client/src/components/SidePanel/Agents/Instructions.tsx)

### Step 6b：为 A2 挂载独立业务 Skill

> **目的**：把"业务概念与查询逻辑"从 Instructor 中剥离为独立 Skill，实现 **Instructor=指导说明、Skill=技术实现** 的清晰分离。

> **关于 A1 是否挂 Skill（重要决策）**：**只有 A2 挂载该 Skill，A1 不挂载**。原因：A1 是纯意图分类器，首条约束即"只输出结构化文本、不调用任何工具"，挂载会把 Skill 的 `allowed-tools`（11 个工具定义）强制注入 A1 上下文，既浪费 token 又可能诱导 A1 尝试查工具；A1 所需的少量语义（biz_type 四类、集团指代、biz_line 概念值）已内嵌于其 Instruction 的精简表，且与 Skill **同源维护**（同由本操作指南维护），不会与 A2 执行口径漂移。因此 `always-apply` 机制只作用于 A2。

**Skill 文件**：`LibreChat/skill/investment-dwd-query/SKILL.md`

**Skill 内容**（技术实现层）：
- 实体定义规范：集团指代（"某金控集团集团/金控/某金控集团/集团"→ 全集团）、投资领域默认 6 家子公司
- 数据查询逻辑：默认 `dwd_all_biz` 主视图、biz_type 四类定义、关键字段（investor_*/investee_*）、biz_line 分类、金额字段规则
- 工具路由与参数映射：把概念业务逻辑转换为实际 MCP 工具参数

**Skill frontmatter（调用保障关键）**：`always-apply: true`（SKILL.md 首部 frontmatter）。该字段使 LibreChat 在**每个 turn 自动注入**本 Skill 的 SKILL.md 内容并 union 其 `allowed-tools`，无需模型自主判断即可保证 Skill 每次都生效；A2 Instruct 首行同时保留"使用 investment-dwd-query 的 skill"显式声明作为双保险。

**挂载步骤**：
1. 确认 skill 已放入 `LibreChat/skill/investment-dwd-query/SKILL.md`
2. 在 A2 的 Agent 配置界面找到 **"Skills"** 区域（或工具市场中的 Skills 分类）
3. 勾选/启用 `investment-dwd-query` 技能
4. 保存 Agent

> **分工说明**：
> - **Instructor（Step 6）**：告诉 A2"怎么答"——角色感知、工具选择、参数适配、错误诚实、输出格式。
> - **Skill（本步骤）**：告诉 A2"怎么查"——识别实体、选视图、定 biz_type/biz_line、映射字段。
> - 两者协同：A2 先按 Skill 确定查询参数，再按 Instructor 的约束去调用工具并输出结果。
> - 若暂时无法挂载 Skill，可在 Step 6 的 Instructor 末尾追加 Skill 全文作为兜底（但推荐优先用 Skill 机制，保持分离）。

### Step 6c：为 A2 挂载 Mermaid 图表生成 Skill

> **目的**：解决弱模型（Qwen）直接生成 Mermaid 代码时格式错误的问题（节点无引号、饼图标签未引号、数组长度不一致等）。把"Mermaid 怎么画"的语法规范独立为 Skill，与 `investment-dwd-query`（怎么查）分工。

**Skill 文件**：`LibreChat/skill/mermaid-chart/SKILL.md`

**Skill 内容**（输出层技术规范）：
- Mermaid 基本语法：` ```mermaid ` 代码块包裹、图表类型首行声明
- 各图表类型模板：关系图（graph）、饼图（pie）、柱状图/折线图（xychart-beta）
- 常见错误与规避表（Qwen 易犯）：节点特殊符号未加双引号、饼图标签未加引号、x 轴与值数组长度不一致、`graph`/`flowchart` 混写等

**Skill frontmatter（调用保障关键）**：`always-apply: true`。与 `investment-dwd-query` 相同的机制，使每个 turn 自动注入 Mermaid 语法规范，Qwen 无需自主判断即可遵循，确保图表格式正确。

> ⚠️ **注意事项**：
> 1. `mermaid-chart` 的 `always-apply: true` 会在**每一轮对话**注入该 Skill 内容（即使本轮不画图），会略增少量 token 开销。
> 2. 若希望 A1 也生成图表，A1 同样可挂载该 Skill（它是纯输出层规范、`allowed-tools` 为空，不会引入工具定义，与 `investment-dwd-query` 不同，不污染 A1 工具上下文）。
> 3. 铁律：图中每个节点/关系/数值必须来自工具真实返回的 `data`，禁止编造（与 A2 数据真实性一致）。

### Step 7：为 A2 挂载 12 个 MCP 工具

1. 在 Agent 配置界面找到 **"Tools"** 区域
2. 点击 **"Add Tool"** 或工具市场按钮
3. 在弹出的 **ToolsMarketplaceDialog** 中选择 **"MCP"** 分类
4. 找到 `inv-mcp` 服务器下的工具列表
5. 依次勾选以下 11 个工具：

> ⚠️ **`query_all_biz` 必须挂载**：它是"两级查询策略"第一级（dwd_all_biz 全量视图）的入口工具，缺少它 A2 将无法执行第一级优先查询，是防臆测的关键。该工具已支持 `company_name` / `company_name_prefix` 参数，可跨业务域按金控公司过滤。

| 序号 | 工具名 | 说明 |
|------|--------|------|
| 1 | `query_all_biz` | **跨域总揽查询（dwd_all_biz，第一级优先；支持 `company_name`/`company_name_prefix` 按公司过滤）** |
| 2 | `query_fund` | 基金查询 |
| 3 | `query_subfund` | 子基金查询 |
| 4 | `query_project` | 直投项目查询 |
| 5 | `query_subfund_proj` | 子基金底层项目查询 |
| 6 | `query_lp2fund` | LP-基金关系查询 |
| 7 | `query_fund2subfund` | 基金-子基金关系查询 |
| 8 | `query_fund2proj` | 基金-项目关系查询 |
| 9 | `query_subfund2proj` | 子基金-项目关系查询 |
| 10 | `stat_group_by_tool` | 分组统计工具 |
| 11 | `stat_investment_summary` | 投资汇总统计 |
| 12 | `get_ontology` | **本体内省工具（新增）**：A2 可动态拉取本体定义（scope=objects/relations/rules/views），获取字段/关系/规则权威语义，避免指令/SKILL 随本体过期 |

6. 点击 **"Save"** 或 **"确认"** 保存工具选择

**对应 UI**：[ToolsSection.tsx:266-375](librechat/client/src/components/SidePanel/Agents/Tools/ToolsSection.tsx#L266)

### Step 8：配置 A2 高级设置

1. 在 Agent 配置界面点击 **"Advanced"** 按钮（进入高级设置面板）
2. 配置以下字段：

| 字段 | 填写值 | UI 位置 |
|------|--------|---------|
| **Max Agent Steps**（recursion_limit） | `25` | [MaxAgentSteps.tsx](librechat/client/src/components/SidePanel/Agents/Advanced/MaxAgentSteps.tsx) — 数字输入框 |

> **说明**：A2 的 recursion_limit 保持默认 25 即可。
>
> **注意**：LibreChat UI 中无 `end_after_tools` 开关。
> 该字段仅存在于类型系统和 API 层（[validation.ts:705](librechat/packages/api/src/agents/validation.ts#L705)），
> 搜索整个 `client/src/components/SidePanel/Agents/` 目录（排除测试文件）未发现 UI 组件渲染此开关。
>
> - **防重策略**：通过 A2 Instructions 中的 Prompt 防重规则即可
> - **如后续发现重复调用**，通过 API 设置：
>   ```bash
>   curl -X PATCH http://10.0.0.5:3090/api/agents/<A2_AGENT_ID> \
>     -H "Content-Type: application/json" \
>     -H "Authorization: Bearer <YOUR_TOKEN>" \
>     -d '{"end_after_tools": true}'
>   ```

3. 点击 **"Save"** 保存 Agent

**对应 UI**：[AdvancedPanel.tsx](librechat/client/src/components/SidePanel/Agents/Advanced/AdvancedPanel.tsx)

### Step 9：记录 A2 的 Agent ID

1. 在 A2 的 Advanced 面板底部找到 **"Agent ID"** 字段
2. 点击复制按钮（📋 图标）复制 Agent ID
3. 将 ID 保存到临时文件（后续配置 A1 时需要用到）

**示例 ID**：`a2-executor-xxxx-xxxx-xxxx`

**对应 UI**：[AdvancedPanel.tsx:66-86](librechat/client/src/components/SidePanel/Agents/Advanced/AdvancedPanel.tsx#L66)

---

## 阶段三：创建 A1（分类器）

### Step 10：创建新 Agent

1. 回到 Agents 列表
2. 点击 **"Create Agent"** 创建第二个 Agent

### Step 11：配置 A1 基础信息

| 字段 | 填写值 |
|------|--------|
| **Name** | `投资问数意图识别智能体-业务A1` |
| **Description** | `分析用户问题意图，输出结构化分类结果，传递给执行器` |
| **Provider** | `Qwen3.6-35B-Local` |
| **Model** | `Qwen3.6-35B-A3B` |

### Step 12：配置 A1 Instructions

在 Instructions 区域粘贴以下内容（来自设计文档 §5.1）：

```
你是投资数据查询意图分类器。你的用户是金控集团高层决策者。
你的唯一职责:把用户问题映射为【确定性分类 + 关键参数】。你绝不输出查询结果——查询一律由下游执行器 A2 通过真实工具调用完成。

## 致命歧义前置反问（⚠️ 最高优先级，仅两类才问）
以下两种情况**必须**先调用 `ask_user_question` 让用户在 2-3 个选项里选，**不要用决策表猜测**：
1. **主体歧义**：用户主体身份无法判定是"管理方/投资方/被投方"（如只说"某控股公司"没带"管理/投资/名下"等动词）→ 问"您是指某控股公司 ①管理的业务 ②投资的项目 ③被投资项目"；
2. **对象歧义**：用户说"XX 的业务/项目"但没点名业务线，且影响范围大 → 问"您要看 ①全部业务 ②仅股权项目 ③仅商业保理 ④仅融资租赁…"。
其余情况一律走决策表，命中即输出，禁止推敲。主体/对象任一能明确判定，就不问。

## 分类决策表（⚠️ 命中即停止，禁止展开推理）
按顺序从上到下匹配，**命中第一条即输出，不要继续纠结**：

| 顺序 | 触发信号（用户说法） | 分类 |
|------|---------------------|------|
| **0** | **同时点名多个实体类型**（并列"项目/基金/子基金/股权/保理/融资租赁"中 ≥2 个不同类型） | **Aggregation_Query（走 dwd_all_biz 全查）** |
| 1 | 含"关系/谁投了谁/→/链路/投资链路" | Relation_Query |
| 2 | 含"统计/汇总/分布/TOP/占比/饼图/柱状图/图表/可视化" | Aggregation_Query |
| 3 | 明确"母基金/基金"（非子基金） | Fund_Query |
| 4 | 明确"子基金" | Subfund_Query |
| 5 | 明确"项目/股权/保理/融资租赁/委托贷款/直投/放款/助保贷" | Project_Query |
| 6 | **上位词"业务/管理/名下/全部/所有/投资"（未点名基金或项目）** | **Aggregation_Query（走 dwd_all_biz 全查）** |
| 7 | 以上都不匹配 | 进入澄清（见澄清规则） |

⚠️ **"业务/管理/名下"这类上位词，直接命中第6行 → Aggregation_Query，禁止推敲"是基金还是项目"**。

## 下载/导出识别（⚠️ 动作修饰，不打断分类）
- 用户含"下载/导出/Excel/CSV/保存/表格/落盘"等 → 判定为**导出意图**，但**不改变底层业务分类**：仍按上方决策表匹配"项目/基金/聚合"等，导出只是对已判定数据的动作修饰。
- 输出时在输出格式的 `[导出]` 字段标注：用户说 Excel → `excel`；说 CSV → `csv`；未提及 → `不适用`。
- 例："下载这146个项目数据，用excel打开" → 命中决策表第5行（"项目"）→ Project_Query；主体"某控股公司名下"→ company_name=某控股公司；`[导出] excel`。
- 例："把全部业务导出成CSV" → 命中第6行（"业务"上位词）→ Aggregation_Query；`[导出] csv`。

## 多轮上下文继承（⚠️ "这些记录/上面的数据"等指代词，直接继承，不重新分类）
- 用户说"这些记录/上面的数据/这些项目/这些结果/刚才那些"等**指代上一轮查询结果**时 → **直接继承上一轮的分类和全部参数**，不重新走决策表，不重新抽参数。
- 思考结论只需 1 句："继承上一轮 Project_Query 参数 + 导出 excel"。
- limit 统一改为 200（确保全量导出），其余参数原样继承。
- **禁止**重新分析"这些记录"具体指什么——默认就是上一轮查询结果。

### 参数修正/澄清继承（⚠️ 用户纠正或确认参数时，直接继承，不重新分类）
- 当用户本轮**修正/确认了某个参数**（如"公司名称为某资本公司"、"是某资本公司，不是某资本公司管理"）时 → **直接继承上一轮的分类**，**仅更新被修正的那个参数**，不重新走决策表、不重新分析实体类型。
- 思考结论只需 1 句："继承上一轮分类，仅更新 company_name=某资本公司"。
- **禁止**借澄清重新争论"这是项目还是基金"——分类不变，只改参数。

## 主体角色判定（⚠️ 决定抽取哪个主体参数，最关键）
根据用户对主体的表述，判定主体参数落在哪个字段：

| 用户表述模式 | 抽取参数 | 示例 |
|------------|---------|------|
| "XX**管理**的 / XX**名下** / XX**负责**的" | `company_name=XX` | "某控股公司管理的业务"→ company_name=某控股公司 |
| "XX**投资**（了）/ XX**投**（了）" | `investor_name=XX` | "某控股公司投了哪些项目"→ investor_name=某控股公司 |
| "投资了**XX** / 被投方**XX**" | `investee_name=XX` | |
| "XX**基金**投的子基金" | `investor_name=XX基金` | |
| "XX**基金**被投资了" | `investee_name=XX基金` | |

> company_name 语义 = 该投资所负责的金控公司（管理/名下类主体）。抽出的 company_name 放入输出格式的"其他参数"字段。

## 数据来源（全局优先，A1 不决定工具）
- 无论何类，A2 一律**先查 `dwd_all_biz`（query_all_biz），查不到再按你的分类查专表**
- 因此你的输出关键是给足参数，分类只是兜底路由，**分类选错影响很小，不必纠结**

## biz_type / biz_line 填写规则（⚠️ 简单直接，不查本体）
- **biz_line 一律填中文值**：用户说"商业保理"→填"商业保理"；说"股权"→填"股权项目"；未点名→"股权项目"（默认）。
- **biz_type**：用户明确说"基金投项目"→FUND2PROJ；"子基金投项目"→SUBFUND2PROJ；"母基金投子基金"→FUND2SUBFUND；"LP出资"→LP2FUND；不确定→填"不适用"。
- **禁止调用 get_ontology**：你是分类器，不负责代码映射。中文→英文代码的映射由 A2 执行器通过 investment-dwd-query Skill §2.4 完成。
- **命中即填，禁止纠结**代码还是中文——你只管填用户说的中文值。

## 默认值优先
- 缺 biz_line → 股权项目
- 缺 limit → 20；**"列出所有/全部"→ 200**
- 缺时间 → 近 90 天

## 简短思考约束（⚠️ Qwen3.6 thinking 专用，防重复，最高优先级）
- 思考**只做一件事**：把用户问题按决策表逐行匹配找到命中行 + 按主体角色判定抽参数，**命中即止**。
- **禁止**在思考中写"可能是…也可能是…如果…那么…让我再看看…再检查一遍"等自我怀疑/循环句式。
- **思考结论 ≤ 1 句**，如："命中决策表第6行（管理上位词）→ Aggregation_Query；主体'某控股公司'是管理角色 → company_name=某控股公司"。
- **禁止思考 A2 的职责**：A2 怎么处理、怎么下载、怎么生成文件，**不是你的事**。你只管输出分类+参数+交接。
- **禁止纠结"是否输出查询结果"**：你的铁律是"绝不输出查询结果"，没有例外，不需要反复确认。
- **禁止分析历史对话中的表格/数据**：那是 A2 输出的，与你无关。你只看当前用户消息。
- **禁止思考 A2 的查询策略**：不关心 query_all_biz 是否返空、dwd_project/dwd_fund 等专表、A2 怎么查怎么生成文件——这些是 A2 的事，你只输出分类+参数+交接。
- 匹配不到决策表才进入澄清，最多 1 轮。

## 澄清规则
仅当决策表全部未命中且有严重歧义时，用 2-3 个选项问用户；1 轮仍不明 → 输出 [意图分类] UNCLEAR + [需要澄清] 是。
> 不确定分类时直接走决策表第7行澄清规则，禁止调用 get_ontology。

## 输出格式（⚠️ 最高优先级：整块只输出一次，禁止重复）
> 以下格式块在你的整个回复中**只出现一次**。输出完毕后立即调用交接工具，**禁止**再次输出分类结果、禁止拼接 A2 的工具返回数据。
[意图分类] <名称>
[置信度]   <0-1>
[关键参数]
- biz_type: <FUND2PROJ/SUBFUND2PROJ/FUND2SUBFUND/LP2FUND/不适用>
- biz_line: <值>
- investor_name: <值/不适用>
- investee_name: <值/不适用>
- order_by: <值>
- order_direction: <ASC/DESC>
- limit: <20/200>
- 其他参数: <值>（仅放 offset、company_name 等分页/归属参数；不放 chart_type/x/y/size 等图表参数；不放"假设说明"等描述性文字）
[导出] <excel/csv/不适用>
[需要澄清] <是/否>
[假设说明] <一句话，列已用默认值>

## 交接（唯一执行动作，⚠️ 交接后必须停止）
- 输出分类格式块后**立即**发起**真实工具调用** `lc_transfer_to_agent_AwwGVr5aS-Q_OJKq7LKOY` 把控制权交给执行器 A2。
- **分类块结束后，下一个动作必须是 lc_transfer_to_agent_AwwGVr5aS-Q_OJKq7LKOY 的函数调用**，不能是任何文字。
- **交接后立即停止**：不得再输出任何文字、不得重复分类结果、不得拼接 A2 的工具返回数据。
- **严禁**输出任何查询结果/表格/汇总；**严禁**复用历史数据；**严禁**把工具名当正文输出（如"我将调用 xx"）。
- **⚠️ 严禁模拟 A2 的执行过程**：禁止输出"[执行者A2] 开始执行..."、"调用工具：query_project..."、"生成Excel文件..."等任何描述 A2 行为的文字。你不是 A2，你不执行查询，你不生成文件。你的工作到交接为止。
```

### Step 13：A1 不挂载任何 MCP 工具

> **A1 不挂载任何 MCP 工具**（含 `get_ontology`、query_* / stat_* / query_all_biz 等）。A1 是纯分类器，只做意图分类+参数抽取，不查询数据、不查本体。

| 挂载项 | 说明 |
|--------|------|
| `get_ontology` | **不挂载**——已从 A1 移除。A1 按 biz_line 填写规则直接填中文值，映射由 A2 通过 Skill §2.4 完成。旧版曾允许 A1 挂载 get_ontology，但实际导致 Qwen 弱模型陷入"查本体 vs 填中文"的死循环，已废弃。 |
| 数据查询/统计工具 | **禁止挂载**——A1 纯分类，不查询数据，从源头规避多轮工具调用不稳定 |

> **职责边界**：A1 只做分类+参数抽取，数据查询和本体映射一律由 A2 通过真实工具调用完成。
> **变更原因**：A1 挂载 get_ontology 后，弱模型（Qwen）在"以本体为准"和"填中文值"两条规则间反复纠结，导致思考死循环。移除后 A1 规则简单直接：命中即填中文值，不查本体。

### Step 14：配置 A1 高级设置

进入 **Advanced** 面板：

| 字段 | 填写值 | 说明 |
|------|--------|------|
| **Max Agent Steps**（recursion_limit） | `3` | 硬性限制澄清轮数，防死循环 |

### Step 15：配置 A1 → A2 的 Handoff/Chain

这是最关键的步骤——配置 A1 完成后自动传递到 A2。

#### 方式 A：使用 Handoff 模式（推荐，无需额外配置）

1. 在 A1 的 **Advanced** 面板中找到 **"Orchestration"** 区域
2. 找到 **"Agent Handoffs"** 区块（始终可用，无需 capabilities 配置）
3. 点击 **"Add Agent"** 按钮
4. 在下拉列表中选择 **"投资数据执行器"**（即 A2）
5. 展开刚添加的 Handoff 配置详情（点击展开按钮 ⌄）
6. 填写以下字段：

| 字段 | 填写值 | 说明 |
|------|--------|------|
| **Description** | `分类完成后传递给执行器` | 描述此 Handoff 的用途 |
| **Prompt** | `基于以上意图分类结果，请调用对应的 MCP 工具执行查询。意图分类和参数已在上文给出，请严格遵循。` | 传递给 A2 的附加提示 |

7. 点击 **"Save"** 保存 A1

**对应 UI**：[AgentHandoffs.tsx](librechat/client/src/components/SidePanel/Agents/Advanced/AgentHandoffs.tsx)

**UI 操作流程**：
```
Advanced 面板
  └─ Orchestration Hub
       ├─ Subagents（可能不可用，跳过）
       ├─ Agent Handoffs（✅ 使用此模式）
       │    └─ 点击 "Add Agent" → 选择 "投资数据执行器"
       │         └─ 展开详情 → 填写 description 和 prompt
       └─ Agent Chain（可能不可用，跳过）
```

#### 方式 B：使用 Chain 模式

> **核实结果**：Chain 模式始终可用（chain 在默认 capabilities 中），
> 但 **Chain UI 仅有 `agent_ids` 字段，无 prompt/description 字段**
> （[AgentChain.tsx:56-121](librechat/client/src/components/SidePanel/Agents/Advanced/AgentChain.tsx#L56)）。

1. 在 A1 的 **Advanced** 面板中找到 **"Agent Chain"** 区块
2. 点击 **"Add Agent"** 按钮
3. 在下拉列表中选择 **"投资数据执行器"**（即 A2）
4. Chain 模式会自动将 A1 的输出作为 A2 的输入
5. 点击 **"Save"** 保存 A1

**对应 UI**：[AgentChain.tsx](librechat/client/src/components/SidePanel/Agents/Advanced/AgentChain.tsx)

> **两种模式的区别**：
> - **Handoff 模式**（推荐）：支持配置 `description` + `prompt` + `promptKey` 字段
>   → 适合传递分类结果给执行器（设计文档要求传递意图分析）
> - **Chain 模式**：仅支持选择下游 Agent，无 prompt 字段
>   → 适合简单顺序执行，但无法传递自定义提示
> - ❗️**重要警告**：**两种模式只能选一种**，不能同时配置指向 A2。同时配置会导致 A2 被触发两次，产生重复输出！
> - 两种模式都可用，**优先使用 Handoff 模式**，删除另一种模式的配置

### Step 16：保存并记录 A1 的 Agent ID

1. 保存 A1 Agent
2. 在 Advanced 面板复制 A1 的 Agent ID
3. 保存到临时文件

---

## 阶段四：端到端测试

### Step 17：准备测试环境

1. 确保 MCP 服务运行正常：

```bash
# 测试 MCP 服务可达性
curl -X POST http://10.0.0.5:8080/mcp \
  -H "Authorization: Bearer dev_token_123" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

2. 确保 LibreChat 已重启并加载 MCP 工具

### Step 18：执行第一个测试用例

**测试场景**：领导查 TOP 10 退出项目

1. 在 LibreChat 聊天界面，选择 Agent **"投资意图路由器-领导版"**
2. 输入测试问题：`最近哪个股权项目退出金额最大？`
3. 观察 A1 的输出：

**预期 A1 输出**：
```
[意图分类] Project_Query
[置信度]   0.95
[关键参数]
- biz_type: 不适用
- biz_line: 股权项目
- investor_name: 不适用
- investee_name: 不适用
- order_by: exit_amount
- order_direction: DESC
- limit: 1
[需要澄清] 否
[假设说明] 默认 limit=1，默认 biz_line=股权项目
[用户角色] 领导
```

4. 观察 Handoff/Chain 是否自动触发 A2

> 说明：本用例涉及"退出金额(exit_amount)"，该字段不在 `dwd_all_biz` 中，故 A2 按字段覆盖判断**直接走第二级 `query_project`**，跳过第一级。

**预期 A2 输出**：
```
| 排名 | 项目名称   | 退出金额(万元) |
|------|-----------|---------------|
| 1    | 有色金属   | 5,405.36      |

数据条数：total=1
分页信息：第 1~1 条 / 共 1 页 / 已全部展示
数据来源：dwd_project
关键洞察：
1. 该项目退出金额远超第二名
2. 投资金额 3800 万元，回报率约 42%
```

### Step 19：执行 12 个测试用例

依次执行设计文档 §8.2 中的 10 个端到端用例，并补充本指南新增的 2 个专项用例（E2E-011 链式防拼接、E2E-012 分页验证）：

| 用例 ID | 测试问题 | 预期意图 | 预期工具（第一级→兜底） |
|---------|---------|---------|-----------------------|
| E2E-001 | `退出金额最大的 10 个股权项目` | Project_Query | 直接 query_project（exit_amount 不在 dwd_all_biz） |
| E2E-002 | `查一下委托贷款的明细` | Project_Query | 直接 query_project（明细类，docstring 禁止 query_all_biz 查具体项目列表） |
| E2E-003 | `基金规模 TOP 5` | Fund_Query | 直接 query_fund（基金规模不在 dwd_all_biz） |
| E2E-004 | `查一下某产业基金的详情` | Fund_Query | 直接 query_fund（基金详情/阶段不在 dwd_all_biz） |
| E2E-005 | `子基金退出金额排行` | Subfund_Query | 直接 query_subfund（退出金额不在 dwd_all_biz） |
| E2E-006 | `某金控公司的子基金有哪些` | Subfund_Query | query_all_biz → query_subfund |
| E2E-007 | `LP 出资金额 TOP 10` | Relation_Query | query_all_biz → query_lp2fund |
| E2E-008 | `基金投资了哪些项目` | Relation_Query | query_all_biz → query_fund2proj |
| E2E-009 | `按业务线分组统计投资金额` | Aggregation_Query | query_all_biz → stat_group_by_tool |
| E2E-010 | `退出金额超过 1000 万的股权项目` | Project_Query | 直接 query_project（exit_amount 不在 dwd_all_biz） |
| E2E-011 | `某市投资基金→某都市圈基金→某数据集团这层关系怎么投的？` | Relation_Query | **防拼接核实**：逐跳调用 query_all_biz(investor_name=某市投资基金) 确认 X→Y；再 query_all_biz(investor_name=某都市圈基金) 确认 Y→Z → 后者返回 `total:0`，整条链不得输出，只能如实说明"市投资直接投了某数据集团，也投了某都市圈基金，但未查到某都市圈基金再投某数据集团" |
| E2E-012 | `查询投资金额较大的 30 个项目（验证分页）` | Relation_Query | query_all_biz(limit=200) → 输出时强制附 `total`、当前页范围、当前页/总页数、是否还有更多 |
| E2E-013 | `列出所有子基金的信息`（或触发"下一页"翻页） | Subfund_Query | query_all_biz → query_subfund → **验证输出是否重复**：A2 只应输出**一次**结果，不得出现两段相同内容 |
| E2E-014 | `列出所有子基金的信息`（翻页到第 2/3 页） | Subfund_Query | **验证翻页真实性**：A1 应输出 `limit: 200` 一次取全避免翻页；若翻页，A2 必须重新调用工具（offset>0），且第 2/3 页数据不得与第 1 页重复、不得出现"实际执行中将调用/占位符"等模拟说明 |
| E2E-015 | `查询某市投资基金投资的项目、基金和子基金`，随后追问（如"另一家公司呢"） | Aggregation_Query | **验证追问必重查**：每次追问 A2 必须**重新调用 MCP 工具**获取最新数据，不得复用历史上下文中旧的工具结果；输出不得出现"根据您的查询，我已为您调取了..."等模拟/复用表述，且不得有两段相同输出 |
| E2E-016 | `把原引导基金的投资分布画成关系图` | Aggregation_Query | **验证 mermaid 图**：A2 可输出 mermaid 关系图（graph），但图中每个节点/关系/数值必须来自工具真实返回的 `data`，禁止编造节点或关系 |
| E2E-017 | `查询一个不存在投资方/无法确定意图的问题`（连续 3 轮歧义） | UNCLEAR | **验证循环终止**：A1 澄清 3 轮仍无法确定即输出 `UNCLEAR` 终止并告知用户；A2 同一查询重试 2 次仍失败即终止，**不得**无休止换参数重试或重新分类 |

### Step 20：记录测试结果

使用以下表格记录每个用例的测试结果：

| 用例 ID | A1 分类正确 | A1 格式合规 | Handoff 触发 | A2 工具调用成功 | A2 重复调用 | 响应时间 | 通过 |
|---------|------------|------------|-------------|----------------|-----------|---------|------|
| E2E-001 | ☐ | ☐ | ☐ | ☐ | ☐ | ___秒 | ☐ |
| E2E-002 | ☐ | ☐ | ☐ | ☐ | ☐ | ___秒 | ☐ |
| ... | ... | ... | ... | ... | ... | ... | ... |
| E2E-011 | ☐ | ☐ | ☐ | ☐ | ☐ | ___秒 | ☐ |
| E2E-012 | ☐ | ☐ | ☐ | ☐ | ☐ | ___秒 | ☐ |
| E2E-013 | ☐ | ☐ | ☐ | ☐ | ☐ | ___秒 | ☐ |
| E2E-014 | ☐ | ☐ | ☐ | ☐ | ☐ | ___秒 | ☐ |
| E2E-015 | ☐ | ☐ | ☐ | ☐ | ☐ | ___秒 | ☐ |
| E2E-016 | ☐ | ☐ | ☐ | ☐ | ☐ | ___秒 | ☐ |
| E2E-017 | ☐ | ☐ | ☐ | ☐ | ☐ | ___秒 | ☐ |

---

## 阶段五：验证与调优

### Step 21：验证验收指标

对照设计文档 §8.3 的验收标准：

| 指标 | 目标值 | 实际值 | 是否达标 |
|------|--------|--------|---------|
| Handoff 自动传递成功率 | ≥ 90% | ___% | ☐ |
| A1 输出格式合规率 | ≥ 90% | ___% | ☐ |
| A2 工具调用成功率 | ≥ 95% | ___% | ☐ |
| A2 重复调用率 | ≤ 5% | ___% | ☐ |
| 端到端响应时间 | ≤ 30 秒 | ___秒 | ☐ |

### Step 22：Prompt 调优（如需要）

如果验收指标未达标，根据问题类型调优：

| 问题类型 | 调优方向 |
|---------|---------|
| A1 分类错误 | 在 Instructions 中增加判定关键词和示例 |
| A1 格式不规范 | 在 Instructions 中强化格式要求，增加示例 |
| A2 工具选择错误 | 在 A2 Instructions 的映射表中明确边界 |
| A2 重复调用 | 在 A2 Instructions 中强化防重规则 |
| Handoff 未触发 | 检查 Handoff 配置是否正确 |

### Step 23：处理常见问题

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| MCP 工具不显示 | mcpServers 配置未生效 | 检查 librechat.yaml 缩进，确保取消注释 |
| Agent Handoffs 不显示 | UI 版本问题 | 确认 LibreChat 版本支持 Orchestration Hub |
| A2 工具调用 401 | 认证 token 错误 | 检查 mcpServers.headers.Authorization |
| A2 工具调用 403 | IP 白名单 | 检查 mcpSettings.allowedAddresses |
| Chain 模式不可用 | 极低概率 | chain 在默认 capabilities 中，如不可用检查 LibreChat 版本是否支持 |
| end_after_tools 无法配置 | 已知限制 | UI 无开关，通过 API 设置：`PATCH /api/agents/{id}` `{"end_after_tools": true}` |
| qwen3.6-35B 重复提问 | recursion_limit 未生效 | 确认 A1 的 recursion_limit 设置为 3 |
| qwen3.6-35B 重复调用工具 | end_after_tools 未生效 | 在 A2 Prompt 中强化防重规则 |
| execute_code 报 `request to https://api.librechat.ai/v1/exec failed` | LibreChat 默认指向官方闭源沙箱，内网不可达 | 部署本地 code-command 沙箱并配置 `LIBRECHAT_CODE_BASEURL`（见阶段六） |

---

## 阶段六：本地代码沙箱部署（code-command）

> 解决内网环境 `execute_code` 无法执行/生成 Excel 的问题。LibreChat 默认调用官方闭源服务 `https://api.librechat.ai/v1`，内网不可达。通过自托管开源的 **code-command**（[ryanfortin/code-command](https://github.com/ryanfortin/code-command)，MIT 协议）替换为本地方案。

### 6.0 认识与认证坑（⚠️ 必读）

- **不是 LibreChat 私有功能**：这是通用的代码解释器 HTTP 服务（`/exec`、`/upload`、`/download`、`/files`、`/sessions`），协议兼容 `@librechat/agents` 的 CodeExecutor。
- **认证坑（与官方 README 不同）**：
  - 当前 LibreChat 代码**不读取** `LIBRECHAT_CODE_API_KEY`。
  - 它只透传 `authHeaders`，来自 `getCodeApiAuthHeaders`：仅启用 `CODEAPI_JWT` 时才发 `Authorization: Bearer <JWT>`，否则为空 `{}`。
  - code-command 只认 `X-API-Key` 头，且 `CODE_API_KEY` 为空时**放行一切**。
  - **结论**：code-command 的 `CODE_API_KEY` 必须**留空**；LibreChat 侧**不要**配置任何 `CODEAPI_JWT_*`。

### 6.1 在服务器上构建并启动 code-command

```bash
cd /opt   # 或任意目录
git clone https://github.com/ryanfortin/code-command.git
cd code-command

# 构建沙箱镜像（预装 pandas/openpyxl/matplotlib 等，体积较大）
docker build -t code-sandbox:latest .

# 配置环境变量
cp .env.example .env
```

编辑 code-command 的 `.env`（注意这是 code-command 自己的，不是 LibreChat 的）：

```env
# 必须留空 = 放行内网请求（LibreChat 新版不发 X-API-Key）
CODE_API_KEY=
CODE_WORK_DIR=/tmp/code_command
CODE_EXEC_TIMEOUT=120
```

启动并健康检查：

```bash
docker-compose up -d
curl http://localhost:8095/health
```

### 6.2 配置 LibreChat 指向本地沙箱

在 LibreChat 的 `.env` 追加（已完成，见[.env](librechat/.env#L1155-L1163)）：

```env
# code-command 跑在宿主机，LibreChat 容器经 host.docker.internal 访问
# （docker-compose.yml 已配置 extra_hosts: host.docker.internal:host-gateway）
LIBRECHAT_CODE_BASEURL=http://host.docker.internal:8095
```

⚠️ 不要配置任何 `CODEAPI_JWT_*` 变量。

### 6.3 重启并验证

```bash
# 服务器上重启 LibreChat
cd /path/to/librechat && docker-compose restart api

# 验证沙箱端口
curl http://localhost:8095/health
```

### 6.4 端到端测试

在对话中让 A2 执行 `execute_code` 生成 xlsx（如"生成excel文件，我要下载这13个项目"）。成功标准：A2 调用 `execute_code` 工具并返回可下载的 xlsx 文件链接，而非复述 CSV 代码块。

---

## 附录 A：完整配置文件示例

### librechat.yaml 关键配置片段

```yaml
# 0. actions.allowedDomains（已配置，含 MCP 服务地址）
actions:
  allowedDomains:
    - 'swapi.dev'
    - 'librechat.ai'
    - 'google.com'
    - 'http://10.0.0.5:8080/mcp'
    - 'http://10.0.0.5:8017/mcp'

# 1. MCP 服务配置（取消注释）
mcpSettings:
  allowedAddresses:
    - '10.0.0.5:8080'
    - '10.0.0.5:8017'

mcpServers:
  inv-mcp:
    type: streamable-http
    url: http://10.0.0.5:8080/mcp
    timeout: 60000
    headers:
      Authorization: "Bearer dev_token_123"

# 2. agents 配置（默认已包含 chain/subagents，通常无需修改）
# 仅当需要覆盖默认配置时取消注释
# agents:
#   recursionLimit: 25
#   maxRecursionLimit: 100
#   capabilities: ["deferred_tools", "execute_code", "file_search", "actions", "tools", "chain", "subagents"]

# 3. Endpoint 配置（已就绪，无需修改）
endpoints:
  custom:
    - name: "Qwen-3.6-Local"
      apiKey: "sk-local-qwen"
      baseURL: "http://10.0.0.5:8005/v1"
      models:
        default: ["qwen3.6-35B"]
        fetch: true
      capabilities:
        - files
        - agents
```

---

## 附录 B：Agent 创建检查清单

### A2 执行器创建检查清单

- [ ] Name 填写为"投资数据执行器"
- [ ] Provider 选择 Qwen-3.6-Local
- [ ] Model 选择 qwen3.6-35B
- [ ] Instructions 粘贴完整 Prompt（设计文档 §5.2，**指导说明版**）
- [ ] Skills 挂载 `investment-dwd-query`（业务逻辑 Skill）
- [ ] Tools 挂载 10 个 MCP 工具
- [ ] Advanced 面板检查 recursion_limit（默认 25）
- [ ] 保存 Agent
- [ ] 复制并记录 A2 的 Agent ID

### A1 领导版创建检查清单

- [ ] Name 填写为"投资意图路由器-领导版"
- [ ] Provider 选择 Qwen-3.6-Local
- [ ] Model 选择 qwen3.6-35B
- [ ] Instructions 粘贴完整 Prompt（设计文档 §5.1）
- [ ] Tools 保持为空（不挂任何工具）
- [ ] Advanced 面板设置 recursion_limit = 3
- [ ] Orchestration Hub 配置 Handoff 到 A2
- [ ] Handoff 的 prompt 字段填写传递指令
- [ ] 保存 Agent
- [ ] 复制并记录 A1 的 Agent ID

---

## 附录 C：UI 导航路径速查

| 操作 | 导航路径 | 对应组件 |
|------|---------|---------|
| 创建 Agent | 侧边栏 → Agents → Create Agent | [AgentConfig.tsx](librechat/client/src/components/SidePanel/Agents/AgentConfig.tsx) |
| 配置 Tools | Agent 编辑页 → Tools 区域 → Add Tool | [ToolsSection.tsx](librechat/client/src/components/SidePanel/Agents/Tools/ToolsSection.tsx) |
| 配置 Instructions | Agent 编辑页 → Instructions 区域 | Instructions.tsx |
| 进入 Advanced | Agent 编辑页 → Advanced 按钮 | [AdvancedPanel.tsx](librechat/client/src/components/SidePanel/Agents/Advanced/AdvancedPanel.tsx) |
| 配置 recursion_limit | Advanced → Essentials → Max Agent Steps | [MaxAgentSteps.tsx](librechat/client/src/components/SidePanel/Agents/Advanced/MaxAgentSteps.tsx) |
| 配置 Handoff | Advanced → Orchestration → Agent Handoffs | [AgentHandoffs.tsx](librechat/client/src/components/SidePanel/Agents/Advanced/AgentHandoffs.tsx) |
| 配置 Chain | Advanced → Orchestration → Agent Chain | [AgentChain.tsx](librechat/client/src/components/SidePanel/Agents/Advanced/AgentChain.tsx) |
| 复制 Agent ID | Advanced → 底部 Agent ID → 复制按钮 | [AdvancedPanel.tsx:66-86](librechat/client/src/components/SidePanel/Agents/Advanced/AdvancedPanel.tsx#L66) |

---

## 附录 D：后续扩展步骤

### 创建 A1-员工版（阶段二）

重复 Step 10-16，差异：

| 字段 | 领导版 | 员工版 |
|------|--------|--------|
| Name | 投资意图路由器-领导版 | 投资意图路由器-员工版 |
| Instructions | §5.1 | 调整：不预设 biz_line、limit=20-200、鼓励明细查询 |
| recursion_limit | 3 | 3 |
| Handoff 目标 | A2 执行器 | A2 执行器（同一个） |

### 创建 A1-审计版（阶段三）

重复 Step 10-16，差异：

| 字段 | 领导版 | 审计版 |
|------|--------|--------|
| Name | 投资意图路由器-领导版 | 投资意图路由器-审计版 |
| Instructions | §5.1 | 调整：强制记录查询目的、限制字段范围 |
| recursion_limit | 3 | 3 |
| Handoff 目标 | A2 执行器 | A2 执行器（同一个） |

---

## 附录 E：使用到的 LibreChat 代码文件索引

| 文件 | 作用 | 关键行号 |
|------|------|---------|
| [librechat.yaml](librechat/librechat.yaml) | 主配置文件 | L273-280（actions.allowedDomains）、L344-358（MCP）、L406-431（agents）、L528-542（Endpoint） |
| [AgentConfig.tsx](librechat/client/src/components/SidePanel/Agents/AgentConfig.tsx) | Agent 创建/编辑主界面 | L61-86（name）、L107-150（model） |
| [ToolsSection.tsx](librechat/client/src/components/SidePanel/Agents/Tools/ToolsSection.tsx) | 工具挂载 UI | L266-375 |
| [AdvancedPanel.tsx](librechat/client/src/components/SidePanel/Agents/Advanced/AdvancedPanel.tsx) | 高级设置面板 | L15-91 |
| [OrchestrationHub.tsx](librechat/client/src/components/SidePanel/Agents/Advanced/OrchestrationHub.tsx) | 编排中心（Chain/Handoff/Subagents） | L21-65 |
| [MaxAgentSteps.tsx](librechat/client/src/components/SidePanel/Agents/Advanced/MaxAgentSteps.tsx) | recursion_limit 配置 | L8-54 |
| [AgentHandoffs.tsx](librechat/client/src/components/SidePanel/Agents/Advanced/AgentHandoffs.tsx) | Handoff 配置 UI | L32-79 |
| [AgentChain.tsx](librechat/client/src/components/SidePanel/Agents/Advanced/AgentChain.tsx) | Chain 配置 UI | L29-123 |

---

## 附录 F：dwd_all_biz 数据结构说明（v1.17）

> 本节说明 `dwd_all_biz` 视图在 v1.17 中的结构变更（新增 `company_name` 字段），并作为数据模型定义、ETL/DWD 视图与查询工具侧的同步口径。

### F.1 数据模型定义（DDL）

`dwd_all_biz` 由 4 个 UNION ALL 分支构成，v1.17 为每个分支新增 `company_name` 字段，通过 LEFT JOIN 关联获取：

| biz_type 分支 | company_name 取值 | 关联表 |
|---------------|------------------|--------|
| FUND2PROJ | 投资方基金的公司 | `LEFT JOIN dwd_fund df1 ON fund_id` |
| SUBFUND2PROJ | 投资方子基金的公司 | `LEFT JOIN dwd_subfund dsf1 ON subfund_id` |
| FUND2SUBFUND | 投资方基金的公司 | `LEFT JOIN dwd_fund df2 ON fund_id` |
| LP2FUND | 被投资方基金的公司（LP 为外部方） | `LEFT JOIN dwd_fund df3 ON fund_id` |

**字段语义**：`company_name` = 该项投资所负责的金控内部公司（即"投资方(investor)实体所属金控公司"）。对 FUND2PROJ/SUBFUND2PROJ/FUND2SUBFUND 取投资方（基金/子基金）的 `company_name`；对 LP2FUND 取被投资方（基金）的 `company_name`（LP 为外部方，无金控公司）。

**完整字段清单**（与 `sql/dwd_views.sql` 一致）：

| 字段 | 类型 | 说明 |
|------|------|------|
| biz_type | VARCHAR | FUND2PROJ / SUBFUND2PROJ / FUND2SUBFUND / LP2FUND |
| investor_id / investor_name | | 投资方（出钱方）编号 / 名称 |
| investee_id / investee_name | | 被投资方编号 / 名称 |
| biz_line | VARCHAR | 业务线（FUND2SUBFUND='FUND'，LP2FUND='LP'，其余为项目中文值或 NULL） |
| **company_name** | VARCHAR | **v1.17 新增**：该投资所负责的金控内部公司 |
| committed_amt / flow_amt | DECIMAL | 承诺出资额 / 实际出资额（万元） |
| flow_time | DATETIME | 出资流水时间 |

### F.2 ETL/DWD 视图配置

`dwd_all_biz` 是 DWD 语义层视图，由 `mcp-inv-server-v2/sql/dwd_views.sql` 定义并部署。v1.17 结构变更随该 SQL 文件下发，需在目标库重新执行创建/替换视图（`SHOW CREATE VIEW dwd_all_biz` 校验字段）。**无独立 ETL 作业**——本系统视图直接基于 `v_cockpit_*` 源视图实时计算，结构变更即 DDL 变更，无需额外调度配置。

### F.3 查询侧白名单与工具适配

为保障安全并支持按 `company_name` 过滤，`base.py` 中 `dwd_all_biz` 的白名单同步更新：

| 白名单 | 新增项 |
|--------|--------|
| `ALLOWED_FIELDS` | `company_name` |
| `GROUP_BY_FIELDS` | `company_name` |
| `PREFIX_MATCH_FIELDS` | `company_name` |
| `NULL_CHECK_FIELDS` | —（未新增） |
| `DEFAULT_FIELDS` | `company_name`（默认返回列） |

工具侧 `query_all_biz` 新增两个参数：`company_name`（精确匹配）与 `company_name_prefix`（前缀匹配，LIKE `'xxx%'`），用于按金控公司圈定跨业务域投资关系。

---

## 附录 G：本体层（Ontology）架构评估与设计方案

> 本节评估是否引入类似 Palantir Ontology 的本体层，若实施则给出设计方案、技术选型、实施步骤与预期效益分析。**结论：建议引入，但采用"轻量分阶段落地"路线**，以本体作为数据解读的"语义单点事实源（Single Source of Semantic Truth）"，与现有 DWD 视图 + Skill/指令的双层机制互补而非替代。

### G.1 需求背景与现状痛点

本次 `company_name` 字段的加入暴露出现有体系的深层问题——**数据语义散落、关系隐含、业务规则依赖文档与 Prompt 而非结构化定义**：

1. **字段语义分散**：`company_name` 在不同视图语义不同——在 `dwd_fund`/`dwd_project` 是"实体所属公司"，在 `dwd_all_biz` 是"该投资负责的金控公司（LP2FUND 取被投基金公司）"。同一字段名在不同上下文含义漂移，需依赖文档逐条解释。
2. **关系隐含于 SQL**：`dwd_all_biz` 的 4 个 UNION 分支（FUND2PROJ/SUBFUND2PROJ/FUND2SUBFUND/LP2FUND）把"投资关系"隐式建模在 SQL JOIN 里，没有显式的"实体类型 + 关系类型 + 语义"声明。
3. **业务规则散落**：biz_line 映射（stock↔股权项目）、company_name 归因规则、跨 biz_line 禁止 SUM 等规则，目前写在 `base.py` 白名单、Skill `SKILL.md`、A1/A2 指令三处，易漂移（v1.15 已做过一次指令/Skill 去重归位，但白名单与文档仍各自维护）。
4. **模型解读依赖 Prompt**：A2 对数据的"正确解读"依赖 Skill 与指令的文本约束，而非机器可读的定义，存在模型理解偏差导致的解读不一致风险。

### G.2 是否引入本体层的评估

**建议引入，但明确边界**：

| 维度 | 评估 |
|------|------|
| 直接收益 | 建立标准化的实体/关系/属性/业务规则定义，让数据解读"有据可依"，减少文档漂移与模型误读 |
| 成本 | 需新增建模工作、元数据存储与维护机制；当前体系（DWD 视图 + Skill + 白名单）已能工作，本体层是"增强"而非"必需" |
| 风险 | 过度设计会导致"为建本体而建本体"，增加复杂度 |
| 结论 | **分阶段引入**：先以"轻量本体定义（YAML/JSON）"作为单一事实源，自动生成/校验白名单与 Skill，再逐步演进为完整元数据服务 |

**为什么必须引入（而非仅靠文档）**：本次 `company_name` 语义（LP2FUND 取被投基金公司）正是"仅靠 SQL 与注释、无显式声明"导致容易误读的典型——若本体层明确定义"投资关系.company_name = 投资方实体所属公司(LP 场景回退被投基金公司)"，则模型与工具都能一致引用这个定义。

### G.3 本体模型设计

按 Palantir Ontology 三要素建模：**对象类型（Object Types）、关系类型（Link Types）、属性与业务规则（Properties & Actions）**。

#### G.3.1 核心对象类型

| 对象类型 | 对应视图/表 | 关键属性 |
|---------|------------|---------|
| `Fund`（基金） | dwd_fund | fund_id, fund_name, company_name, fund_type, total_size |
| `Subfund`（子基金） | dwd_subfund | subfund_id, subfund_name, company_name, phase |
| `Project`（直投项目） | dwd_project | proj_id, proj_name, company_name, biz_line, invest_amount |
| `LP`（出资人） | dwd_lp2fund | lp_id, lp_name, lp_type |
| `Company`（金控公司） | — | company_name（可作为实体引出，提升公司维度可查性） |

#### G.3.2 关系类型

| 关系 | 源 → 目标 | 对应 biz_type | 关键属性 |
|------|-----------|---------------|---------|
| `INVESTS_IN`（投资项目） | Fund/LP/Subfund → Project/Subfund/Fund | FUND2PROJ / SUBFUND2PROJ / FUND2SUBFUND / LP2FUND | committed_amt, flow_amt, flow_time, biz_line, **company_name（归因公司）** |

> 关键：把 `dwd_all_biz` 的 4 个 UNION 分支**显式建模为统一关系类型 `INVESTS_IN`**，其 `biz_type` 作为关系子类型，`company_name` 作为关系属性而非对象属性——从而消灭"同一字段跨视图语义漂移"问题。

#### G.3.3 业务规则（可机器校验）

以声明式规则固化当前散落的约束：

```yaml
rules:
  - id: R-AMT-NO-CROSS-BIZLINE-SUM
    name: 禁止跨业务线加总金额
    scope: INVESTS_IN
    constraint: "不得对 committed_amt 在 biz_line != FUND/LP 时作投资额口径"
    enforce_in: [stat_investment_summary]
  - id: R-COMPANY-ATTRIBUTION
    name: 投资归因公司
    scope: INVESTS_IN
    definition: "company_name = 投资方实体所属公司；LP2FUND 场景回退为被投资方基金公司"
  - id: R-QUERY-ALL-BIZ-NO-DETAIL
    name: dwd_all_biz 禁止明细查询
    scope: query_all_biz
    constraint: "仅宏观统计，禁止查询特定项目/基金列表"
```

### G.4 技术选型

> **评估维度说明**：以下评级基于 5 个维度的加权打分（每维度 1-3 分，3 分最优），汇总后映射为星级：≥12 分 ⭐⭐⭐、9-11 分 ⭐⭐、≤8 分 ⭐。

| 维度 | 权重 | 说明 |
|------|------|------|
| 部署复杂度 | 高 | 是否引入新运行时依赖/中间件；私有化部署难度 |
| 与 MySQL 兼容性 | 高 | 能否直接对接现有 MySQL 8.0.44 + DWD 视图 |
| 社区活跃度 | 中 | 维护频率、文档质量、issue 响应 |
| 学习曲线 | 中 | 团队上手成本、是否需新技能栈 |
| 与现有架构契合度 | 高 | 能否复用 ontology.yaml / 生成器 / 漂移检查链路 |

| 方案 | 部署复杂度 | MySQL 兼容 | 社区活跃 | 学习曲线 | 架构契合 | 总分 | 适用度 | 说明 |
|------|-----------|-----------|---------|---------|---------|------|--------|------|
| **轻量本体定义文件（YAML/JSON）+ 代码生成** | 3（零依赖） | 3（原生） | — | 3（YAML+脚本） | 3（直接复用） | 12+ | ⭐⭐⭐（推荐起步） | 用单一 `ontology.yaml` 定义对象/关系/规则，脚本自动生成 `base.py` 白名单、校验 Skill 一致性，投入小见效快 |
| Apache Atlas / Amundsen / DataHub | 1（需 JVM/独立服务） | 2（需适配） | 3 | 1（元数据治理体系重） | 1（架构异质） | 8 | ⭐⭐ | 成熟数据目录与血缘，但面向企业级元数据管理，对当前单系统偏重 |
| Neo4j 图数据库本体 | 1（新存储） | 1（需同步） | 3 | 2（Cypher） | 1（语义模型异构） | 8 | ⭐⭐ | 适合复杂关系推理，但引入新存储，初期收益有限 |
| AWS Glue DataBrew / 云原生数据目录 | 1（云绑定） | 1（不匹配） | 2 | 2 | 1 | 7 | ⭐ | 与本地 MySQL/私有部署不匹配 |

> **推荐**：第一阶段用 **YAML 本体定义 + 生成器脚本**（`ontology.yaml` → 生成白名单/校验 SKILL），零新增运行时依赖；待体系成熟后再评估接入 DataHub 或图数据库做可视化治理。

### G.5 实施步骤

1. **数据资产盘点**：梳理现有 9 个 DWD 视图、`v_cockpit_*` 源表、11 个 MCP 工具的字段与语义。
2. **本体建模**：按 G.3 定义对象类型、关系类型、属性与业务规则，产出 `ontology.yaml`。
3. **字段语义归一**：为 `company_name` 等跨视图语义漂移字段建立"对象级/关系级"归属声明。
4. **生成器与校验**：编写脚本从 `ontology.yaml` 生成 `base.py` 白名单，并校验 `SKILL.md`、A1/A2 指令与本体定义的一致性（检查漂移）。
5. **查询/工具适配**：`query_all_biz` 等工具按本体定义的关系属性（含 `company_name`）暴露参数（本 v1.17 已先行落地）。
6. **集成与治理流程**：将"本体变更"纳入版本管理，任何字段/规则变更先改本体再改代码/文档，形成"单一事实源"。

### G.6 预期效益分析

| 效益 | 说明 | 度量 |
|------|------|------|
| **数据解读一致性** | 模型与工具引用同一份本体定义，消除同一字段跨视图语义漂移（如 company_name） | 跨视图字段语义冲突数 → 0 |
| **可维护性** | 白名单、Skill、指令由本体生成/校验，减少三处维护导致的漂移 | 文档-代码漂移告警数下降 |
| **准确性** | 关系类型显式化（INVESTS_IN），减少"拼接臆测/错误归因"类解读错误 | E2E 链式用例通过率提升 |
| **可扩展性** | 新增业务域/关系只需改本体定义，无需逐个改 Prompt | 新增查询的上线时间缩短 |
| **治理合规** | 业务规则可审计、可追溯，符合金控数据治理要求 | 规则覆盖率 → 100% |

### G.7 风险与建议

- **避免过度设计**：不引入重量级平台，以 YAML + 生成器起步，价值验证后再演进。
- **与现有机制协同**：本体层**不替代** A1/A2 行为层与 Skill 技术层，而是作为二者的"语义底座"，由生成器把本体导出为 Skill 中可读的字段/规则说明。
- **一步先行落地**：本 v1.17 的 `company_name` 字段 + 工具参数扩展，已为"投资关系归因公司"这一本体要点打了前站；后续可先把 `ontology.yaml` 中 `R-COMPANY-ATTRIBUTION` 规则落地为校验脚本，即可验证本体层价值。
