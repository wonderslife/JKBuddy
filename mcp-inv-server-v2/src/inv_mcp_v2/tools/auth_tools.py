"""认证相关工具（保留原有 get_current_user / test_auth）"""

from __future__ import annotations

from typing import Any


def register_auth_tools(mcp) -> None:
    """注册认证相关工具"""

    @mcp.tool()
    def get_current_user(user: dict[str, Any] | None = None) -> dict[str, Any]:
        """获取当前认证用户信息（client_id、role、auth_mode）"""
        if user:
            return {"status": "authenticated", "user": user}
        return {"status": "unauthenticated", "message": "未提供有效认证信息"}

    @mcp.tool()
    def test_auth(user: dict[str, Any] | None = None) -> dict[str, Any]:
        """测试 Token 认证是否工作"""
        if user:
            return {"status": "success", "message": "认证成功", "user": user}
        return {"status": "failed", "message": "认证失败"}
