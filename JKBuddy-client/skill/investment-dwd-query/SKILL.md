---
name: investment-dwd-query
description: 投资数据 DWD 语义查询执行 Skill。基于 dwd_all_biz 主视图及 9 个 DWD 视图，提供实体识别、业务类型(biz_type)区分、业务线(biz_line)分类、投资/被投资方字段与金额字段处理规则。当 A2 执行器需要把用户意图翻译为具体的 MCP 工具调用参数，或需要判断"集团/金控/子公司"指代、选择数据来源、映射 biz_type/biz_line/金额字段时使用本技能。
allowed-tools:
  - query_all_biz
  - stat_investment_summary
  - stat_group_by_tool
  - query_fund
  - query_subfund
  - query_project
  - query_subfund_proj
  - query_lp2fund
  - query_fund2subfund
  - query_fund2proj
  - query_subfund2proj
  - get_ontology
always-apply: true
user-invocable: true
disable-model-invocation: false
---
> 语义单一事实源：`mcp-inv-server-v2/ontology/ontology.yaml`。
> 字段/关系/规则的权威定义见本体生成的人读投影 `ontology/generated/skill-semantics.md`，
> 本文件仅保留"如何把本体语义翻译成 MCP 调用"的操作适配。
# 投资数据 DWD 语义查询执行 Skill

> **定位**：本技能是**技术实现层**，只负责"怎么查"——把用户问题翻译为符合业务语义的 MCP 工具调用参数（实体识别、数据来源选择、工具路由、参数值映射）。它**不负责"怎么答"**（角色感知、输出格式、分页展示、数据诚实与防过滤/去重、防拼接等行为规范）——后者由 A2 执行器的 Instruct 指导说明负责。
>
> **使用时机**：当 A2 收到用户查询，需要确定"查哪个实体、哪个视图、哪个业务类型、哪个业务线、传哪些字段"时，严格按本技能规则执行。
>
> **职责边界**：本技能只提供技术决策；一切数据返回后的**输出、诚实、防过滤/去重、防拼接、分页展示**规则见 A2 Instruct 的"数据真实性/数据忠实性/链式核实/分页"章节。本技能不重复这些行为规范。

---

## 一、实体定义规范

### 1.1 集团指代（统一语义）

以下名词**均指代整个金控集团**，在查询时表示"全集团范围、不限定子公司"：

| 用户说法 | 语义 |
|---------|------|
| 金控集团 | 整个金控集团 |
| 金控 | 整个金控集团 |
| 金控集团 | 整个金控集团 |
| 集团 | 整个金控集团 |

> 规则：当出现上述任一说法且未指定具体子公司时，查询范围 = **全集团**，不传 `company_name`/`dept_id` 过滤。

### 1.2 投资领域默认子公司（默认范围）

当用户问"投资领域/集团投资板块"且未逐一命名时，**默认包含以下投资类子公司**：

| 子公司 | 说明 |
|--------|------|
| 某投资平台 | 母基金/资本运作 |
| 某科技风投 | 科技风险投资 |
| 创业投资 | 创业投资 |
| 某投资管理公司 | 投资管理 |
| 某控股公司 | 控股投资 |
| 某农投发展公司 | 农业投资发展 |

> 规则：
> - 用户明确说"XX公司"时，按该具体公司过滤（传 `company_name`）。
> - 用户说"投资领域/集团各投资公司"但未点名时，上述 6 家为默认集合。
> - `company_name` 用于 dwd_fund/dwd_subfund/dwd_project/dwd_subfund_proj 等视图；**`dwd_all_biz` 也已新增 `company_name` 字段**，可直接过滤。

### 1.3 主体角色判定（⚠️ 决定抽取哪个主体参数）

> 与 A1 分类器同源维护。根据用户对主体的表述，判定主体参数落在哪个字段：

| 用户表述模式 | 抽取参数 | 示例 |
|------------|---------|------|
| "XX**管理**的 / XX**名下** / XX**负责**的" | `company_name=XX` | "某控股公司管理的业务"→ company_name=某控股公司 |
| "XX**投资**（了）/ XX**投**（了）" | `investor_name=XX` | "某控股公司投了哪些项目"→ investor_name=某控股公司 |
| "投资了**XX** / 被投方**XX**" | `investee_name=XX` | |
| "XX**基金**投的子基金" | `investor_name=XX基金` | |
| "XX**基金**被投资了" | `investee_name=XX基金` | |

