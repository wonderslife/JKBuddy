# Investment MCP Server v2

基于 FastMCP 的投资数据 MCP 服务器，支持 Token 验证授权。

## 架构

```
mcp-inv-server-v2/
├── src/inv_mcp_v2/          # 源代码
│   ├── __init__.py
│   ├── config.py            # 配置管理（pydantic-settings）
│   ├── auth.py              # Token / OAuth2 认证核心
│   ├── middleware.py        # FastMCP 中间件
│   ├── db.py                # 数据库访问
│   ├── lenient_tools.py     # 宽松参数解析工具
│   ├── server.py            # 服务器入口
│   ├── ontology/            # 本体（SSOT）加载与校验
│   │   ├── __init__.py
│   │   ├── drift.py         # 本体漂移检测
│   │   ├── generator.py     # 机读/人读投影生成
│   │   ├── model.py         # 本体数据模型
│   │   └── ontology.yaml    # 本体定义（单一事实源，脱敏示例）
│   └── tools/               # DWD 视图查询工具
│       ├── __init__.py
│       ├── base.py          # 工具基类/公共逻辑
│       ├── auth_tools.py    # 鉴权工具
│       ├── fund.py          # 基金 / 子基金查询
│       ├── project.py       # 直投项目查询
│       ├── relations.py     # 投资关系查询
│       ├── subfund.py       # 子基金查询
│       ├── subfund_proj.py  # 子基金底层项目查询
│       ├── summary.py       # 跨域汇总统计
│       └── ontology_tools.py# 本体查询工具
├── pyproject.toml           # 项目配置
├── .env.example             # 环境变量示例
└── README.md                # 本文件
```

## 功能模块

### 1. Token 验证授权模块

- Token 生成（JWT）
- Token 验证
- Token 刷新
- Token 过期处理
- 基于角色的访问控制

### 2. DWD 语义查询

基于本体（ontology）将自然语言意图映射为 9 个 DWD 视图的查询工具，
覆盖基金、子基金、直投项目、子基金底层项目及 4 类投资关系与跨域汇总。

## 安装

```bash
# 使用 uv（推荐）
uv sync

# 或使用 pip
pip install -e .
```

## 配置

1. 复制环境变量示例：
```bash
cp .env.example .env
```

2. 修改 `.env` 文件配置

## 运行

```bash
# 开发模式
uv run mcp dev src/inv_mcp_v2/server.py

# 或直接运行
uv run python -m inv_mcp_v2.server
```

## 测试

```bash
uv run pytest tests/ -v
```

## License

MIT