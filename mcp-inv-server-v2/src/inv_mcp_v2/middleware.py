"""Token 认证中间件

基于 FastMCP 的中间件模式，实现 Token 验证授权。
支持静态 Token 和 JWT Token 两种认证方式。
"""

from __future__ import annotations

import hmac
import logging
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from inv_mcp_v2.config import Settings, get_settings

logger = logging.getLogger(__name__)


class TokenAuthMiddleware:
    """Token 认证中间件

    基于 ASGI/Starlette 中间件模式，对 MCP 请求进行认证：
    - 静态 Token：HMAC 安全比较（防止时序攻击）
    - JWT Token：签名验证 + 过期检查

    使用示例：
        middleware = TokenAuthMiddleware(settings)
        app.add_middleware(BaseHTTPMiddleware, dispatch=middleware)
    """

    # 允许跳过认证的路径
    PUBLIC_PATHS: frozenset[str] = frozenset({"/health", "/", "/mcp", "/mcp/tools"})

    def __init__(self, settings: Settings | None = None) -> None:
        """初始化认证中间件

        Args:
            settings: 应用配置（None 则自动获取）
        """
        self._settings = settings or get_settings()
        self._jwt_secret = self._settings.jwt_secret
        self._jwt_algorithm = self._settings.jwt_algorithm

        # 解析静态 Token 配置
        self._static_tokens: dict[str, dict[str, str]] = self._parse_static_tokens(
            self._settings.static_tokens
        )

        logger.info(
            f"Token auth middleware initialized: static_token_count={len(self._static_tokens)}, jwt_algorithm={self._jwt_algorithm}"
        )

    def is_public_path(self, path: str) -> bool:
        """检查路径是否为公开路径"""
        return path in self.PUBLIC_PATHS

    @staticmethod
    def _parse_static_tokens(tokens_config: str | None) -> dict[str, dict[str, str]]:
        """解析静态 Token 配置

        格式：client_id:secret:role，逗号分隔多个
        示例：client1:secret1:admin,client2:secret2:user

        Returns:
            {secret: {client_id, role}} 的映射字典
        """
        if not tokens_config:
            return {}

        result: dict[str, dict[str, str]] = {}
        for token_entry in tokens_config.split(","):
            token_entry = token_entry.strip()
            if not token_entry:
                continue

            parts = token_entry.split(":")
            if len(parts) != 3:
                logger.warning(
                    f"Invalid token config: {token_entry}, expected format: client_id:secret:role"
                )
                continue

            client_id, secret, role = parts
            result[secret] = {
                "client_id": client_id,
                "role": role,
            }

        logger.info(f"Static tokens loaded: count={len(result)}")
        return result

    async def __call__(self, request: Request, call_next) -> Any:
        """中间件主入口

        处理流程：
        1. 处理 OPTIONS 预检请求
        2. 公共路径放行
        3. Authorization 头提取
        4. Token 校验（静态 Token 或 JWT）
        5. 注入用户信息到 request.state
        """
        path = request.url.path

        # 1. 处理 OPTIONS 预检请求
        if request.method == "OPTIONS":
            return self._cors_response()

        # 2. 公共路径放行
        if path in self.PUBLIC_PATHS:
            response = await call_next(request)
            return self._add_cors_headers(response)

        # 3. Token 提取
        auth_header = request.headers.get("authorization", "")
        token = self._extract_bearer_token(auth_header)

        if not token:
            return self._error_response(
                "MISSING_TOKEN",
                "缺少认证信息（需要 Authorization: Bearer <token>）",
                status_code=401,
            )

        # 3. Token 校验
        try:
            user_info = self._verify_token(token)
        except Exception as e:
            logger.error(f"Token verification exception: {e}")
            return self._error_response(
                "INVALID_TOKEN",
                f"认证过程发生异常: {e}",
                status_code=500,
            )

        if not user_info:
            return self._error_response(
                "INVALID_TOKEN",
                "Token无效或已过期",
                status_code=401,
            )

        # 4. 注入用户信息到 request.state
        request.state.user = user_info
        logger.debug(
            f"Auth success: client_id={user_info.get('client_id')}, role={user_info.get('role')}, path={path}"
        )

        response = await call_next(request)
        return self._add_cors_headers(response)

    @staticmethod
    def _add_cors_headers(response) -> Any:
        """为响应添加 CORS 头"""
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, Accept"
        response.headers["Access-Control-Max-Age"] = "86400"
        return response

    @staticmethod
    def _cors_response() -> JSONResponse:
        """构造 CORS 预检响应"""
        response = JSONResponse(
            {"status": "ok"},
            status_code=200,
        )
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, Accept"
        response.headers["Access-Control-Max-Age"] = "86400"
        return response

    @staticmethod
    def _extract_bearer_token(auth_header: str) -> str | None:
        """从 Authorization 头提取 Bearer Token

        支持 "Bearer <token>" 格式，大小写不敏感。
        """
        if not auth_header:
            return None
        if not auth_header.lower().startswith("bearer "):
            return None
        return auth_header[7:].strip()

    def _verify_token(self, token: str) -> dict[str, Any] | None:
        """验证 Token（静态 Token 或 JWT）

        优先尝试静态 Token 验证，失败则尝试 JWT 验证。

        Args:
            token: 客户端提交的 Token

        Returns:
            用户信息字典；None 表示校验失败
        """
        # 1. 尝试静态 Token 验证
        user_info = self._verify_static_token(token)
        if user_info:
            return user_info

        # 2. 尝试 JWT 验证
        user_info = self._verify_jwt_token(token)
        return user_info

    def _verify_static_token(self, token: str) -> dict[str, Any] | None:
        """静态 Token 校验

        使用 hmac.compare_digest 进行恒定时间比较，防止时序攻击。

        Args:
            token: 客户端提交的 Token

        Returns:
            用户信息字典；None 表示校验失败
        """
        if not self._static_tokens:
            return None

        for secret, config in self._static_tokens.items():
            if hmac.compare_digest(token, secret):
                return {
                    "client_id": config["client_id"],
                    "role": config["role"],
                    "auth_mode": "static",
                }

        return None

    def _verify_jwt_token(self, token: str) -> dict[str, Any] | None:
        """JWT Token 校验

        解析 JWT Token，验证签名和过期时间。

        Args:
            token: JWT Token

        Returns:
            用户信息字典；None 表示校验失败
        """
        try:
            import jwt

            payload = jwt.decode(
                token,
                self._jwt_secret,
                algorithms=[self._jwt_algorithm],
                options={"verify_exp": True},
            )

            return {
                "client_id": payload.get("client_id", "unknown"),
                "role": payload.get("role", "user"),
                "auth_mode": "jwt",
                "payload": payload,
            }
        except jwt.ExpiredSignatureError:
            logger.warning("JWT expired")
            return None
        except Exception as e:
            logger.warning(f"JWT invalid: {e}")
            return None

    def _error_response(
        self,
        error_code: str,
        message: str,
        status_code: int = 401,
    ) -> JSONResponse:
        """构造统一格式的错误响应

        Args:
            error_code: 错误码
            message: 错误消息
            status_code: HTTP 状态码

        Returns:
            JSONResponse
        """
        response = JSONResponse(
            {
                "code": status_code,
                "error_code": error_code,
                "msg": message,
            },
            status_code=status_code,
        )
        return self._add_cors_headers(response)


