"""数据库连接与查询模块

使用 SQLAlchemy 异步引擎连接 MySQL，提供只读查询能力。
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote_plus

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from .config import get_settings

logger = logging.getLogger(__name__)

# 模块级引擎实例（惰性创建）
_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _build_url() -> str:
    """构建数据库连接 URL

    使用 quote_plus 对用户名和密码进行 URL 编码，
    避免密码中的特殊字符（如 @、:、/ 等）被解析为 URL 分隔符。
    """
    settings = get_settings()
    user_encoded = quote_plus(settings.db_user)
    pwd_encoded = quote_plus(settings.db_password)
    return (
        f"mysql+asyncmy://{user_encoded}:{pwd_encoded}"
        f"@{settings.db_host}:{settings.db_port}/{settings.db_name}?charset=utf8mb4"
    )


def get_engine():
    """获取异步引擎单例"""
    global _engine
    if _engine is None:
        url = _build_url()
        logger.info("database_engine_created host=%s port=%s db=%s",
                    get_settings().db_host, get_settings().db_port, get_settings().db_name)
        _engine = create_async_engine(
            url,
            pool_size=10,
            max_overflow=20,
            pool_recycle=3600,
            pool_pre_ping=True,
            echo=False,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """获取会话工厂"""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


def _to_sql_literal(value: Any) -> str:
    """将 Python 参数值渲染为 SQL 字面量，供日志对照使用。"""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    # 字符串/list 等一律按字符串字面量渲染（转义单引号）
    return "'" + str(value).replace("'", "''") + "'"


def _render_sql(sql: str, params: dict[str, Any] | None) -> str:
    """将 :param 命名参数替换为实际值，生成可直接执行的 SQL 文本（仅用于日志）。"""
    if not params:
        return sql
    rendered = sql
    for key, value in params.items():
        rendered = rendered.replace(f":{key}", _to_sql_literal(value))
    return rendered


async def execute_query(
    sql: str,
    params: dict[str, Any] | None = None,
    query_type: str = "data",
) -> list[dict[str, Any]]:
    """执行只读 SQL 查询并返回字典列表

    Args:
        sql: SQL 语句（使用 :param 命名参数）
        params: 参数字典
        query_type: 查询类型标记（data=数据查询 / count=统计 COUNT / agg=聚合统计），用于日志区分

    Returns:
        查询结果列表，每行为一个字典
    """
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(text(sql), params or {})
        rows = result.mappings().all()
        data = [dict(row) for row in rows]
        logger.info(
            "sql_executed type=%s rows=%d params=%s\nsql=%s\nrendered_sql=%s",
            query_type, len(data), params, sql, _render_sql(sql, params),
        )
        return data


async def execute_one(sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """执行查询返回单行"""
    rows = await execute_query(sql, params)
    return rows[0] if rows else None


async def close_engine() -> None:
    """关闭引擎（用于应用退出）"""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
