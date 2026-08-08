"""FastMCP 参数宽容补丁

解决上游 Agent（如 A2 执行器）调用工具时传入 schema 之外参数导致查询失败的问题。

背景
----
LibreChat 多 Agent 架构中，A1 分类器输出抽象的"关键参数"（biz_line/relation_type/action 等），
A2 执行器可能原样透传给工具。FastMCP 默认对未知参数抛 `ValidationError`（unexpected_keyword_argument），
导致工具调用失败。

本补丁在工具参数校验前，按工具 schema 过滤掉未知参数，使工具能忽略冗余参数并正常执行。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def patch_fastmcp_lenient() -> None:
    """启用 FastMCP 工具参数宽容模式（幂等，可重复调用）。

    在 launch 处调用一次即可，作用于所有已注册及后续注册的工具。
    """
    import fastmcp.tools.function_tool as ft

    if getattr(ft.FunctionTool, "_lenient_patched", False):
        return

    _orig_execute = ft.FunctionTool._execute

    async def _patched_execute(
        self: ft.FunctionTool,
        type_adapter: Any,
        exec_is_async: bool,
        arguments: dict[str, Any],
    ) -> Any:
        filtered = _filter_unknown_params(type_adapter, arguments)
        return await _orig_execute(self, type_adapter, exec_is_async, filtered)

    ft.FunctionTool._execute = _patched_execute
    ft.FunctionTool._lenient_patched = True  # type: ignore[attr-defined]
    logger.info("fastmcp_lenient_patch_applied")


def _filter_unknown_params(type_adapter: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    """按工具参数 schema 过滤 arguments，仅保留已声明的参数。

    Args:
        type_adapter: FastMCP 构建的工具参数 TypeAdapter（含 json_schema）。
        arguments: 待校验的参数。

    Returns:
        过滤后的参数；若无法解析 schema 则原样返回。
    """
    if not isinstance(arguments, dict):
        return arguments

    try:
        schema = type_adapter.json_schema()
        properties = schema.get("properties", {})
        if not properties:
            return arguments

        filtered = {k: v for k, v in arguments.items() if k in properties}
        dropped = set(arguments) - set(filtered)
        if dropped:
            logger.info(
                "filtered_unknown_args dropped=%s", sorted(dropped)
            )
        return filtered
    except Exception:
        logger.exception("filter_unknown_params_failed")
        return arguments