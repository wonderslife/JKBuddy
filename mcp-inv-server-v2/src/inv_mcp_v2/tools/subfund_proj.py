"""子基金底层投资项目查询工具 - 对应 dwd_subfund_proj 视图"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from .base import query_view, count_view


def register_subfund_proj_tools(mcp: FastMCP) -> None:
    """注册子基金底层项目相关工具"""

    @mcp.tool()
    async def query_subfund_proj(
        subfund_proj_id: str | None = None,
        subfund_id: str | None = None,
        subfund_name: str | None = None,
        subfund_proj_name: str | None = None,
        dept_id: str | None = None,
        company_name: str | None = None,
        is_null_fields: list[str] | None = None,
        is_not_null_fields: list[str] | None = None,
        subfund_name_prefix: str | None = None,
        subfund_proj_name_prefix: str | None = None,
        company_name_prefix: str | None = None,
        order_by: str | None = None,
        order_direction: str = "DESC",
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """查询子基金投资的底层项目信息。

        视图: dwd_subfund_proj
        可用过滤: subfund_proj_id, subfund_id, subfund_name(模糊), subfund_proj_name(模糊),
                  dept_id, company_name(模糊),
                  is_null_fields(IS NULL 过滤, 可选: time_value),
                  is_not_null_fields(IS NOT NULL 过滤, 可选: time_value),
                  subfund_name_prefix(子基金名称前缀匹配, LIKE 'xxx%'),
                  subfund_proj_name_prefix(底层项目名称前缀匹配, LIKE 'xxx%'),
                  company_name_prefix(公司名称前缀匹配, LIKE 'xxx%')
        可用排序字段: subfund_proj_id, subfund_id, subfund_name, subfund_proj_name, time_value

        Args:
            subfund_proj_id: 底层项目编号（精确）
            subfund_id: 所属子基金编号（精确）
            subfund_name: 所属子基金名称（模糊，LIKE '%xxx%'）
            subfund_proj_name: 底层项目名称（模糊，LIKE '%xxx%'）
            dept_id: 金控公司编号
            company_name: 金控公司名称（模糊，LIKE '%xxx%'）
            is_null_fields: 需要 IS NULL 过滤的字段列表。可选: time_value
            is_not_null_fields: 需要 IS NOT NULL 过滤的字段列表。可选: time_value
            subfund_name_prefix: 子基金名称前缀（如"某"匹配"某都市圈基金"，LIKE '某%'）
            subfund_proj_name_prefix: 底层项目名称前缀（如"嘉兴"匹配"嘉兴科技"，LIKE '嘉兴%'）
            company_name_prefix: 公司名称前缀（如"科技"匹配"某科技风投"开头，LIKE '科技%'）
            order_by: 排序字段（默认 time_value）。可选：subfund_id/subfund_proj_id/time_value 等
            order_direction: 排序方向，"ASC"（升序）/ "DESC"（降序，默认）
            limit: 返回行数（1-200）
            offset: 偏移量

        Returns:
            {total, limit, offset, data: [...]}

        Note:
            dwd_subfund_proj 视图实际无金额字段（仅 time_value 字符串字段），
            之前版本错误提供了 min/max_invest_amount 参数，已于 2026-07-31 移除
            （依据 verify_tool_fields.py 审计报告）。
        """
        # subfund_proj_name 已加入白名单（ALLOWED_FIELDS["dwd_subfund_proj"]）
        # 修复：之前的版本遗漏了 subfund_proj_name 字段，导致参数失效
        filters = {
            "subfund_proj_id": subfund_proj_id,
            "subfund_id": subfund_id,
            "subfund_name": subfund_name,
            "subfund_proj_name": subfund_proj_name,
            "dept_id": dept_id,
            "company_name": company_name,
        }
        prefix_filters: dict[str, str] = {}
        if subfund_name_prefix:
            prefix_filters["subfund_name"] = subfund_name_prefix
        if subfund_proj_name_prefix:
            prefix_filters["subfund_proj_name"] = subfund_proj_name_prefix
        if company_name_prefix:
            prefix_filters["company_name"] = company_name_prefix
        pf = prefix_filters or None
        final_order_by = order_by if order_by else "time_value"
        data = await query_view("dwd_subfund_proj", filters, limit, offset, order_by=final_order_by,
                                order_direction=order_direction,
                                null_fields=is_null_fields, not_null_fields=is_not_null_fields,
                                prefix_filters=pf)
        total = await count_view("dwd_subfund_proj", filters,
                                  null_fields=is_null_fields, not_null_fields=is_not_null_fields,
                                  prefix_filters=pf)
        return {"total": total, "limit": limit, "offset": offset, "data": data}