# ── 模块级单例 ──

_middleware: TokenAuthMiddleware | None = None


def get_auth_middleware() -> TokenAuthMiddleware:
    """获取认证中间件单例

    使用单例模式避免重复初始化。
    """
    global _middleware
    if _middleware is None:
        _middleware = TokenAuthMiddleware()
    return _middleware


def reset_auth_middleware() -> None:
    """重置中间件单例（测试用）"""
    global _middleware
    _middleware = None


class RoleBasedAccessMiddleware:
    """基于角色的访问控制中间件

    用于对特定路径进行细粒度的角色检查。
    """

    def __init__(
        self,
        settings: Settings | None = None,
        path_roles: dict[str, list[str]] | None = None,
    ) -> None:
        """初始化中间件

        Args:
            settings: 配置对象（None 则自动获取）
            path_roles: 路径到角色的映射（支持通配符 *）
        """
        self._settings = settings or get_settings()
        self._path_roles = path_roles or {}

    def match_path(self, pattern: str, path: str) -> bool:
        """检查路径是否匹配模式"""
        if pattern.endswith("/*"):
            prefix = pattern[:-2]
            return path.startswith(prefix)
        return path == pattern

    def get_required_roles(self, path: str) -> list[str] | None:
        """获取路径要求的角色"""
        for pattern, roles in self._path_roles.items():
            if self.match_path(pattern, path):
                return roles
        return None

    async def __call__(
        self,
        request: Request,
        call_next,
    ) -> Any:
        """中间件主入口"""
        user = getattr(request.state, "user", None)
        if not user:
            return await call_next(request)

        path = request.url.path
        required_roles = self.get_required_roles(path)

        if not required_roles:
            return await call_next(request)

        user_role = user.get("role", "")
        admin_roles = self._settings.parsed_admin_roles

        if user_role in admin_roles:
            return await call_next(request)

        if user_role not in required_roles:
            return JSONResponse(
                {
                    "code": 403,
                    "error_code": "INSUFFICIENT_PERMISSIONS",
                    "msg": f"权限不足，需要以下角色之一: {', '.join(required_roles)}",
                },
                status_code=403,
            )

        return await call_next(request)


def get_user_from_request(request: Request) -> dict[str, Any] | None:
    """从请求中获取用户信息"""
    return getattr(request.state, "user", None)


def get_current_user() -> dict[str, Any] | None:
    """获取当前用户信息（从上下文）"""
    try:
        from fastmcp.server.dependencies import get_http_request

        request = get_http_request()
        return get_user_from_request(request)
    except Exception:
        return None


def require_role(required_role: str) -> None:
    """要求当前用户具有指定角色"""
    user = get_current_user()
    if not user:
        raise PermissionError("未认证用户")

    user_role = user.get("role", "")
    admin_roles = get_settings().parsed_admin_roles

    if user_role in admin_roles:
        return

    if user_role != required_role:
        raise PermissionError(f"权限不足，需要角色: {required_role}")


def require_any_role(required_roles: list[str]) -> None:
    """要求当前用户具有任一指定角色"""
    user = get_current_user()
    if not user:
        raise PermissionError("未认证用户")

    user_role = user.get("role", "")
    admin_roles = get_settings().parsed_admin_roles

    if user_role in admin_roles:
        return

    if user_role not in required_roles:
        raise PermissionError(f"权限不足，需要以下角色之一: {', '.join(required_roles)}")