# JKBuddy 智能业务伙伴系统

基于 **LibreChat** 框架 + **MCP（Model Context Protocol）** 构建的金控集团智能业务伙伴系统。

> 本仓库为**脱敏后的公开版本**。真实生产环境涉及的内网地址、数据库凭据、密钥、真实企业名称均已替换为占位符/抽象名。请勿将任何生产 `.env` 或密钥提交到本仓库。

## 目录结构

```
JKBuddy/
├── librechat/              # LibreChat 完整源码快照（干净副本，无 .git/node_modules/.env）
├── JKBuddy-client/         # LibreChat 定制补丁与配置（Skill + librechat.yaml + Docker）
├── mcp-inv-server-v2/      # MCP 服务：投资数据语义查询工具（FastMCP + DWD 视图）
├── scripts/                # Agent 指令管理与脱敏工具脚本
├── docs/                   # 核心设计文档（脱敏）
└── README.md
```

## 核心能力

- **MCP 服务**：基于 DWD（Data Warehouse Dimension）语义视图，提供 9 大业务域查询能力（基金、子基金、直投项目、子基金底层项目、4 类投资关系、跨域汇总），所有金额单位统一为万元。
- **双 Agent 问数架构**：
  - **A1 意图分类器**：将用户问题映射为「确定性分类 + 关键参数」
  - **A2 执行器**：通过真实 MCP 工具调用查询数据、生成图表、导出 Excel
- **本地模型接入**：支持部署本地大模型（Gemma / Qwen 等），内网环境自托管。
- **本地代码沙箱**：通过 code-command 自托管代码解释器，实现内网环境下的图表生成与 Excel 导出。

## 快速开始

### 1. 部署 MCP 服务

```bash
cd mcp-inv-server-v2
cp .env.example .env   # 编辑填入你的数据库配置
pip install -r requirements.txt
python -m inv_mcp_v2.server
```

### 2. 配置 LibreChat 客户端

`JKBuddy-client/` 为 LibreChat 的定制补丁（Skill 目录、`librechat.yaml` 本地模型、Docker 配置），
`librechat/` 为完整的 LibreChat 源码快照。将定制补丁合并到源码快照后启动，详见 `docs/01-多Agent问数架构设计.md`。

## 安全说明

本仓库为**脱敏后的公开版本**，不包含任何真实生产凭据、内网地址、密钥或真实企业/业务数据。
部署时请：
1. 使用 `.env.example` 创建你自己的 `.env`
2. 切勿提交 `.env`、密钥、真实内网地址
3. 参考 `.gitignore` 的忽略规则
4. 业务规则、数仓字段设计与智能体提示词已做抽象化处理，仅作技术展示

## License

MIT
