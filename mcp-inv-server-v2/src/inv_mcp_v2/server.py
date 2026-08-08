"""FastMCP 服务器入口

启动 MCP 服务器，注册所有 DWD 视图查询工具，配置生命周期事件。
支持 Streamable HTTP 传输，端口默认 8080。

启动方式：
    python -m inv_mcp_v2.server

开发模式（带热重载）：
    uvicorn inv_mcp_v2.server:app --reload --port 8080
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from inv_mcp_v2.config import get_settings
from inv_mcp_v2.lenient_tools import patch_fastmcp_lenient
from inv_mcp_v2.middleware import get_auth_middleware
from inv_mcp_v2.tools import register_all_tools

# 配置日志（级别从 INV_MCP_LOG_LEVEL 读取，默认 INFO）
logging.basicConfig(
    level=getattr(logging, get_settings().log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app) -> AsyncIterator[None]:
    """应用生命周期管理

    启动时：初始化配置
    关闭时：清理数据库连接
    """
    settings = get_settings()
    logger.info(
        "server_starting host=%s port=%s debug=%s",
        settings.host, settings.port, settings.debug,
    )
    logger.info("server_started")

    try:
        yield
    finally:
        # 关闭数据库连接池
        from inv_mcp_v2.db import close_engine
        await close_engine()
        logger.info("server_stopped")


def create_mcp_server() -> FastMCP:
    """创建 FastMCP 服务器并注册全部 DWD 查询工具"""
    from mcp.server.transport_security import TransportSecuritySettings

    settings = get_settings()

    # 启用参数宽容补丁：过滤工具 schema 之外的参数，避免上游 Agent 传错参数导致查询失败
    patch_fastmcp_lenient()

    _transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    )

    mcp = FastMCP(
        "inv-mcp-v2",
        instructions=(
            "投资数据 MCP 服务器 v2。基于 DWD 语义视图，提供 9 大业务域查询能力："
            "基金、子基金、直投项目、子基金底层项目、4 类投资关系、跨域汇总。"
            "所有金额单位统一为万元。"
        ),
        host=settings.host,
        port=settings.port,
        transport_security=_transport_security,
        lifespan=lifespan,
    )

    # 注册全部工具（auth + 9 个 DWD 工具 + 本体工具）
    register_all_tools(mcp)
    logger.info("all_tools_registered count=12")

    return mcp


# ── 创建 ASGI 应用 ──

mcp = create_mcp_server()
app = mcp.streamable_http_app()


# ── HTTP API 路由（供测试页面/前端直接调用）──


async def root(request: Request):
    """根路径：返回服务信息"""
    return JSONResponse({
        "service": "inv-mcp-v2",
        "version": "0.2.0",
        "status": "running",
        "message": "MCP v2 服务已启动（含 DWD 视图查询工具）",
        "endpoints": {
            "/": "服务信息",
            "/mcp/tools": "工具列表（动态）",
            "/mcp/{tool_name}": "调用工具（POST）",
        },
    })


async def api_list_tools(request: Request):
    """返回所有可用工具的元数据（动态从 FastMCP 实例读取）"""
    try:
        tools_meta = await mcp.list_tools()
        tools = []
        for t in tools_meta:
            tools.append({
                "name": t.name,
                "description": (t.description or "").split("\n")[0],  # 首行简述
                "full_description": t.description,
                "endpoint": f"/mcp/{t.name}",
                "method": "POST",
                "input_schema": t.inputSchema or {},
            })
        return JSONResponse({"tools": tools, "count": len(tools)})
    except Exception as e:
        logger.exception("list_tools_failed")
        return JSONResponse({"error": str(e)}, status_code=500)


async def api_call_tool(request: Request):
    """通用工具调用端点：POST /mcp/{tool_name}

    请求体: 工具参数 JSON
    """
    tool_name = request.path_params["tool_name"]
    try:
        body = await request.json()
    except Exception:
        body = {}

    user = getattr(request.state, "user", None)
    # 注入 user 到工具参数（auth 工具需要）
    if user is not None and "user" not in body:
        body["user"] = user

    try:
        result = await mcp.call_tool(tool_name, body)
        # FastMCP 返回 ToolResult 对象
        if hasattr(result, "content"):
            # 提取文本内容
            texts = [c.text for c in result.content if hasattr(c, "text")]
            return JSONResponse({
                "status": "success",
                "tool": tool_name,
                "result": texts[0] if len(texts) == 1 else texts,
            })
        return JSONResponse({"status": "success", "tool": tool_name, "result": str(result)})
    except ValueError as e:
        return JSONResponse({"status": "error", "tool": tool_name, "error": str(e)}, status_code=400)
    except Exception as e:
        logger.exception("tool_call_failed tool=%s", tool_name)
        return JSONResponse({"status": "error", "tool": tool_name, "error": str(e)}, status_code=500)


# 添加路由
app.routes.insert(0, Route("/", root))
app.routes.insert(0, Route("/mcp/tools", api_list_tools, methods=["GET", "OPTIONS"]))
app.routes.insert(0, Route("/mcp/{tool_name}", api_call_tool, methods=["POST", "OPTIONS"]))


# 集成认证中间件
_auth_middleware = get_auth_middleware()
app.add_middleware(BaseHTTPMiddleware, dispatch=_auth_middleware)

logger.info("auth_middleware_registered")


def main() -> None:
    """主入口：启动 uvicorn 服务器"""
    settings = get_settings()
    logger.info(
        "Starting uvicorn on %s:%s with log level %s",
        settings.host, settings.port, settings.log_level,
    )
    uvicorn.run(
        "inv_mcp_v2.server:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        lifespan="on",
        access_log=True,
    )


if __name__ == "__main__":
    main()
