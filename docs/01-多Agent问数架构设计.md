# 投资系统 AI 问数多 Agent 架构设计

> **文档版本**：v1.0
> **作者**：GLM-5.2（通过 brainstorming + deepsearch 深度讨论生成）
> **生成日期**：2026-07-31
> **方法论**：Socratic 辩证 + 三轮 12 问深度访谈
> **目标平台**：LibreChat + mcp-inv-server-v2
> **架构方案**：方案 A - 分层共享架构

---

## 执行摘要

本文档基于 brainstorming skill 引导的深度讨论，通过三轮 12 个问题与用户共同确认了投资系统 AI 问数的多 Agent 架构设计。最终采用**方案 A：分层共享架构**——3 个角色化 A1（分类器）共享 1 个 A2（执行器），通过 LibreChat 原生 Agent Chain 串联。

**核心设计决策**：

| 维度 | 决策 | 化解的矛盾 |
|------|------|-----------|
| 用户画像 | 金控集团领导 / 业务部门员工 / 外部监管审计（3 类） | 角色差异化需求 |
| Agent 组织 | 3 个 A1 共享 1 个 A2 | 配置维护成本 vs 隔离性 |
| 澄清策略 | 多轮对话澄清 + recursion_limit=3 硬性限制 | Gemma4 重复提问缺陷 |
| 工具权限 | A2 全挂 10 个工具 | 误用风险 vs 配置复杂度 |
| 上线节奏 | 逐套上线（先领导版 → 员工版 → 审计版） | MVP 风险控制 |
| MVP 能力 | 仅基础查询 + 表格输出 | 范围控制 |

---

## 一、需求背景

### 1.1 业务背景

投资集团需要为不同角色用户提供自然语言查询投资数据的能力，覆盖：

- **基金管理**：基金基本信息、规模、阶段、LP 出资等
- **子基金管理**：子基金投资、退出、底层资产等
- **直投项目**：股权项目、委托贷款、融资租赁、商业保理、应急转贷、助保贷
- **投资关系**：LP-基金、基金-子基金、基金-项目、子基金-项目
- **聚合统计**：分组统计、TOP N、汇总分析

### 1.2 技术现状