> `company_name` 语义 = 该投资所负责的金控公司（管理/名下类主体）。用 `query_all_biz(company_name=XX)` 过滤"某金控公司名下/负责的投资"。

---

## 二、数据查询逻辑

### 2.1 数据来源（默认主视图 + 两级查询策略）

**核心策略：一般查询一律先查 `dwd_all_biz` 全量视图（`query_all_biz`）；查不到再分头查专表。**

**字段覆盖判断（先看字段再查）**：`dwd_all_biz` 含 `investor_*` / `investee_*` / `company_name` / `biz_type` / `biz_line` / `flow_amt` / `committed_amt` / `flow_time`。若查询涉及 **退出金额(exit_amount)、基金阶段(fund_phase)、基金规模等 `dwd_all_biz` 不含的字段**，则**直接走第二级专表工具**，跳过第一级。

**明细类查询规则（⚠️ 与 query_all_biz 定位对齐）**：`query_all_biz` 的定位是**全集团跨域宏观统计**，docstring 明确**禁止用于查询特定项目/基金列表**。因此凡属"查明细/列表/详情"类查询（如查某项目明细、某基金详情、某 LP 出资明细），**直接走第二级专表工具**，不先查 `dwd_all_biz`。仅"投资关系/投资金额/跨域统计/分组汇总"类查询走第一级 `dwd_all_biz`。

**第一级（优先）**：默认以 `dwd_all_biz` 视图作为主要数据查询来源（对应工具 `query_all_biz`）。
适用场景：
- 跨业务域宏观统计、投资金额汇总、趋势分析
- 同时看到"投资方→被投资方"的通用关系
- 业务类型(biz_type)维度统计
- **一般查询的默认起点**（投资/被投方、投资金额、投资时间等 dwd_all_biz 覆盖字段）

**第二级（兜底）**：仅当 `query_all_biz` **真实返回空**（`data:[]` / `total:0`）时，才按业务域改查**专表视图**（更精确）：
- `dwd_fund` → `query_fund`（基金）
- `dwd_subfund` → `query_subfund`（子基金）
- `dwd_project` → `query_project`（直投项目，biz_line 必填）
- `dwd_subfund_proj` → `query_subfund_proj`（子基金底层项目）
- `dwd_lp2fund` → `query_lp2fund`（LP 出资基金）
- `dwd_fund2subfund` → `query_fund2subfund`（母基金投子基金）
- `dwd_fund2proj` → `query_fund2proj`（基金投项目）
- `dwd_subfund2proj` → `query_subfund2proj`（子基金投项目）

> 两级查询均返回空时，如实报告"无数据"，禁止编造结论。
> 注意：`query_all_biz` 与专表工具**不得重复查询同一语义**（先全量、空才专表），避免重复调用。

### 2.2 业务类型（biz_type）定义

`biz_type` 是 `dwd_all_biz` 的唯一定义维度，**4 种类型互斥**：

| biz_type | 含义 | 关系语义 |
|----------|------|---------|
| FUND2PROJ | 基金投资的项目 | 基金 → 直投项目 |
| SUBFUND2PROJ | 基金投资的子基金所投资的项目 | 子基金 → 底层项目 |
| FUND2SUBFUND | 基金投资的子基金 | 母基金 → 子基金 |
| LP2FUND | 出资人 LP 投资的基金 | LP → 基金 |

> 规则：用户问"基金投了哪些项目"→ `biz_type=FUND2PROJ`；"子基金投了哪些项目"→ `biz_type=SUBFUND2PROJ`；"母基金投了哪些子基金"→ `biz_type=FUND2SUBFUND`；"LP 出资了哪些基金"→ `biz_type=LP2FUND`。

### 2.3 关键字段含义

`dwd_all_biz` 通用投资/被投资双方字段：

| 字段 | 类型 | 含义 |
|------|------|------|
| investor_id | 编号 | 投资人系统唯一编号（可包含基金、子基金和 LP） |
| investor_name | 名称 | 投资人名称 |
| investee_id | 编号 | 被投资人系统唯一编号 |
| investee_name | 名称 | 被投资人名称（可以是项目、基金、子基金） |
| company_name | 名称 | 该投资所负责的金控内部公司（即"投资方实体所属金控公司"） |

