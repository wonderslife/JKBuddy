"""子基金查询工具 - 对应 dwd_subfund 视图"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from .base import query_view, count_view


def register_subfund_tools(mcp: FastMCP) -> None:
    """注册子基金相关工具"""

    @mcp.tool()
    async def query_subfund(
        subfund_id: str | None = None,
        subfund_name: str | None = None,
        subfund_type: str | None = None,
        phase: str | None = None,
        dept_id: str | None = None,
        company_name: str | None = None,
        in_date_start: str | None = None,
        in_date_end: str | None = None,
        min_invest_amount: float | None = None,
        max_invest_amount: float | None = None,
        min_exit_amount: float | None = None,
        max_exit_amount: float | None = None,
        min_total_size: float | None = None,
        max_total_size: float | None = None,
        is_null_fields: list[str] | None = None,
        is_not_null_fields: list[str] | None = None,
        subfund_name_prefix: str | None = None,
        company_name_prefix: str | None = None,
        order_by: str | None = None,
        order_direction: str = "DESC",
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """查询子基金基本信息（规模、阶段、投资额、退出额）.

        视图: dwd_subfund
        单位: 金额均为万元
        可用过滤: subfund_id, subfund_name(模糊), subfund_type, phase(项目储备/项目推进中/投后管理/项目退出),
                  dept_id, company_name(模糊), in_date_start/in_date_end(入库日期范围),
                  min/max_invest_amount(投资金额范围),
                  min/max_exit_amount(退出金额范围),
                  min/max_total_size(基金总规模范围),
                  is_null_fields(IS NULL 过滤, 可选: invest_amount/exit_amount),
                  is_not_null_fields(IS NOT NULL 过滤, 同上),
                  subfund_name_prefix(子基金名称前缀匹配, LIKE 'xxx%'),
                  company_name_prefix(公司名称前缀匹配, LIKE 'xxx%')
        可用排序字段: subfund_id, subfund_name, subfund_type, phase, in_date,
                     invest_amount, exit_amount, total_size

        Args:
            subfund_id: 子基金编号（精确）
            subfund_name: 子基金名称（模糊，LIKE '%xxx%'）
            subfund_type: 子基金类型
            phase: 阶段中文值：项目储备 / 项目推进中 / 投后管理 / 项目退出
            dept_id: 金控公司编号
            company_name: 金控公司名称（模糊，LIKE '%xxx%'）
            in_date_start: 入库日期起始（YYYY-MM-DD，含）
            in_date_end: 入库日期结束（YYYY-MM-DD，含）
            min_invest_amount: 最小投资金额（万元，含）
            max_invest_amount: 最大投资金额（万元，含）
            min_exit_amount: 最小退出金额（万元，含）
            max_exit_amount: 最大退出金额（万元，含）
            min_total_size: 最小基金总规模（万元，含）
            max_total_size: 最大基金总规模（万元，含）
            is_null_fields: 需要 IS NULL 过滤的字段列表。可选: invest_amount, exit_amount
            is_not_null_fields: 需要 IS NOT NULL 过滤的字段列表。可选: invest_amount, exit_amount
            subfund_name_prefix: 子基金名称前缀（如"某"匹配"某都市圈基金"，LIKE '某%'）
            company_name_prefix: 公司名称前缀（如"科技"匹配"某科技风投"开头，LIKE '科技%'）
            order_by: 排序字段（默认 in_date）。可选：invest_amount/exit_amount/total_size/in_date 等
            order_direction: 排序方向，"ASC"（升序）/ "DESC"（降序，默认）
            limit: 返回行数（1-200）
            offset: 偏移量

        Returns:
            {total, limit, offset, data: [...]}
        """
        filters = {
            "subfund_id": subfund_id,
            "subfund_name": subfund_name,
            "subfund_type": subfund_type,
            "phase": phase,
            "dept_id": dept_id,
            "company_name": company_name,
        }
        prefix_filters: dict[str, str] = {}
        if subfund_name_prefix:
            prefix_filters["subfund_name"] = subfund_name_prefix
        if company_name_prefix:
            prefix_filters["company_name"] = company_name_prefix
        pf = prefix_filters or None
        date_ranges = {
            "in_date": (in_date_start, in_date_end),
        } if (in_date_start or in_date_end) else None
        amount_ranges: dict[str, tuple[float | None, float | None]] = {}
        if min_invest_amount is not None or max_invest_amount is not None:
            amount_ranges["invest_amount"] = (min_invest_amount, max_invest_amount)
        if min_exit_amount is not None or max_exit_amount is not None:
            amount_ranges["exit_amount"] = (min_exit_amount, max_exit_amount)
        if min_total_size is not None or max_total_size is not None:
            amount_ranges["total_size"] = (min_total_size, max_total_size)
        ar = amount_ranges or None
        final_order_by = order_by if order_by else "in_date"
        data = await query_view("dwd_subfund", filters, limit, offset, order_by=final_order_by,
                                date_ranges=date_ranges, amount_ranges=ar,
                                order_direction=order_direction,
                                null_fields=is_null_fields, not_null_fields=is_not_null_fields,
                                prefix_filters=pf)
        total = await count_view("dwd_subfund", filters, date_ranges=date_ranges, amount_ranges=ar,
                                  null_fields=is_null_fields, not_null_fields=is_not_null_fields,
                                  prefix_filters=pf)
        return {"total": total, "limit": limit, "offset": offset, "data": data}
