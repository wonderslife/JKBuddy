"""Investment MCP Server v2

基于 FastMCP 的投资数据查询服务,支持 JWT Token 认证。
"""

__version__ = "0.1.0"

from .auth import (
    InvalidTokenError,
    TokenData,
    TokenExpiredError,
    create_access_token,
    create_refresh_token,
    extract_token_from_header,
    is_admin,
    parse_static_tokens,
    refresh_access_token,
    verify_token,
)
from .config import OAuthMode, Settings, get_settings

__all__ = [
    # 认证相关
    "TokenData",
    "TokenExpiredError",
    "InvalidTokenError",
    "create_access_token",
    "create_refresh_token",
    "verify_token",
    "refresh_access_token",
    "parse_static_tokens",
    "is_admin",
    "extract_token_from_header",
    # 配置相关
    "Settings",
    "OAuthMode",
    "get_settings",
]