> 规则：`investor_*` 永远是"出钱方"，`investee_*` 永远是"被投方"。具体到某个 biz_type 时，投资方/被投资方可能是基金、子基金、LP 或项目，需按 2.2 的语义判断。
> ⚠️ **`company_name` 语义（重要）**：在 `dwd_all_biz` 中表示"该投资所负责的金控内部公司是哪家"。对 FUND2PROJ/SUBFUND2PROJ/FUND2SUBFUND 取**投资方（基金/子基金）** 的 `company_name`；对 LP2FUND 取**被投资方（基金）** 的 `company_name`（LP 为外部方，无金控公司）。查询"某金控公司名下投资/负责的投资"时用 `company_name` 过滤（`query_all_biz` 支持 `company_name` 精确与 `company_name_prefix` 前缀匹配）。

### 2.4 业务线（biz_line）分类处理

`biz_line` 表示"业务线/业务类型归属"，在 `dwd_all_biz` 中用于区分业务大类。**按以下分类处理**：

| biz_line 代码 | 业务含义 |
|--------------|---------|
| stock | 股权项目 |
| rzzl | 融资租赁 |
| debt | 委托贷款 |
| bl | 商业保理 |
| elo | 应急转贷 |
| FUND | 基金（FUND2SUBFUND 类型） |
| LP | 投资人（LP2FUND 类型） |
| subfund_proj | 子基金投资的项目 |

> ⚠️ **工具参数映射（必须遵守，避免传错值）**：
> 不同视图对 `biz_line` 的取值格式不同，调用工具前按目标视图转换：
>
> | 目标视图/工具 | biz_line 取值格式 | 示例 |
> |--------------|------------------|------|
> | `query_project`（dwd_project） | 中文业务名 | `股权项目`/`委托贷款`/`融资租赁`/`商业保理`/`应急转贷`/`助保贷` |
> | `query_fund2proj`（dwd_fund2proj） | 英文代码 | `stock`/`debt`/`rzzl`/`bl`/`elo`/`egl` |
> | `query_all_biz`（dwd_all_biz） | 按 biz_type 取值 | `FUND2SUBFUND`→`FUND`；`LP2FUND`→`LP`；`FUND2PROJ`→项目中文值；`SUBFUND2PROJ`→不传(空) |
>
> 映射关系：`stock`↔`股权项目`、`rzzl`↔`融资租赁`、`debt`↔`委托贷款`、`bl`↔`商业保理`、`elo`↔`应急转贷`。

### 2.5 金额字段处理规则

| 字段 | 含义 | 有效范围 |
|------|------|---------|
| committed_amt | 基金的认缴规模（承诺出资额） | **仅在 biz_line 为 FUND 和 LP 时有效** |
| flow_amt | 实际投资额 | 通用 |
| flow_time | 实际投资时间 | 通用（日期筛选/趋势用） |

> 规则：
> - `committed_amt` 只在 `FUND`（FUND2SUBFUND）和 `LP`（LP2FUND）业务线下有业务意义；对项目类（stock/rzzl/debt/bl/elo）不要用 `committed_amt` 作"投资额"口径。
> - 用户问"实际投了多少/投资金额"→ 用 `flow_amt`。
> - 用户问"认缴/承诺规模"→ 用 `committed_amt`（仅基金/LP 场景）。
> - 金额单位统一为**万元**。
> - 不同 `biz_line` 的金额语义不同，**禁止跨 biz_line 直接 SUM**（用 `stat_investment_summary` 按 biz_line 分组统计）。

---

## 三、工具路由与参数映射（决策规则）

**路由原则：两级查询。第一级统一走 `query_all_biz`（dwd_all_biz）；仅当其返回空时，第二级才按业务域查专表工具。** 严格按 2.x 的映射填充参数：

**第一级（所有查询的默认起点）**：

| 查询范围 | 第一级工具 | 关键参数 |
|---------|-----------|---------|
| 任何业务查询（基金/项目/关系/汇总） | `query_all_biz` | biz_type / biz_line / investor_name / investee_name / **company_name** / limit |

**第二级（仅当第一级返回空 data:[] / total:0 时）**：