| 维度 | 现状 | 来源 |
|------|------|------|
| MCP 服务 | mcp-inv-server-v2，10 个查询工具覆盖 9 个 DWD 视图 | [mcp-inv-server-v2](file:///my-project/mcp-inv-server-v2) |
| LibreChat Endpoint | Gemma-4-Local（gemma-4-26B-A4B-it） | [librechat.yaml:528](file:///LibreChat/librechat.yaml#L528) |
| MCP 服务地址 | `http://<server-host>:8080/mcp` | [librechat.yaml:347](file:///LibreChat/librechat.yaml#L347) |
| Agent 编排能力 | 原生支持 Chain / Handoff / Subagents | [AgentChain.tsx](file:///LibreChat/client/src/components/SidePanel/Agents/Advanced/AgentChain.tsx) |
| Gemma4 已知缺陷 | 重复调用工具、重复提问 | project_memory.md "Lessons Learned" |
| 数据库 | your_db_name @ <db-host> | 已部署验证 |

### 1.3 设计目标

1. **平台原生**：使用 LibreChat 原生能力，零后端开发
2. **模型适配**：规避 Gemma4 已知缺陷
3. **角色差异化**：3 类用户获得针对性体验
4. **渐进落地**：MVP 先上领导版，逐套扩展
5. **可监控**：关键指标可度量，为优化提供数据

---

## 二、深度讨论过程

### 2.1 方法论

采用 Socratic 辩证法 + brainstorming skill，通过三轮 12 个问题引导用户逐步明确需求：

| 轮次 | 主题 | 问题数 | 关键决策 |
|------|------|--------|---------|
| 第一轮 | 业务范围与画像 | 4 | 用户画像、澄清策略、工具权限、高级能力 |
| 第二轮 | 矛盾化解 | 4 | Gemma4 缺陷处理、角色组织、跨域实现、导出能力 |
| 第三轮 | 实施细节 | 4 | Agent 组织、MVP 范围、审计日志、上线节奏 |

### 2.2 核心矛盾与化解

通过深度讨论识别并化解了 4 个核心矛盾：

| 矛盾 | 用户选择 | 化解方案 |
|------|---------|---------|
| 多轮澄清 vs Gemma4 重复提问缺陷 | 多轮澄清 | recursion_limit=3 硬性限制 |
| 3 类用户差异 vs 单一 Agent 能力 | 按角色创建多套 | 3 个 A1 + 1 个共享 A2 |
| 跨域关联 vs 多工具组合风险 | 依赖现有聚合视图 | dwd_all_biz + stat_investment_summary |
| 数据导出 vs MCP 能力边界 | MVP 不做 | 二期评估 |

---

## 三、架构总览（方案 A：分层共享架构）

### 3.1 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    用户（3 类角色）                          │
│   金控集团领导 │ 业务部门员工 │ 外部监管/审计                 │
└──────────┬─────────────────┬──────────────────┬─────────────┘
           │                 │                  │
           ▼                 ▼                  ▼
   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
   │  A1-领导版   │  │  A1-员工版   │  │  A1-审计版   │
   │  意图分类    │  │  意图分类    │  │  意图分类    │
   │  recursion_  │  │  recursion_  │  │  recursion_  │
   │  limit=3     │  │  limit=3     │  │  limit=3     │
   │  tools=[]    │  │  tools=[]    │  │  tools=[]    │
   └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
          │                 │                 │
          └────────┬────────┴────────┬─────────┘
                   │                 │
                   ▼                 ▼
            ┌────────────────────────────┐
            │     共享 A2 执行器         │
            │  ┌──────────────────────┐  │
            │  │ 10 个 MCP 工具全挂载 │  │
            │  │ end_after_tools=true │  │
            │  │ 角色感知输出格式     │  │
            │  └──────────────────────┘  │
            └────────────┬───────────────┘
                         │
                         ▼
            ┌────────────────────────────┐
            │   mcp-inv-server-v2        │
            │   http://<server-host>:8080    │
            │   9 个 DWD 视图            │
            └────────────────────────────┘
```

### 3.2 核心设计原则

| 原则 | 说明 | 化解的风险 |
|------|------|-----------|
| A1 不挂工具 | `tools=[]` | 从源头规避 Gemma4 重复调用工具 |
| recursion_limit=3 | 硬性限制澄清轮数 | 化解 Gemma4 重复提问 |
| end_after_tools=true | A2 工具调用后立即结束 | 双保险防重 |
| 共享 A2 | 3 套 A1 共用 1 个 A2 | 降低维护成本 |
| 角色感知 | A2 通过 Chain 上下文识别角色 | 差异化输出 |

### 3.3 方案选型对比

| 方案 | 配置量 | 维护成本 | 角色隔离 | 推荐度 |
|------|--------|---------|---------|--------|
| **方案 A：分层共享** | 4 个 Agent | 低 | 中 | ⭐⭐⭐⭐⭐ |
| 方案 B：统一智能 | 2 个 Agent | 极低 | 低 | ⭐⭐⭐ |
| 方案 C：完全独立 | 6 个 Agent | 高 | 高 | ⭐⭐ |

**选型理由**：方案 A 契合用户"共享 A2 + 逐套上线"决策，维护友好且演进灵活。

---

## 四、Agent 配置详情

### 4.1 A1-领导版（阶段一上线）

| 字段 | 配置值 | 说明 |
|------|--------|------|
| name | `投资意图路由器-领导版` | |
| model | `gemma-4-26B-A4B-it` | |
| endpoint | `Gemma-4-Local` | [librechat.yaml:528](file:///LibreChat/librechat.yaml#L528) |
| tools | `[]` | **关键防重设计：不挂任何工具** |
| recursion_limit | `3` | 硬性限制澄清轮数 |
| instructions | 见 §5.1 | 针对领导场景优化 |

### 4.2 A1-员工版（阶段二上线）

与领导版结构相同，instructions 差异：

- 不预设 biz_line 默认值（员工应明确指定）
- 允许更高 limit（最高 200）
- 鼓励明细查询而非聚合
- 提问时使用业务术语而非通俗表达

### 4.3 A1-审计版（阶段三上线）

- 强制记录查询目的
- 限制可查询字段范围（通过 Prompt 约束）
- 输出中明确标注数据来源视图
- 查询时间戳记录

### 4.4 共享 A2 执行器

| 字段 | 配置值 | 说明 |
|------|--------|------|
| name | `投资数据执行器` | |
| model | `gemma-4-26B-A4B-it` | |
| endpoint | `Gemma-4-Local` | |
| tools | 10 个 MCP 工具全挂载 | query_fund, query_subfund, query_project, query_subfund_proj, query_lp2fund, query_fund2subfund, query_fund2proj, query_subfund2proj, stat_group_by_tool, stat_investment_summary |
| end_after_tools | `true` | **工具调用后立即结束，防止重复调用** |
| instructions | 见 §5.2 | 角色感知 + 防重规则 |

### 4.5 Agent Chain 配置

每套 A1 通过 `edges` 字段配置到 A2 的 Chain：

```json
{
  "agent_id": "<A1-领导版 ID>",
  "edges": [
    {
      "from": "<A1-领导版 ID>",
      "to": "<A2 执行器 ID>",
      "edgeType": "direct",
      "description": "领导版分类完成后传递给执行器",
      "prompt": "基于以上意图分类结果，请调用对应的 MCP 工具执行查询。意图分类和参数已在上文给出，请严格遵循。",
      "excludeResults": false
    }
  ]
}
```

员工版、审计版各自配置一条 edge 指向同一 A2，仅 `description` 字段不同。

---

## 五、关键 Prompt 设计

### 5.1 A1-领导版 Instructions

```
你是投资数据查询意图分类器（领导版）。你的用户是金控集团高层决策者。

## 角色认知
- 用户关心 TOP N、聚合统计、趋势分析
- 用户问题常模糊（如"最近亏损的项目"）
- 用户不关心 SQL 细节

## 分类规则
将问题分类为以下 5 类之一：

1. **Fund_Query（基金查询）**：涉及基金基本信息、规模、阶段、投资人数量等
2. **Subfund_Query（子基金查询）**：涉及子基金基本信息、投资金额、退出金额等
3. **Project_Query（项目查询）**：涉及直投项目、股权项目、委托贷款、融资租赁、商业保理、应急转贷、助保贷等
4. **Relation_Query（关系查询）**：涉及 LP-基金、基金-子基金、基金-项目、子基金-项目等投资关系
5. **Aggregation_Query（聚合统计）**：涉及分组统计、汇总分析、TOP N 等

## 默认值优先原则（领导版特化）
- 缺失 biz_line → 默认"股权项目"
- 缺失 limit → 默认 10（领导关心 TOP）
- 缺失排序 → 默认 exit_amount DESC
- 缺失时间范围 → 默认近 90 天

## 澄清规则（⚠️ 严格限制）
1. 仅当存在严重歧义时才提问（如"关系"无法判断类型）
2. 同一会话内同一参数最多提问 1 次
3. 总澄清轮数 ≤ 3 轮（recursion_limit=3，超过将强制执行）
4. 提问时给出 2-3 个候选选项供用户选择

## 输出格式（严格遵守）
```
[意图分类] <名称>
[置信度]   <0-1>
[关键参数]
- biz_line: <值>
- order_by: <值>
- order_direction: <ASC/DESC>
- limit: <数值>
- 其他参数: <值>
[需要澄清] <是/否>
[假设说明] <列出已使用的默认值>
[用户角色] 领导
```

## 约束
1. 只输出上述结构化文本，不调用任何工具
2. 禁止重复提问
3. 禁止输出 JSON 之外的格式
```

### 5.2 A2 执行器 Instructions

```
你是投资数据查询执行器。你接收来自上游 A1 分类器的意图分析结果，调用 MCP 工具执行查询，并总结结果。

## 角色感知
根据 Chain 传递的 A1 上下文中的"[用户角色]"字段，调整输出格式：
- **领导**：精简表格（≤5 列）+ 3 行关键洞察
- **员工**：完整表格 + 全部明细字段 + 数据来源
- **审计**：表格 + 数据来源视图 + 查询时间戳 + 字段范围说明

## 工具选择映射表

| 意图分类 | 工具 | 关键参数 |
|---------|------|---------|
| Fund_Query | query_fund | fund_id, fund_name, fund_type, fund_phase |
| Subfund_Query | query_subfund | subfund_id, subfund_name, phase |
| Project_Query | query_project | biz_line（必填）, proj_name, phase |
| Relation_Query-LP2FUND | query_lp2fund | lp_name, fund_name |
| Relation_Query-FUND2SUBFUND | query_fund2subfund | fund_name, subfund_name |
| Relation_Query-FUND2PROJ | query_fund2proj | fund_name, proj_name |
| Relation_Query-SUBFUND2PROJ | query_subfund2proj | subfund_name, subfund_proj_name |
| Aggregation_Query | stat_group_by_tool 或 stat_investment_summary | group_by, agg_field |

## 工具调用约束（⚠️ 防重核心）
1. **同一工具同一参数组合最多调用 1 次**
2. 工具返回空数据时告知用户并建议调整，禁止重试
3. 参数缺失直接报错，禁止"猜测补全"
4. 工具调用成功后立即总结输出，禁止再次调用

## 输出格式
- Markdown 表格（列名中文）
- 附数据条数
- 附数据来源视图名
- 领导版附 3 行关键洞察
- 员工版附完整明细
- 审计版附查询时间戳和字段范围
```

---

## 六、数据流示例

### 6.1 场景一：领导简单查询

**用户输入**："最近哪个股权项目退出金额最大？"

**A1-领导版输出**：
```
[意图分类] Project_Query
[置信度]   0.95
[关键参数]
- biz_line: 股权项目
- order_by: exit_amount
- order_direction: DESC
- limit: 1
[需要澄清] 否
[假设说明] 默认 limit=1（用户问"哪个"），默认 biz_line=股权项目
[用户角色] 领导
```

**A2 执行**：
- 识别意图为 Project_Query → 选 query_project
- 识别用户角色=领导 → 启用精简输出模式
- 调用 `query_project(biz_line="股权项目", order_by="exit_amount", order_direction="DESC", limit=1)`

**A2 输出**：
```
| 排名 | 项目名称   | 退出金额(万元) |
|------|-----------|---------------|
| 1    | 有色金属   | 5,405.36      |

数据条数：1
数据来源：dwd_project
关键洞察：
1. 该项目退出金额远超第二名（5405 vs 993）
2. 投资金额 3800 万元，回报率约 42%
3. 业务线为股权项目，退出周期约 2 年
```

### 6.2 场景二：员工需要澄清

**用户输入**："查一下子基金投资情况"

**A1-员工版第一轮**：
```
[意图分类] Subfund_Query
[置信度]   0.6
[关键参数]
- (待确认)
[需要澄清] 是
[澄清问题] 请选择查询范围：
  A. 全部子基金
  B. 指定金控公司的子基金
  C. 指定阶段的子基金（如"投资中"）
[假设说明] 无
[用户角色] 员工
```

**用户回答**："B，某金控集团的"

**A1-员工版第二轮**（recursion 内）：
```
[意图分类] Subfund_Query
[置信度]   0.9
[关键参数]
- company_name: 金控集团
- limit: 20
[需要澄清] 否
[假设说明] 默认 limit=20
[用户角色] 员工
```

**A2 执行 → 输出完整表格**

### 6.3 场景三：审计场景

**用户输入**："查询所有退出金额超过 1000 万的股权项目"

**A1-审计版输出**：
```
[意图分类] Project_Query
[置信度]   0.92
[关键参数]
- biz_line: 股权项目
- min_exit_amount: 1000
- limit: 200
[需要澄清] 否
[假设说明] 默认 limit=200（审计需要完整数据）
[用户角色] 审计
[查询目的] 高额退出项目审计
```

**A2 输出**：
- 表格 + 数据来源 dwd_project
- 查询时间戳：2026-07-31 19:30:00
- 字段范围说明：仅查询 biz_line, exit_amount, proj_name 字段

---

## 七、错误处理策略

| 错误场景 | 处理方式 | 用户感知 |
|---------|---------|---------|
| A1 输出格式不规范 | A2 Prompt 容错：识别 `[意图分类]` 标签失败时回退为通用查询 | "无法识别查询意图，已执行通用查询" |
| A2 工具调用失败（401/403） | A2 输出错误提示 + 建议联系管理员，不重试 | "认证失败，请联系管理员" |
| A2 工具返回空数据 | A2 输出"未找到匹配数据"+ 建议调整参数 | "未找到匹配数据，建议调整条件" |
| Gemma4 重复调用工具 | `end_after_tools=true` + Prompt 双保险 | 用户无感知（后台拦截） |
| Gemma4 重复提问 | `recursion_limit=3` 硬性限制 | 最多 3 轮澄清后强制执行 |
| Chain 传递中断 | LibreChat 自动报错 | "Agent 链执行失败，请重试" |
| MCP 服务不可达 | A2 输出"服务暂不可用"+ 不重试 | "服务暂不可用，请稍后重试" |
| 参数缺失 | A2 直接报错 | "缺少必填参数：biz_line" |

---

## 八、测试策略

### 8.1 测试金字塔

```
        ┌─────────────┐
        │  人工验收    │  A1 契约合规率、A2 调用成功率
        └──────┬──────┘
        ┌──────┴──────┐
        │  集成测试    │  10 个端到端用例（5 类意图 × 2 场景）
        └──────┬──────┘
        ┌──────┴──────┐
        │  回归测试    │  P2/P3/P4.1/P4.2 + prefix_match（已有）
        └──────┬──────┘
        ┌──────┴──────┐
        │  单元测试    │  MCP 工具 24 个用例（已有）
        └─────────────┘
```

### 8.2 端到端测试用例

| 用例 ID | 意图 | 场景 | 预期结果 |
|---------|------|------|---------|
| E2E-001 | Project_Query | 领导查 TOP 10 退出项目 | A1 输出 JSON 契约，A2 返回 10 条数据 |
| E2E-002 | Project_Query | 员工查指定 biz_line 明细 | A1 提问 biz_line，A2 返回完整字段 |
| E2E-003 | Fund_Query | 领导查基金规模 TOP 5 | A1 默认 limit=5，A2 返回 5 条 |
| E2E-004 | Fund_Query | 员工查指定基金详情 | A1 提问 fund_id，A2 返回单条详情 |
| E2E-005 | Subfund_Query | 领导查子基金退出排行 | A1 默认排序 exit_amount DESC |
| E2E-006 | Subfund_Query | 员工查指定公司子基金 | A1 提问 company_name |
| E2E-007 | Relation_Query | 领导查 LP 出资 TOP 10 | A1 路由到 query_lp2fund |
| E2E-008 | Relation_Query | 员工查基金-项目关系 | A1 路由到 query_fund2proj |
| E2E-009 | Aggregation_Query | 领导查按 biz_line 分组统计 | A1 路由到 stat_group_by_tool |
| E2E-010 | Project_Query | 审计查高额退出项目 | A1 默认 limit=200，A2 附审计信息 |

### 8.3 验收指标

| 指标 | 目标值 | 监控方式 |
|------|--------|---------|
| A1 JSON 契约合规率 | ≥ 90% | 人工抽检 50 条 |
| A2 工具调用成功率 | ≥ 95% | MCP 服务端日志 |
| A2 重复调用率 | ≤ 5% | MCP 服务端日志（同参数去重统计） |
| A1 重复提问率 | ≤ 10% | LibreChat 对话日志 |
| 端到端响应时间 | ≤ 30 秒 | 人工计时 |
| 用户满意度 | ≥ 4/5 | 主观评分 |

---

## 九、实施路线图

### 9.1 阶段一：MVP 落地（1-2 周）

**目标**：A1-领导版 + 共享 A2 上线，可端到端跑通基础查询。

**任务清单**：

1. 创建 Agent A1-领导版，配置 System Prompt（§5.1），设置 `tools=[]`、`recursion_limit=3`
2. 创建 Agent A2 执行器，挂载 10 个 MCP 工具，配置 System Prompt（§5.2），设置 `end_after_tools=true`
3. 配置 Agent Chain：A1-领导版 → A2，`edgeType=direct`，传递 prompt
4. 准备 10 个端到端测试用例（§8.2）
5. 执行测试，记录 A1 合规率、A2 调用成功率、响应时间
6. 修复发现的问题，迭代 Prompt

**验收标准**：

- Chain 自动传递成功率 ≥ 90%
- A1 输出格式合规率 ≥ 90%
- A2 工具调用成功率 ≥ 95%
- A2 重复调用率 ≤ 5%
- 端到端响应时间 ≤ 30 秒

### 9.2 阶段二：员工版上线（2-3 周）

**目标**：A1-员工版上线，覆盖明细查询场景。

**任务清单**：

1. 基于阶段一数据优化 A1-领导版 Prompt
2. 创建 A1-员工版，调整默认值策略（不预设 biz_line、limit=20-200）
3. 配置 Chain：A1-员工版 → A2
4. 补充员工场景测试用例（E2E-002、E2E-004、E2E-006、E2E-008）
5. 优化 A2 角色感知逻辑（基于阶段一数据）

### 9.3 阶段三：审计版上线（3-4 周）

**目标**：A1-审计版上线，支持审计场景。

**任务清单**：

1. 创建 A1-审计版，配置字段范围限制
2. 配置 Chain：A1-审计版 → A2
3. 开发 LibreChat 日志提取脚本，从对话历史提取审计所需信息
4. 补充审计场景测试用例（E2E-010）
5. 验证审计日志完整性

### 9.4 阶段四：能力扩展（5-8 周，二期）

**目标**：扩展趋势分析、跨域关联能力。

**任务清单**：

1. 评估引入 A3（后处理 Agent）的必要性
   - 趋势分析：A3 对 A2 返回数据做时序分析
   - 图表生成：A3 输出 ASCII/Markdown 图表
2. 跨域关联分析
   - 使用 dwd_all_biz 跨业务视图
   - 使用 stat_investment_summary 汇总工具
3. 数据导出能力评估
   - 评估 MCP 服务端新增 export_csv 工具的可行性
   - 评估后端独立 /api/export 接口的开发成本

---

## 十、风险与缓解

### 10.1 已识别风险

| 风险 ID | 风险描述 | 影响 | 概率 | 缓解措施 |
|---------|---------|------|------|---------|
| R1 | Gemma4 在 A2 阶段重复调用同一工具 | 响应延迟、资源浪费 | 高 | `end_after_tools=true` + Prompt 显式禁止 + 用户监督 |
| R2 | Gemma4 在 A1 阶段重复提问 | 用户体验下降 | 高 | `recursion_limit=3` + Prompt 强制"同一参数最多提问一次" |
| R3 | A1 输出格式不规范导致 A2 无法识别 | A2 执行失败 | 中 | A1 Prompt 给出严格格式示例 + A2 Prompt 容错处理 |
| R4 | Chain 传递上下文过长导致性能下降 | 响应超时 | 低 | 设置 `recursion_limit` + A2 Prompt 聚焦关键信息 |
| R5 | MCP 服务认证失败（401/403） | A2 工具调用失败 | 低 | 参见 project_memory.md 的认证配置规范 |
| R6 | A2 角色识别错误（领导被识别为员工） | 输出格式不当 | 中 | A1 在 `[用户角色]` 字段明确标注，A2 严格读取 |
| R7 | 审计版字段范围限制未生效 | 数据泄露风险 | 中 | A1 Prompt 显式限制 + A2 二次校验 |

### 10.2 监控指标

建议在阶段一 MVP 上线后立即监控：

| 指标 | 目标值 | 监控方式 | 预警阈值 |
|------|--------|---------|---------|
| A1 JSON 契约合规率 | ≥ 90% | 人工抽检 50 条/周 | < 85% 触发 Prompt 优化 |
| A2 工具调用成功率 | ≥ 95% | MCP 服务端日志 | < 90% 触发紧急排查 |
| A2 重复调用率 | ≤ 5% | MCP 服务端日志（同参数去重） | > 10% 触发 Prompt 强化 |
| A1 重复提问率 | ≤ 10% | LibreChat 对话日志 | > 20% 触发 recursion_limit 下调 |
| 端到端响应时间 | ≤ 30 秒 | 人工计时 | > 60 秒 触发性能排查 |
| 用户满意度 | ≥ 4/5 | 主观评分 | < 3/5 触发全面复盘 |

---

## 十一、演进路径

### 11.1 短期演进（3-6 个月）

1. **3 套 Agent 逐套上线**：领导 → 员工 → 审计
2. **Prompt 持续优化**：基于监控数据迭代
3. **Handoff 模式评估**：A1 稳定后，评估升级为 Handoff 支持动态路由

### 11.2 中期演进（6-12 个月）

1. **A3 后处理 Agent**：支持趋势分析、图表生成
2. **跨域关联分析**：基于 dwd_all_biz 视图实现 LP→基金→项目穿透
3. **数据导出能力**：MCP 新增 export_csv 工具或后端独立接口
4. **模型升级评估**：当 GPT-4o-mini 或 Qwen 等更稳定模型可用时，评估替换 Gemma4

### 11.3 长期演进（1 年以上）

1. **Subagents 模式**：A1 派生 A2 在隔离上下文执行
2. **多模型混合**：A1 用轻量模型（分类），A2 用强模型（执行）
3. **自主学习**：基于历史查询数据优化默认值策略

---

## 十二、附录

### 12.1 决策记录

| 决策 ID | 决策内容 | 决策依据 | 日期 |
|---------|---------|---------|------|
| D1 | 采用方案 A（分层共享架构） | 配置量与隔离性平衡 | 2026-07-31 |
| D2 | A1 不挂工具（tools=[]） | 规避 Gemma4 重复调用工具缺陷 | 2026-07-31 |
| D3 | recursion_limit=3 | 化解 Gemma4 重复提问缺陷 | 2026-07-31 |
| D4 | MVP 仅做基础查询 | 控制范围，快速验证 | 2026-07-31 |
| D5 | 逐套上线 | 降低风险，逐步积累数据 | 2026-07-31 |
| D6 | 依赖现有聚合视图 | 避免多工具组合风险 | 2026-07-31 |
| D7 | 审计日志依赖 LibreChat | 零开发，MVP 快速落地 | 2026-07-31 |

### 12.2 参考资料

- [librechat.yaml](file:///LibreChat/librechat.yaml) - LibreChat 主配置文件
- [mcp-inv-server-v2](file:///my-project/mcp-inv-server-v2) - MCP 服务端项目
- 历史教训记录（详见项目内部知识库，不公开）
- [dwd_views.sql](file:///my-project/mcp-inv-server-v2/sql/dwd_views.sql) - DWD 视图定义
- [AgentChain.tsx](file:///LibreChat/client/src/components/SidePanel/Agents/Advanced/AgentChain.tsx) - Chain UI 组件
- [chain.ts](file:///LibreChat/packages/api/src/agents/chain.ts) - Chain 执行逻辑
- [assistants.ts:269-315](file:///LibreChat/packages/data-provider/src/types/assistants.ts#L269-L315) - Agent 类型定义
- [agents.ts:657-687](file:///LibreChat/packages/data-provider/src/types/agents.ts#L657-L687) - GraphEdge 类型定义
- [multi-agent-mcp-design.md v2.0](file:///my-project/docs/plans/multi-agent-mcp-design.md) - 前期方案（已被本方案取代）

### 12.3 术语表

| 术语 | 释义 |
|------|------|
| Endpoint | LibreChat 中的模型接入端点（如 Gemma-4-Local） |
| Assistant / Agent | LibreChat 中基于 Endpoint 创建的智能助手，可挂载工具和 Prompt |
| MCP | Model Context Protocol，模型上下文协议 |
| Agent Chain | LibreChat 原生能力，多个 Agent 顺序执行，自动传递上下文 |
| Agent Handoff | LibreChat 原生能力，Agent 动态决定是否移交控制权 |
| Subagents | LibreChat 原生能力，父 Agent 派生子 Agent 在隔离上下文执行 |
| recursion_limit | Agent 递归调用最大深度，用于限制澄清轮数 |
| end_after_tools | Agent 工具调用后立即结束的配置项 |
| DWD 视图 | 数据仓库明细层视图，共 9 个（4 实体 + 4 关系 + 1 汇总） |

### 12.4 修订历史

| 版本 | 日期 | 修订内容 | 作者 |
|------|------|---------|------|
| v1.0 | 2026-07-31 | 初始版本，基于 brainstorming 深度讨论生成 | GLM-5.2 |
