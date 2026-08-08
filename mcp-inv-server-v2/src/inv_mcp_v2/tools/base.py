"""工具公共辅助函数

所有工具直接查询数据库中已创建的 dwd_* 视图（见 sql/dwd_views.sql）。
字段/白名单等语义定义以本体（ontology/ontology.yaml）为单一事实源（SSOT），
本模块在启动/首次导入时自动从本体机读投影加载运行时白名单，无需手工维护
或运行任何同步命令。

字段名严格对齐 dwd_views.sql 中的视图定义：
- dwd_fund:        fund_type, fund_phase（中文名通过 CASE 直接输出，无 _name 后缀）
- dwd_subfund:     phase
- dwd_project:     phase, biz_line
- dwd_fund2subfund: fund_id, fund_name（不是 parent_fund_*）
- dwd_subfund2proj: subfund_proj_id, subfund_proj_name（不是 proj_*）
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from ..db import execute_query
from ..ontology import Whitelists, generate_whitelists, get_ontology, get_ontology_path

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_whitelists() -> Whitelists:
    """从本体（SSOT）加载并生成运行时白名单（懒加载单例，fail-fast）。

    进程内首次调用后缓存，返回与本体机读投影一致的 Whitelists 容器。
    本体加载失败时抛错，禁止静默降级为空白名单（否则等于无白名单，
    存在 SQL 注入风险）。
    """
    whitelists = generate_whitelists(get_ontology())
    views = sorted(whitelists.ALLOWED_FIELDS.keys())
    logger.info(
        "ontology_loaded path=%s views=%d objects=%d links=%d rules=%d view_list=%s",
        get_ontology_path(),
        len(views),
        len(get_ontology().object_types),
        len(get_ontology().link_types),
        len(get_ontology().rules),
        ",".join(views),
    )
    return whitelists


# ── 运行时白名单：本体(SSOT) → 机读投影 ──
# 启动/首次导入时从 ontology.yaml 加载，随本体变更自动生效，无需命令同步。
_wl = get_whitelists()
ALLOWED_FIELDS: dict[str, set[str]] = _wl.ALLOWED_FIELDS
DATE_RANGE_FIELDS: dict[str, set[str]] = _wl.DATE_RANGE_FIELDS
AMOUNT_RANGE_FIELDS: dict[str, set[str]] = _wl.AMOUNT_RANGE_FIELDS
GROUP_BY_FIELDS: dict[str, set[str]] = _wl.GROUP_BY_FIELDS
AGG_FIELDS: dict[str, set[str]] = _wl.AGG_FIELDS
NULL_CHECK_FIELDS: dict[str, set[str]] = _wl.NULL_CHECK_FIELDS
PREFIX_MATCH_FIELDS: dict[str, set[str]] = _wl.PREFIX_MATCH_FIELDS
ALLOWED_GROUP_BY_EXPRS: dict[str, set[str]] = _wl.ALLOWED_GROUP_BY_EXPRS
STABLE_ORDER_FIELDS: dict[str, str] = _wl.STABLE_ORDER_FIELDS
DEFAULT_FIELDS: dict[str, list[str]] = _wl.DEFAULT_FIELDS
del _wl

# 允许的聚合函数（白名单，防 SQL 注入）。与视图无关的安全常量，不随本体变化。
ALLOWED_AGG_FUNCS = frozenset({"SUM", "AVG", "MIN", "MAX", "COUNT"})


def build_where(
    filters: dict[str, Any],
    view: str,
    date_ranges: dict[str, tuple[str | None, str | None]] | None = None,
    amount_ranges: dict[str, tuple[float | None, float | None]] | None = None,
    null_fields: list[str] | None = None,
    not_null_fields: list[str] | None = None,
    prefix_filters: dict[str, str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """构建 WHERE 子句（白名单过滤）

    Args:
        filters: 精确匹配/模糊匹配的过滤条件
        view: 视图名
        date_ranges: 日期范围过滤条件
            key = 日期字段名，value = (start, end)，None 表示该方向不限制
            例：{"cap_date": ("2026-01-01", "2026-12-31")}
        amount_ranges: 金额范围过滤条件（单位万元）
            key = 金额字段名，value = (min, max)，None 表示该方向不限制
            例：{"invest_amount": (1000.0, 5000.0)}
        null_fields: 需要 IS NULL 过滤的字段列表
            字段必须在 NULL_CHECK_FIELDS[view] 白名单中
            例：["cap_date", "invest_amount"]
        not_null_fields: 需要 IS NOT NULL 过滤的字段列表
            字段必须在 NULL_CHECK_FIELDS[view] 白名单中
            例：["ownership_pct"]
        prefix_filters: 前缀匹配过滤条件（LIKE 'xxx%'）
            key = 字段名，value = 前缀字符串（不含 %，函数内自动追加）
            字段必须在 PREFIX_MATCH_FIELDS[view] 白名单中
            例：{"fund_name": "某集团"} 生成 `fund_name LIKE '某集团%'`

    Returns:
        (where_clause, params) - where_clause 以 " AND " 开头（用于追加到 WHERE 1=1 后），
        无条件时为空字符串
    """
    allowed = ALLOWED_FIELDS.get(view, set())
    allowed_null_checks = NULL_CHECK_FIELDS.get(view, set())
    allowed_prefix = PREFIX_MATCH_FIELDS.get(view, set())
    clauses: list[str] = []
    params: dict[str, Any] = {}

    # 处理精确/模糊匹配
    for key, value in filters.items():
        if key not in allowed or value is None or value == "":
            continue

        param_name = f"p_{key}"
        # 名称类字段支持 LIKE 模糊匹配
        if key.endswith("_name") or key == "company_name":
            clauses.append(f"`{key}` LIKE :{param_name}")
            params[param_name] = f"%{value}%"
        else:
            clauses.append(f"`{key}` = :{param_name}")
            params[param_name] = value

    # 处理日期范围
    if date_ranges:
        allowed_dates = DATE_RANGE_FIELDS.get(view, set())
        for field, (start, end) in date_ranges.items():
            # 字段必须在白名单 + 允许范围查询的字段集合中
            if field not in allowed or field not in allowed_dates:
                continue
            if start and end:
                clauses.append(f"`{field}` BETWEEN :{field}_start AND :{field}_end")
                params[f"{field}_start"] = start
                params[f"{field}_end"] = end
            elif start:
                clauses.append(f"`{field}` >= :{field}_start")
                params[f"{field}_start"] = start
            elif end:
                clauses.append(f"`{field}` <= :{field}_end")
                params[f"{field}_end"] = end

    # 处理金额范围
    if amount_ranges:
        allowed_amounts = AMOUNT_RANGE_FIELDS.get(view, set())
        for field, (min_val, max_val) in amount_ranges.items():
            # 字段必须在白名单 + 允许范围查询的金额字段集合中
            if field not in allowed or field not in allowed_amounts:
                continue
            if min_val is not None and max_val is not None:
                clauses.append(f"`{field}` BETWEEN :{field}_min AND :{field}_max")
                params[f"{field}_min"] = min_val
                params[f"{field}_max"] = max_val
            elif min_val is not None:
                clauses.append(f"`{field}` >= :{field}_min")
                params[f"{field}_min"] = min_val
            elif max_val is not None:
                clauses.append(f"`{field}` <= :{field}_max")
                params[f"{field}_max"] = max_val

    # 处理 IS NULL
    if null_fields:
        for field in null_fields:
            # 字段必须在白名单 + 允许 NULL 检查的字段集合中（防 SQL 注入）
            if field in allowed and field in allowed_null_checks:
                clauses.append(f"`{field}` IS NULL")

    # 处理 IS NOT NULL
    if not_null_fields:
        for field in not_null_fields:
            if field in allowed and field in allowed_null_checks:
                clauses.append(f"`{field}` IS NOT NULL")

    # 处理前缀匹配（LIKE 'xxx%'）
    if prefix_filters:
        for field, value in prefix_filters.items():
            # 字段必须在前缀匹配白名单中（防 SQL 注入）
            if field not in allowed_prefix or value is None or value == "":
                continue
            param_name = f"prefix_{field}"
            clauses.append(f"`{field}` LIKE :{param_name}")
            params[param_name] = f"{value}%"

    return (" AND " + " AND ".join(clauses)) if clauses else "", params


async def query_view(
    view: str,
    filters: dict[str, Any] | None = None,
    limit: int = 20,
    offset: int = 0,
    order_by: str | None = None,
    date_ranges: dict[str, tuple[str | None, str | None]] | None = None,
    amount_ranges: dict[str, tuple[float | None, float | None]] | None = None,
    order_direction: str = "DESC",
    null_fields: list[str] | None = None,
    not_null_fields: list[str] | None = None,
    prefix_filters: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """通用视图查询

    Args:
        view: 视图名（如 dwd_fund、dwd_project、dwd_lp2fund）
        filters: 精确匹配/模糊匹配的过滤条件
        limit: 返回行数上限（最大 200）
        offset: 偏移量
        order_by: 排序字段（必须为白名单字段）
        date_ranges: 日期范围过滤，key=字段名，value=(start, end)
        amount_ranges: 金额范围过滤（单位万元），key=字段名，value=(min, max)
        order_direction: 排序方向，可选值 "ASC"（升序）/ "DESC"（降序，默认）。
            ⚠️ 仅在 order_by 非空时生效；非法值会被强制重置为 "DESC"。
        null_fields: 需要 IS NULL 过滤的字段列表（必须在 NULL_CHECK_FIELDS 白名单中）
        not_null_fields: 需要 IS NOT NULL 过滤的字段列表（必须在 NULL_CHECK_FIELDS 白名单中）
        prefix_filters: 前缀匹配过滤条件（LIKE 'xxx%'）
            key=字段名，value=前缀字符串。字段必须在 PREFIX_MATCH_FIELDS 白名单中。
            例：{"fund_name": "某集团"} 生成 `fund_name LIKE '某集团%'`

    Returns:
        查询结果列表（仅返回 DEFAULT_FIELDS 中指定的字段）
    """
    if view not in VIEW_NAMES:
        raise ValueError(f"未知视图: {view}")

    # 构建追加 WHERE 条件
    where_clause, params = build_where(
        filters or {}, view, date_ranges, amount_ranges,
        null_fields=null_fields, not_null_fields=not_null_fields,
        prefix_filters=prefix_filters,
    )

    # 安全的排序字段 + 方向
    # order_direction 仅允许 ASC / DESC，其他值一律降级为 DESC（防 SQL 注入）
    direction = "ASC" if str(order_direction).upper() == "ASC" else "DESC"

    # 获取稳定排序兜底字段（每个视图的唯一ID字段）
    stable_field = STABLE_ORDER_FIELDS.get(view, None)

    # 构建排序子句：
    # 1. 若用户 order_by 合法，用户排序 + 兜底唯一排序（保证唯一性）
    # 2. 若用户 order_by 非法或为空，仅用兜底排序（稳定分页，避免重复）
    if order_by and order_by in ALLOWED_FIELDS.get(view, set()):
        if stable_field:
            order_clause = f" ORDER BY `{order_by}` {direction}, `{stable_field}` ASC"
        else:
            order_clause = f" ORDER BY `{order_by}` {direction}"
    else:
        # 用户排序无效，使用兜底稳定排序
        if stable_field:
            order_clause = f" ORDER BY `{stable_field}` ASC"
        else:
            order_clause = ""

    # 限制最大返回行数
    limit = max(1, min(limit, 200))

    # 仅 SELECT 白名单中的字段
    fields = ", ".join(f"`{f}`" for f in DEFAULT_FIELDS.get(view, ["*"]))
    sql = f"SELECT {fields} FROM `{view}` WHERE 1=1{where_clause}{order_clause} LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset

    return await execute_query(sql, params)


async def count_view(
    view: str,
    filters: dict[str, Any] | None = None,
    date_ranges: dict[str, tuple[str | None, str | None]] | None = None,
    amount_ranges: dict[str, tuple[float | None, float | None]] | None = None,
    null_fields: list[str] | None = None,
    not_null_fields: list[str] | None = None,
    prefix_filters: dict[str, str] | None = None,
) -> int:
    """统计视图行数"""
    if view not in VIEW_NAMES:
        raise ValueError(f"未知视图: {view}")

    where_clause, params = build_where(
        filters or {}, view, date_ranges, amount_ranges,
        null_fields=null_fields, not_null_fields=not_null_fields,
        prefix_filters=prefix_filters,
    )
    sql = f"SELECT COUNT(*) AS cnt FROM `{view}` WHERE 1=1{where_clause}"
    rows = await execute_query(sql, params, query_type="count")
    return int(rows[0]["cnt"]) if rows else 0


async def execute_raw(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """执行原始 SQL（供 summary 工具使用）"""
    return await execute_query(sql, params)


async def stat_group_by(
    view: str,
    group_by: str | None = None,
    group_by_expr: str | None = None,
    filters: dict[str, Any] | None = None,
    date_ranges: dict[str, tuple[str | None, str | None]] | None = None,
    amount_ranges: dict[str, tuple[float | None, float | None]] | None = None,
    agg_funcs: dict[str, str] | None = None,
    order_by: str | None = None,
    order_direction: str = "DESC",
    limit: int = 50,
    null_fields: list[str] | None = None,
    not_null_fields: list[str] | None = None,
    prefix_filters: dict[str, str] | None = None,
) -> dict[str, Any]:
    """通用分组统计（GROUP BY + 聚合）

    支持两种分组方式（二选一）：
    - group_by: 按字段名分组（如 fund_type）
    - group_by_expr: 按表达式分组（如 YEAR(cap_date)），用于按年份/月份统计

    聚合字段别名规则：{func_lower}_{field}（如 sum_invest_amount、avg_total_size、count）。

    Args:
        view: 视图名（如 dwd_fund、dwd_project）
        group_by: 分组字段（必须在 GROUP_BY_FIELDS 白名单中）
        group_by_expr: 分组表达式（必须在 ALLOWED_GROUP_BY_EXPRS 白名单中）
            支持的表达式：YEAR(cap_date), MONTH(cap_date), YEAR(in_date), YEAR(flow_time) 等
            与 group_by 互斥，优先使用 group_by_expr
        filters: 精确/模糊匹配过滤条件（复用 build_where）
        date_ranges: 日期范围过滤
        amount_ranges: 金额范围过滤
        agg_funcs: 聚合配置 {字段: 函数}，函数可选 SUM/AVG/MIN/MAX/COUNT。
            None 时默认对 AGG_FIELDS[view] 中所有字段做 SUM。
            特殊：agg_funcs={"*": "COUNT"} 仅做 COUNT(*)。
        order_by: 排序字段（分组字段/表达式别名或聚合字段别名，如 sum_invest_amount）
        order_direction: 排序方向，"ASC"/"DESC"（默认 DESC）
        limit: 返回分组数上限（1-200，默认 50）
        null_fields: 需要 IS NULL 过滤的字段列表（必须在 NULL_CHECK_FIELDS 白名单中）
        not_null_fields: 需要 IS NOT NULL 过滤的字段列表（必须在 NULL_CHECK_FIELDS 白名单中）

    Returns:
        {
            "view": str, "group_by": str, "group_by_expr": str | None,
            "agg_funcs": {field: func},
            "count": int,  # 分组数
            "data": [{<分组字段>, <聚合别名>, ...}]
        }

    Raises:
        ValueError: 视图或分组字段/表达式不在白名单中
    """
    if view not in VIEW_NAMES:
        raise ValueError(f"未知视图: {view}")

    # 分组方式选择：优先 group_by_expr
    use_expr = group_by_expr is not None
    if use_expr:
        # 表达式分组模式
        if group_by_expr not in ALLOWED_GROUP_BY_EXPRS.get(view, set()):
            allowed = sorted(ALLOWED_GROUP_BY_EXPRS.get(view, set()))
            raise ValueError(
                f"视图 {view} 不支持按表达式 '{group_by_expr}' 分组。"
                f"允许表达式: {', '.join(allowed) or '(无)'}"
            )
        # 表达式的别名：YEAR(cap_date) -> year_cap_date
        expr_alias = group_by_expr.lower().replace("(", "_").replace(")", "")
        group_clause = f"{group_by_expr} AS `{expr_alias}`"
        group_by_sql = group_by_expr
        group_label = group_by_expr  # 用于返回结果标记
    else:
        # 字段分组模式
        if not group_by:
            raise ValueError("必须提供 group_by 或 group_by_expr 之一")
        if group_by not in GROUP_BY_FIELDS.get(view, set()):
            allowed = sorted(GROUP_BY_FIELDS.get(view, set()))
            raise ValueError(
                f"视图 {view} 不支持按 '{group_by}' 分组。"
                f"允许字段: {', '.join(allowed) or '(无)'}"
            )
        expr_alias = group_by
        group_clause = f"`{group_by}` AS `{group_by}`"
        group_by_sql = f"`{group_by}`"
        group_label = group_by

    # 构建聚合配置（agg_funcs）
    allowed_aggs = AGG_FIELDS.get(view, set())
    if agg_funcs is None:
        # 默认：对所有金额字段做 SUM
        agg_funcs = {f: "SUM" for f in allowed_aggs}
    else:
        # 校验并规范化用户传入的 agg_funcs
        validated: dict[str, str] = {}
        for field, func in agg_funcs.items():
            # 特殊字段 "*" 表示 COUNT(*)，不受 AGG_FIELDS 白名单限制
            if field == "*":
                func_upper = str(func).upper()
                if func_upper == "COUNT":
                    validated["*"] = "COUNT"
                continue
            if field not in allowed_aggs:
                continue
            func_upper = str(func).upper()
            if func_upper not in ALLOWED_AGG_FUNCS:
                continue
            validated[field] = func_upper
        agg_funcs = validated

    # 构建 SELECT 子句
    select_parts: list[str] = [group_clause]
    # 始终追加 COUNT(*) AS count
    select_parts.append("COUNT(*) AS `count`")
    for field, func in agg_funcs.items():
        if field == "*":
            # COUNT(*) 已单独处理
            continue
        alias = f"{func.lower()}_{field}"
        select_parts.append(f"{func}(`{field}`) AS `{alias}`")
    select_clause = ", ".join(select_parts)

    # 构建 WHERE 子句
    where_clause, params = build_where(
        filters or {}, view, date_ranges, amount_ranges,
        null_fields=null_fields, not_null_fields=not_null_fields,
        prefix_filters=prefix_filters,
    )

    # 构建 ORDER BY 子句
    direction = "ASC" if str(order_direction).upper() == "ASC" else "DESC"
    valid_order_fields = {expr_alias, "count"}
    valid_order_fields.update(
        f"{func.lower()}_{field}"
        for field, func in agg_funcs.items()
        if field != "*"
    )
    # order_by 为空或非法值时，回退到默认 ORDER BY count DESC
    if order_by and order_by in valid_order_fields:
        order_clause = f" ORDER BY `{order_by}` {direction}"
    else:
        # 默认按 count DESC 排序（非法 order_by 也走此分支，防注入）
        order_clause = " ORDER BY `count` DESC"

    # 限制最大返回分组数
    limit = max(1, min(limit, 200))

    sql = (
        f"SELECT {select_clause} FROM `{view}` "
        f"WHERE 1=1{where_clause} "
        f"GROUP BY {group_by_sql}"
        f"{order_clause} LIMIT :limit"
    )
    params["limit"] = limit

    rows = await execute_query(sql, params, query_type="agg")
    return {
        "view": view,
        "group_by": group_label,
        "group_by_expr": group_by_expr if use_expr else None,
        "agg_funcs": agg_funcs,
        "count": len(rows),
        "data": rows,
    }


# 已注册的 dwd_* 视图名集合
VIEW_NAMES = frozenset(ALLOWED_FIELDS.keys())
