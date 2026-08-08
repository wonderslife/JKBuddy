"""基金查询工具 - 对应 dwd_fund 视图"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from .base import query_view, count_view


def register_fund_tools(mcp: FastMCP) -> None:
    """注册基金相关工具"""

    @mcp.tool()
    async def query_fund(
        fund_id: str | None = None,
        fund_name: str | None = None,
        fund_type: str | None = None,
        fund_phase: str | None = None,
        dept_id: str | None = None,
        company_name: str | None = None,
        cap_date_start: str | None = None,
        cap_date_end: str | None = None,
        min_invest_amount: float | None = None,
        max_invest_amount: float | None = None,
        min_exit_amount: float | None = None,
        max_exit_amount: float | None = None,
        min_subscribed_amt: float | None = None,
        max_subscribed_amt: float | None = None,
        min_total_size: float | None = None,
        max_total_size: float | None = None,
        is_null_fields: list[str] | None = None,
        is_not_null_fields: list[str] | None = None,
        fund_name_prefix: str | None = None,
        company_name_prefix: str | None = None,
        order_by: str | None = None,
        order_direction: str = "DESC",
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """查询基金基本信息（规模、阶段、投资额、退出额）.

        视图: dwd_fund
        单位: 金额均为万元
        可用过滤: fund_id, fund_name(模糊), fund_type(自管基金/自有资金),
                  fund_phase(筹备/募集/投资/退出), dept_id, company_name(模糊),
                  cap_date_start/cap_date_end(统计日期范围),
                  min/max_invest_amount(投资金额范围),
                  min/max_exit_amount(退出金额范围),
                  min/max_subscribed_amt(认缴金额范围),
                  min/max_total_size(基金总规模范围),
                  is_null_fields(IS NULL 过滤, 可选: cap_date/invest_amount/exit_amount),
                  is_not_null_fields(IS NOT NULL 过滤, 同上),
                  fund_name_prefix(基金名称前缀匹配, LIKE 'xxx%'),
                  company_name_prefix(公司名称前缀匹配, LIKE 'xxx%')
        可用排序字段: fund_id, fund_name, fund_type, fund_phase, cap_date,
                     invest_amount, exit_amount, subscribed_amt, total_size

        Args:
            fund_id: 基金编号（精确匹配）
            fund_name: 基金名称（模糊匹配，LIKE '%xxx%'）
            fund_type: 基金类型中文值：自管基金 / 自有资金
            fund_phase: 基金阶段中文值：筹备 / 募集 / 投资 / 退出
            dept_id: 金控公司编号
            company_name: 金控公司名称（模糊匹配，LIKE '%xxx%'）
            cap_date_start: 统计日期起始（YYYY-MM-DD，含）
            cap_date_end: 统计日期结束（YYYY-MM-DD，含）
            min_invest_amount: 最小投资金额（万元，含）
            max_invest_amount: 最大投资金额（万元，含）
            min_exit_amount: 最小退出金额（万元，含）
            max_exit_amount: 最大退出金额（万元，含）
            min_subscribed_amt: 最小认缴金额（万元，含）
            max_subscribed_amt: 最大认缴金额（万元，含）
            min_total_size: 最小基金总规模（万元，含）
            max_total_size: 最大基金总规模（万元，含）
            is_null_fields: 需要 IS NULL 过滤的字段列表。可选: cap_date, invest_amount, exit_amount
            is_not_null_fields: 需要 IS NOT NULL 过滤的字段列表。可选: cap_date, invest_amount, exit_amount
            fund_name_prefix: 基金名称前缀（如"某"匹配"某都市圈基金"，LIKE '某%'）
            company_name_prefix: 公司名称前缀（如"科技"匹配"某科技风投"开头，LIKE '科技%'）
            order_by: 排序字段（默认 cap_date）。可选：invest_amount/exit_amount/total_size/subscribed_amt/cap_date 等
            order_direction: 排序方向，"ASC"（升序，如查询最小金额的项目）/ "DESC"（降序，默认）
            limit: 返回行数（1-200，默认20）
            offset: 偏移量（分页用）

        Returns:
            {total, limit, offset, data: [...]}
        """
        filters = {
            "fund_id": fund_id,
            "fund_name": fund_name,
            "fund_type": fund_type,
            "fund_phase": fund_phase,
            "dept_id": dept_id,
            "company_name": company_name,
        }
        prefix_filters: dict[str, str] = {}
        if fund_name_prefix:
            prefix_filters["fund_name"] = fund_name_prefix
        if company_name_prefix:
            prefix_filters["company_name"] = company_name_prefix
        pf = prefix_filters or None
        date_ranges = {
            "cap_date": (cap_date_start, cap_date_end),
        } if (cap_date_start or cap_date_end) else None
        amount_ranges: dict[str, tuple[float | None, float | None]] = {}
        if min_invest_amount is not None or max_invest_amount is not None:
            amount_ranges["invest_amount"] = (min_invest_amount, max_invest_amount)
        if min_exit_amount is not None or max_exit_amount is not None:
            amount_ranges["exit_amount"] = (min_exit_amount, max_exit_amount)
        if min_subscribed_amt is not None or max_subscribed_amt is not None:
            amount_ranges["subscribed_amt"] = (min_subscribed_amt, max_subscribed_amt)
        if min_total_size is not None or max_total_size is not None:
            amount_ranges["total_size"] = (min_total_size, max_total_size)
        ar = amount_ranges or None
        # 默认按 cap_date 排序，若用户指定 order_by 则使用用户值（白名单校验在 query_view 内）
        final_order_by = order_by if order_by else "cap_date"
        data = await query_view("dwd_fund", filters, limit, offset, order_by=final_order_by,
                                date_ranges=date_ranges, amount_ranges=ar,
                                order_direction=order_direction,
                                null_fields=is_null_fields, not_null_fields=is_not_null_fields,
                                prefix_filters=pf)
        total = await count_view("dwd_fund", filters, date_ranges=date_ranges, amount_ranges=ar,
                                  null_fields=is_null_fields, not_null_fields=is_not_null_fields,
                                  prefix_filters=pf)
        return {"total": total, "limit": limit, "offset": offset, "data": data}