| 用户意图 | 兜底工具 | 关键参数 |
|---------|---------|---------|
| 全集团跨域宏观统计/汇总 | `stat_investment_summary` | biz_type / biz_line |
| 分组统计/趋势 | `stat_group_by_tool` | view + group_by / group_by_expr |
| 基金明细 | `query_fund` | fund_name / fund_type / fund_phase |
| 子基金明细 | `query_subfund` | subfund_name / phase |
| 直投项目明细 | `query_project` | **biz_line(必填)** / proj_name / phase |
| 子基金底层项目 | `query_subfund_proj` | subfund_name / phase |
| LP-基金关系 | `query_lp2fund` | lp_name / fund_name |
| 基金-子基金关系 | `query_fund2subfund` | fund_name / subfund_name |
| 基金-项目关系 | `query_fund2proj` | fund_name / proj_name / biz_line |
| 子基金-项目关系 | `query_subfund2proj` | subfund_name / subfund_proj_name |

### 参数构造约束（防参数错误）

1. **只传工具 schema 中已声明的参数**，不存在的参数一律不传（如 `query_lp2fund` 无 `biz_line`/`biz_type`/`action`）。
2. 按 2.4 的映射表把概念 `biz_line` 转换为目标视图的实际取值。
3. `query_project` 的 `biz_line` 为**必填**中文值，防止跨业务域误聚合。
4. 参数名与 schema 完全一致（大小写、下划线），不得别名替换。
5. 排序/分页：`limit` **一律传 200（工具上限）**或按用户需求条数，避免默认值截断；`order_by`/`order_direction` **仅当工具支持且用户明确要求时传**，且 `order_by` 必须用目标工具 schema 的**合法字段名**（如子基金视图用 `subfund_name`，不得用 `name`；基金视图用 `fund_name`）。用户未明确要求排序时，**不传 `order_by`**，由服务端自动按稳定字段排序保证分页不重复。
6. `query_all_biz` 与专表工具**不得重复查询同一语义**：先全量、空才专表。
7. **"列出所有/全部/完整列表"类请求 → `limit: 200`（工具上限，一次取全，避免翻页导致后续页编造）**。⚠️ 只有当用户明确要求分批/翻页浏览时才用较小 limit。
8. **按公司过滤 `dwd_all_biz`**：`query_all_biz` 支持 `company_name`（精确）与 `company_name_prefix`（前缀，如"某控股"匹配"某控股公司"）。查询"某金控公司名下/负责的投资"时用这两个参数。

---

## 四、执行流程

1. **实体识别**：按 §一 判断集团/子公司范围，确定是否过滤 `company_name`（`dwd_all_biz` 的 `company_name` 语义见 §2.3）。
2. **第一级查询（优先）**：调用 `query_all_biz`（dwd_all_biz），按 §2.2/§2.4 确定 `biz_type`/`biz_line` 并映射参数。
3. **判断结果**：若 `query_all_biz` 返回非空 → 交由 A2 按 Instruct 输出规范总结。
4. **第二级查询（兜底）**：若第一级**真实返回空** → 按目标业务域选专表工具（§三 第二级表）分头查询。
5. **字段选择**：按 §2.3/§2.5 确定投资/被投方与金额字段口径。
6. **构造并调用工具**：按 §三 路由，只传合法参数。
7. **结果处理**：两级均空则如实报告"无数据"；工具报错时如实报告，禁止编造。

---

## 边界与禁止（技术底线）

- **禁止编造数据**：工具返回空或报错时如实说明，不臆测"ETL 未完成/数据未上线"；输出每一行必须来自工具实际返回的 `data`。
- **禁止用 `query_all_biz` 查询特定项目/基金明细**（见 §2.1 明细类规则）。
- **禁止把概念 `biz_line` 原样透传给所有工具**（必须按 §2.4 转换）。
- **禁止跨 biz_line 直接 SUM 金额**（用 `stat_investment_summary` 按 biz_line 分组统计）。
- **数据忠实底线**：工具返回的名称含"测试""备份"等字样、或同一"投资方→被投资方"的多条记录，均属数据库真实数据，须原样保留、不得自行过滤或去重；详尽的输出诚实与防过滤/去重规范见 A2 Instruct"数据真实性/数据忠实性"章节。