"""JWT Token 认证模块

提供 JWT token 的生成、验证、刷新功能。
使用 PyJWT 库实现 token 管理。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import jwt
from pydantic import BaseModel, Field

from .config import get_settings


# ── 异常定义 ──


class TokenExpiredError(Exception):
    """Token 已过期异常"""

    def __init__(self, message: str = "Token has expired"):
        self.message = message
        super().__init__(self.message)


class InvalidTokenError(Exception):
    """Token 无效异常"""

    def __init__(self, message: str = "Invalid token"):
        self.message = message
        super().__init__(self.message)


# ── Token 数据模型 ──


class TokenData(BaseModel):
    """Token 中包含的用户信息

    Attributes:
        client_id: 客户端ID
        role: 用户角色
        exp: 过期时间(Unix timestamp)
        iat: 签发时间(Unix timestamp)
        company: 所属公司(可选)
    """

    client_id: str = Field(..., description="客户端ID")
    role: str = Field(..., description="用户角色")
    exp: int = Field(..., description="过期时间(Unix timestamp)")
    iat: int = Field(..., description="签发时间(Unix timestamp)")
    company: str | None = Field(default=None, description="所属公司")
    token_type: str = Field(default="access", description="Token类型: access/refresh")


# ── Token 生成函数 ──


def create_access_token(
    client_id: str,
    role: str,
    company: str | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """生成 Access Token

    Args:
        client_id: 客户端ID
        role: 用户角色
        company: 所属公司(可选)
        expires_delta: 自定义过期时间间隔(可选)

    Returns:
        str: JWT token 字符串

    Example:
        >>> token = create_access_token("client123", "admin", company="某创投集团")
        >>> print(token)
        eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
    """
    settings = get_settings()

    # 计算过期时间
    now = datetime.utcnow()
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.access_token_expire_minutes)

    # 构建 payload
    payload: dict[str, Any] = {
        "client_id": client_id,
        "role": role,
        "exp": expire,
        "iat": now,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "token_type": "access",
    }

    # 添加可选字段
    if company:
        payload["company"] = company

    # 生成 token
    token = jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    return token


def create_refresh_token(
    client_id: str,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    """生成 Refresh Token

    Refresh Token 用于刷新 Access Token,通常有效期更长。
    Refresh Token 不包含敏感信息,仅用于身份验证。

    Args:
        client_id: 客户端ID
        role: 用户角色
        expires_delta: 自定义过期时间间隔(可选)

    Returns:
        str: JWT refresh token 字符串

    Example:
        >>> refresh_token = create_refresh_token("client123", "admin")
        >>> print(refresh_token)
        eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
    """
    settings = get_settings()

    # 计算过期时间
    now = datetime.utcnow()
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.refresh_token_expire_days)

    # 构建 payload(仅包含必要信息)
    payload: dict[str, Any] = {
        "client_id": client_id,
        "role": role,
        "exp": expire,
        "iat": now,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "token_type": "refresh",
    }

    # 生成 token
    token = jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    return token


# ── Token 验证函数 ──


def verify_token(token: str, token_type: str = "access") -> TokenData:
    """验证 Token 有效性并返回 TokenData

    Args:
        token: JWT token 字符串
        token_type: 预期的 token 类型("access" 或 "refresh")

    Returns:
        TokenData: Token 中包含的用户信息

    Raises:
        TokenExpiredError: Token 已过期
        InvalidTokenError: Token 无效(签名错误、格式错误等)

    Example:
        >>> token = create_access_token("client123", "admin")
        >>> token_data = verify_token(token)
        >>> print(token_data.client_id)
        client123
    """
    settings = get_settings()

    try:
        # 解码 token
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
        )

        # 验证 token 类型
        if payload.get("token_type") != token_type:
            raise InvalidTokenError(f"Invalid token type. Expected {token_type}, got {payload.get('token_type')}")

        # 构建 TokenData
        # JWT payload 中的 exp/iat 可能是 int 或 float,统一转换为 int
        token_data = TokenData(
            client_id=payload["client_id"],
            role=payload["role"],
            exp=int(payload["exp"]),
            iat=int(payload["iat"]),
            company=payload.get("company"),
            token_type=payload.get("token_type", "access"),
        )

        return token_data

    except jwt.ExpiredSignatureError as e:
        raise TokenExpiredError("Token has expired") from e
    except jwt.InvalidIssuerError as e:
        raise InvalidTokenError("Invalid issuer") from e
    except jwt.InvalidAudienceError as e:
        raise InvalidTokenError("Invalid audience") from e
    except jwt.InvalidSignatureError as e:
        raise InvalidTokenError("Invalid signature") from e
    except jwt.DecodeError as e:
        raise InvalidTokenError("Invalid token format") from e
    except KeyError as e:
        raise InvalidTokenError(f"Missing required field: {e}") from e
    except Exception as e:
        raise InvalidTokenError(f"Token validation failed: {e}") from e


# ── Token 刷新函数 ──


def refresh_access_token(refresh_token: str) -> str:
    """使用 Refresh Token 生成新的 Access Token

    验证 refresh token 的有效性,然后签发新的 access token。

    Args:
        refresh_token: Refresh token 字符串

    Returns:
        str: 新的 access token 字符串

    Raises:
        TokenExpiredError: Refresh token 已过期
        InvalidTokenError: Refresh token 无效或不是 refresh 类型

    Example:
        >>> refresh_token = create_refresh_token("client123", "admin")
        >>> new_access_token = refresh_access_token(refresh_token)
        >>> print(new_access_token)
        eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
    """
    # 验证 refresh token
    token_data = verify_token(refresh_token, token_type="refresh")

    # 使用 refresh token 中的信息生成新的 access token
    new_access_token = create_access_token(
        client_id=token_data.client_id,
        role=token_data.role,
        company=token_data.company,
    )

    return new_access_token


# ── 静态 Token 解析 ──


def parse_static_tokens(tokens_config: str) -> dict[str, TokenData]:
    """解析静态 Token 配置

    从配置字符串解析静态 token 映射关系。
    配置格式:"client_id:secret:role,client_id2:secret2:role2"

    Args:
        tokens_config: Token 配置字符串

    Returns:
        dict[str, TokenData]: secret -> TokenData 的映射字典

    Example:
        >>> tokens = parse_static_tokens("client1:secret123:admin,client2:secret456:user")
        >>> print(tokens["secret123"].client_id)
        client1
        >>> print(tokens["secret123"].role)
        admin
    """
    result: dict[str, TokenData] = {}

    if not tokens_config:
        return result

    # 分割多个 token 配置
    for entry in tokens_config.split(","):
        parts = entry.strip().split(":")

        # 验证格式
        if len(parts) != 3:
            continue

        client_id, secret, role = parts

        # 创建 TokenData
        # 注意:静态 token 不包含 exp/iat,使用当前时间作为占位符
        now = int(datetime.utcnow().timestamp())
        token_data = TokenData(
            client_id=client_id,
            role=role,
            exp=now,  # 静态 token 不会真正过期
            iat=now,
            company=None,
            token_type="static",
        )

        result[secret] = token_data

    return result


# ── 辅助函数 ──


def is_admin(role: str) -> bool:
    """判断角色是否为管理员

    Args:
        role: 用户角色

    Returns:
        bool: 是否为管理员

    Example:
        >>> is_admin("admin")
        True
        >>> is_admin("user")
        False
    """
    settings = get_settings()
    return role in settings.admin_roles_list


def extract_token_from_header(auth_header: str) -> str | None:
    """从 Authorization header 提取 token

    支持 Bearer token 格式

    Args:
        auth_header: Authorization header 值

    Returns:
        str | None: token 字符串,无效则返回 None

    Example:
        >>> token = extract_token_from_header("Bearer eyJhbGciOi...")
        >>> print(token)
        eyJhbGciOi...
    """
    if not auth_header:
        return None

    # 支持 Bearer token 格式
    if auth_header.startswith("Bearer "):
        return auth_header[7:]

    return auth_header if auth_header else None