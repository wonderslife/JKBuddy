"""配置管理模块

使用 pydantic-settings 实现配置管理，支持从 .env 文件加载配置。
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class OAuthMode(str, Enum):
    """OAuth 认证模式"""

    NONE = "none"
    STATIC = "static"
    OAUTH2 = "oauth2"


class Settings(BaseSettings):
    """应用配置主类"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="INV_MCP_",
        extra="ignore",
    )

    # 服务器配置
    host: str = Field(default="0.0.0.0", description="服务器监听地址")
    port: int = Field(default=8080, description="服务器监听端口")
    debug: bool = Field(default=False, description="调试模式")

    # JWT 配置
    jwt_secret: str = Field(default="your-secret-key-change-in-production", description="JWT 密钥")
    jwt_algorithm: str = Field(default="HS256", description="JWT 签名算法")
    jwt_issuer: str = Field(default="inv-mcp-v2", description="JWT 签发者")
    jwt_audience: str = Field(default="inv-mcp-v2", description="JWT 受众")
    access_token_expire_minutes: int = Field(default=30, description="访问令牌过期时间（分钟）")
    refresh_token_expire_days: int = Field(default=7, description="刷新令牌过期时间（天）")

    # 静态令牌列表（原始字符串格式）
    static_tokens: str = Field(
        default="",
        description="静态令牌列表，格式: client_id:secret:role，多个令牌用逗号分隔",
    )

    # OAuth2 配置
    oauth_mode: OAuthMode = Field(default=OAuthMode.STATIC, description="OAuth 认证模式")
    oauth_enabled: bool = Field(default=False, description="是否启用 OAuth2")
    oauth_issuer: str = Field(default="", description="OAuth2 Issuer URL")
    oauth_client_id: str = Field(default="", description="OAuth2 Client ID")
    oauth_client_secret: str = Field(default="", description="OAuth2 Client Secret")

    # 数据库配置
    db_host: str = Field(default="localhost", description="数据库主机地址")
    db_port: int = Field(default=3306, description="数据库端口")
    db_name: str = Field(default="your_db_name", description="数据库名称")
    db_user: str = Field(default="", description="数据库用户名")
    db_password: str = Field(default="", description="数据库密码")

    # 日志配置
    log_level: str = Field(default="INFO", description="日志级别")
    log_file: str = Field(default="logs/inv_mcp.log", description="日志文件路径")

    # 本体定义文件路径（语义单一事实源 SSOT）
    # 留空时使用默认相对路径：<项目根>/ontology/ontology.yaml
    ontology_path: str = Field(
        default="",
        description="本体定义文件路径（ontology.yaml），留空则使用默认相对路径",
    )

    # 管理员角色配置
    admin_roles: str = Field(
        default="admin,system,administrator,超级管理员,平台管理员",
        description="管理员角色列表,多个角色用逗号分隔",
    )

    @field_validator("oauth_mode", mode="before")
    @classmethod
    def validate_oauth_mode(cls, value: Any) -> OAuthMode:
        """验证并转换 oauth_mode"""
        if isinstance(value, OAuthMode):
            return value
        if isinstance(value, str):
            return OAuthMode(value.lower())
        return OAuthMode.STATIC

    def _parse_static_tokens(self) -> list[dict[str, str]]:
        """解析静态令牌配置

        Returns:
            解析后的静态令牌配置列表
        """
        if not self.static_tokens:
            return []

        tokens: list[dict[str, str]] = []
        for token_str in self.static_tokens.split(","):
            parts = token_str.strip().split(":")
            if len(parts) == 3:
                tokens.append(
                    {
                        "client_id": parts[0].strip(),
                        "secret": parts[1].strip(),
                        "role": parts[2].strip(),
                    }
                )

        return tokens

    def _parse_admin_roles(self) -> list[str]:
        """解析管理员角色列表

        Returns:
            管理员角色列表
        """
        if not self.admin_roles:
            return ["admin"]
        return [role.strip() for role in self.admin_roles.split(",")]

    @property
    def parsed_static_tokens(self) -> list[dict[str, str]]:
        """解析后的静态令牌配置列表"""
        return self._parse_static_tokens()

    @property
    def parsed_admin_roles(self) -> list[str]:
        """解析后的管理员角色列表"""
        return self._parse_admin_roles()

    @property
    def admin_roles_list(self) -> list[str]:
        """解析后的管理员角色列表(别名)"""
        return self._parse_admin_roles()


@lru_cache
def get_settings() -> Settings:
    """获取配置单例

    Returns:
        Settings: 配置实例
    """
    return Settings()