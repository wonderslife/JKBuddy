"""投资关系查询工具 - 对应 4 个 DWD 关系视图

依据 final-dwd-data-structure-design.md §5.5-5.8:
- dwd_lp2fund: LP 出资基金关系
- dwd_fund2subfund: 母基金投资子基金关系
- dwd_fund2proj: 基金投资项目关系
- dwd_subfund2proj: 子基金投资项目关系
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from .base import query_view, count_view


def register_relation_tools(mcp: FastMCP) -> None:
    """注册投资关系相关工具"""

    @mcp.tool()
    async def query_lp2fund(
        lp_id: str | None = None,
        lp_name: str | None = None,
        fund_id: str | None = None,
        fund_name: str | None = None,
        lp_type: str | None = None,
        cap_date_start: str | None = None,
        cap_date_end: str | None = None,
        flow_time_start: str | None = None,
        flow_time_end: str | None = None,
        min_committed_amt: float | None = None,
        max_committed_amt: float | None = None,
        is_null_fields: list[str] | None = None,
        is_not_null_fields: list[str] | None = None,
        lp_name_prefix: str | None = None,
        fund_name_prefix: str | None = None,
        order_by: str | None = None,
        order_direction: str = "DESC",
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """查询 LP 出资基金的关系及出资流水。

        视图: dwd_lp2fund
        单位: 金额均为万元
        关系语义: LP (投资人) → 基金 (被投资方)
        可用过滤: lp_id, lp_name(模糊), fund_id, fund_name(模糊), lp_type,
                  cap_date_start/cap_date_end(统计日期范围),
                  flow_time_start/flow_time_end(出资流水日期范围),
                  min/max_committed_amt(承诺出资金额范围),
                  is_null_fields(IS NULL 过滤, 可选: committed_amt/flow_amt/ownership_pct),
                  is_not_null_fields(IS NOT NULL 过滤, 同上),
                  lp_name_prefix(LP名称前缀匹配, LIKE 'xxx%'),
                  fund_name_prefix(基金名称前缀匹配, LIKE 'xxx%')
        可用排序字段: lp_id, lp_name, lp_type, fund_id, fund_name, cap_date, flow_time, committed_amt

        Args:
            lp_id: LP 投资人编号（精确）
            lp_name: LP 名称（模糊，LIKE '%xxx%'）
            fund_id: 基金编号（精确）
            fund_name: 基金名称（模糊，LIKE '%xxx%'）
            lp_type: LP 类型（FUND/IR_INVESTOR/FUND_MANAGER）
            cap_date_start: 统计日期起始（YYYY-MM-DD，含）
            cap_date_end: 统计日期结束（YYYY-MM-DD，含）
            flow_time_start: 出资流水日期起始（YYYY-MM-DD，含）
            flow_time_end: 出资流水日期结束（YYYY-MM-DD，含）
            min_committed_amt: 最小承诺出资金额（万元，含）
            max_committed_amt: 最大承诺出资金额（万元，含）
            is_null_fields: 需要 IS NULL 过滤的字段列表。可选: committed_amt, flow_amt, ownership_pct
            is_not_null_fields: 需要 IS NOT NULL 过滤的字段列表。可选: committed_amt, flow_amt, ownership_pct
            lp_name_prefix: LP 名称前缀（如"市"匹配"某市投资基金"，LIKE '市%'）
            fund_name_prefix: 基金名称前缀（如"某"匹配"某都市圈基金"，LIKE '某%'）
            order_by: 排序字段（默认 cap_date）。可选：committed_amt/cap_date/flow_time 等
            order_direction: 排序方向，"ASC"（升序，如查询承诺出资最小的 LP）/ "DESC"（降序，默认）
            limit: 返回行数（1-200）
            offset: 偏移量

        Returns:
            {total, limit, offset, data: [...]}
        """
        filters = {
            "lp_id": lp_id,
            "lp_name": lp_name,
            "fund_id": fund_id,
            "fund_name": fund_name,
            "lp_type": lp_type,
        }
        prefix_filters: dict[str, str] = {}
        if lp_name_prefix:
            prefix_filters["lp_name"] = lp_name_prefix
        if fund_name_prefix:
            prefix_filters["fund_name"] = fund_name_prefix
        pf = prefix_filters or None
        date_ranges: dict[str, tuple[str | None, str | None]] = {}
        if cap_date_start or cap_date_end:
            date_ranges["cap_date"] = (cap_date_start, cap_date_end)
        if flow_time_start or flow_time_end:
            date_ranges["flow_time"] = (flow_time_start, flow_time_end)
        dr = date_ranges or None
        amount_ranges: dict[str, tuple[float | None, float | None]] = {}
        if min_committed_amt is not None or max_committed_amt is not None:
            amount_ranges["committed_amt"] = (min_committed_amt, max_committed_amt)
        ar = amount_ranges or None
        final_order_by = order_by if order_by else "cap_date"
        data = await query_view("dwd_lp2fund", filters, limit, offset, order_by=final_order_by,
                                date_ranges=dr, amount_ranges=ar,
                                order_direction=order_direction,
                                null_fields=is_null_fields, not_null_fields=is_not_null_fields,
                                prefix_filters=pf)
        total = await count_view("dwd_lp2fund", filters, date_ranges=dr, amount_ranges=ar,
                                  null_fields=is_null_fields, not_null_fields=is_not_null_fields,
                                  prefix_filters=pf)
        return {"total": total, "limit": limit, "offset": offset, "data": data}

    @mcp.tool()
    async def query_fund2subfund(
        fund_id: str | None = None,
        fund_name: str | None = None,
        subfund_id: str | None = None,
        subfund_name: str | None = None,
        cap_date_start: str | None = None,
        cap_date_end: str | None = None,
        flow_time_start: str | None = None,
        flow_time_end: str | None = None,
        min_committed_amt: float | None = None,
        max_committed_amt: float | None = None,
        is_null_fields: list[str] | None = None,
        is_not_null_fields: list[str] | None = None,
        fund_name_prefix: str | None = None,
        subfund_name_prefix: str | None = None,
        order_by: str | None = None,
        order_direction: str = "DESC",
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """查询母基金投资子基金的关系及出资流水。

        视图: dwd_fund2subfund
        单位: 金额均为万元
        关系语义: 母基金 (investor) → 子基金 (investee)
        可用过滤: fund_id, fund_name(模糊), subfund_id, subfund_name(模糊),
                  cap_date_start/cap_date_end(统计日期范围),
                  flow_time_start/flow_time_end(出资流水日期范围),
                  min/max_committed_amt(承诺出资金额范围),
                  is_null_fields(IS NULL 过滤, 可选: committed_amt/flow_amt/ownership_pct),
                  is_not_null_fields(IS NOT NULL 过滤, 同上),
                  fund_name_prefix(母基金名称前缀匹配, LIKE 'xxx%'),
                  subfund_name_prefix(子基金名称前缀匹配, LIKE 'xxx%')
        可用排序字段: fund_id, fund_name, subfund_id, subfund_name, cap_date, flow_time, committed_amt

        Args:
            fund_id: 母基金编号（精确）
            fund_name: 母基金名称（模糊，LIKE '%xxx%'）
            subfund_id: 子基金编号（精确）
            subfund_name: 子基金名称（模糊，LIKE '%xxx%'）
            cap_date_start: 统计日期起始（YYYY-MM-DD，含）
            cap_date_end: 统计日期结束（YYYY-MM-DD，含）
            flow_time_start: 出资流水日期起始（YYYY-MM-DD，含）
            flow_time_end: 出资流水日期结束（YYYY-MM-DD，含）
            min_committed_amt: 最小承诺出资金额（万元，含）
            max_committed_amt: 最大承诺出资金额（万元，含）
            is_null_fields: 需要 IS NULL 过滤的字段列表。可选: committed_amt, flow_amt, ownership_pct
            is_not_null_fields: 需要 IS NOT NULL 过滤的字段列表。可选: committed_amt, flow_amt, ownership_pct
            fund_name_prefix: 母基金名称前缀（如"某"匹配"某都市圈基金"，LIKE '某%'）
            subfund_name_prefix: 子基金名称前缀（如"某"匹配"某天使基金"，LIKE '某%'）
            order_by: 排序字段（默认 cap_date）。可选：committed_amt/cap_date/flow_time 等
            order_direction: 排序方向，"ASC"（升序，如查询承诺出资最小的关系）/ "DESC"（降序，默认）
            limit: 返回行数（1-200）
            offset: 偏移量

        Returns:
            {total, limit, offset, data: [...]}
        """
        filters = {
            "fund_id": fund_id,
            "fund_name": fund_name,
            "subfund_id": subfund_id,
            "subfund_name": subfund_name,
        }
        prefix_filters: dict[str, str] = {}
        if fund_name_prefix:
            prefix_filters["fund_name"] = fund_name_prefix
        if subfund_name_prefix:
            prefix_filters["subfund_name"] = subfund_name_prefix
        pf = prefix_filters or None
        date_ranges: dict[str, tuple[str | None, str | None]] = {}
        if cap_date_start or cap_date_end:
            date_ranges["cap_date"] = (cap_date_start, cap_date_end)
        if flow_time_start or flow_time_end:
            date_ranges["flow_time"] = (flow_time_start, flow_time_end)
        dr = date_ranges or None
        amount_ranges: dict[str, tuple[float | None, float | None]] = {}
        if min_committed_amt is not None or max_committed_amt is not None:
            amount_ranges["committed_amt"] = (min_committed_amt, max_committed_amt)
        ar = amount_ranges or None
        final_order_by = order_by if order_by else "cap_date"
        data = await query_view("dwd_fund2subfund", filters, limit, offset, order_by=final_order_by,
                                date_ranges=dr, amount_ranges=ar,
                                order_direction=order_direction,
                                null_fields=is_null_fields, not_null_fields=is_not_null_fields,
                                prefix_filters=pf)
        total = await count_view("dwd_fund2subfund", filters, date_ranges=dr, amount_ranges=ar,
                                  null_fields=is_null_fields, not_null_fields=is_not_null_fields,
                                  prefix_filters=pf)
        return {"total": total, "limit": limit, "offset": offset, "data": data}

    @mcp.tool()
    async def query_fund2proj(
        fund_id: str | None = None,
        fund_name: str | None = None,
        proj_id: str | None = None,
        proj_name: str | None = None,
        biz_line: str | None = None,
        cap_date_start: str | None = None,
        cap_date_end: str | None = None,
        flow_time_start: str | None = None,
        flow_time_end: str | None = None,
        min_committed_amt: float | None = None,
        max_committed_amt: float | None = None,
        is_null_fields: list[str] | None = None,
        is_not_null_fields: list[str] | None = None,
        fund_name_prefix: str | None = None,
        proj_name_prefix: str | None = None,
        order_by: str | None = None,
        order_direction: str = "DESC",
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """查询基金直接投资项目的出资流水及股权比例。

        视图: dwd_fund2proj
        单位: 金额均为万元
        关系语义: 基金 (investor) → 直投项目 (investee)
        可用过滤: fund_id, fund_name(模糊), proj_id, proj_name(模糊), biz_line,
                  cap_date_start/cap_date_end(统计日期范围),
                  flow_time_start/flow_time_end(出资流水日期范围),
                  min/max_committed_amt(承诺出资金额范围),
                  is_null_fields(IS NULL 过滤, 可选: committed_amt/flow_amt/ownership_pct),
                  is_not_null_fields(IS NOT NULL 过滤, 同上),
                  fund_name_prefix(基金名称前缀匹配, LIKE 'xxx%'),
                  proj_name_prefix(项目名称前缀匹配, LIKE 'xxx%')
        可用排序字段: fund_id, fund_name, proj_id, proj_name, biz_line, cap_date, flow_time, committed_amt

        Args:
            fund_id: 基金编号（精确）
            fund_name: 基金名称（模糊，LIKE '%xxx%'）
            proj_id: 项目编号（精确）
            proj_name: 项目名称（模糊，LIKE '%xxx%'）
            biz_line: 业务线代码（stock/debt/rzzl/bl/elo/egl）
            cap_date_start: 统计日期起始（YYYY-MM-DD，含）
            cap_date_end: 统计日期结束（YYYY-MM-DD，含）
            flow_time_start: 出资流水日期起始（YYYY-MM-DD，含）
            flow_time_end: 出资流水日期结束（YYYY-MM-DD，含）
            min_committed_amt: 最小承诺出资金额（万元，含）
            max_committed_amt: 最大承诺出资金额（万元，含）
            is_null_fields: 需要 IS NULL 过滤的字段列表。可选: committed_amt, flow_amt, ownership_pct
            is_not_null_fields: 需要 IS NOT NULL 过滤的字段列表。可选: committed_amt, flow_amt, ownership_pct
            fund_name_prefix: 基金名称前缀（如"某"匹配"某都市圈基金"，LIKE '某%'）
            proj_name_prefix: 项目名称前缀（如"嘉兴"匹配"嘉兴科技"，LIKE '嘉兴%'）
            order_by: 排序字段（默认 cap_date）。可选：committed_amt/cap_date/flow_time 等
            order_direction: 排序方向，"ASC"（升序，如查询承诺出资最小的关系）/ "DESC"（降序，默认）
            limit: 返回行数（1-200）
            offset: 偏移量

        Returns:
            {total, limit, offset, data: [...]}
        """
        filters = {
            "fund_id": fund_id,
            "fund_name": fund_name,
            "proj_id": proj_id,
            "proj_name": proj_name,
            "biz_line": biz_line,
        }
        prefix_filters: dict[str, str] = {}
        if fund_name_prefix:
            prefix_filters["fund_name"] = fund_name_prefix
        if proj_name_prefix:
            prefix_filters["proj_name"] = proj_name_prefix
        pf = prefix_filters or None
        date_ranges: dict[str, tuple[str | None, str | None]] = {}
        if cap_date_start or cap_date_end:
            date_ranges["cap_date"] = (cap_date_start, cap_date_end)
        if flow_time_start or flow_time_end:
            date_ranges["flow_time"] = (flow_time_start, flow_time_end)
        dr = date_ranges or None
        amount_ranges: dict[str, tuple[float | None, float | None]] = {}
        if min_committed_amt is not None or max_committed_amt is not None:
            amount_ranges["committed_amt"] = (min_committed_amt, max_committed_amt)
        ar = amount_ranges or None
        final_order_by = order_by if order_by else "cap_date"
        data = await query_view("dwd_fund2proj", filters, limit, offset, order_by=final_order_by,
                                date_ranges=dr, amount_ranges=ar,
                                order_direction=order_direction,
                                null_fields=is_null_fields, not_null_fields=is_not_null_fields,
                                prefix_filters=pf)
        total = await count_view("dwd_fund2proj", filters, date_ranges=dr, amount_ranges=ar,
                                  null_fields=is_null_fields, not_null_fields=is_not_null_fields,
                                  prefix_filters=pf)
        return {"total": total, "limit": limit, "offset": offset, "data": data}

    @mcp.tool()
    async def query_subfund2proj(
        subfund_id: str | None = None,
        subfund_name: str | None = None,
        subfund_proj_id: str | None = None,
        subfund_proj_name: str | None = None,
        cap_date_start: str | None = None,
        cap_date_end: str | None = None,
        flow_time_start: str | None = None,
        flow_time_end: str | None = None,
        min_committed_amt: float | None = None,
        max_committed_amt: float | None = None,
        is_null_fields: list[str] | None = None,
        is_not_null_fields: list[str] | None = None,
        subfund_name_prefix: str | None = None,
        subfund_proj_name_prefix: str | None = None,
        order_by: str | None = None,
        order_direction: str = "DESC",
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """查询子基金投资底层项目的出资流水及股权比例。

        视图: dwd_subfund2proj
        单位: 金额均为万元
        关系语义: 子基金 (investor) → 子基金底层项目 (investee)
        可用过滤: subfund_id, subfund_name(模糊), subfund_proj_id, subfund_proj_name(模糊),
                  cap_date_start/cap_date_end(统计日期范围),
                  flow_time_start/flow_time_end(出资流水日期范围),
                  min/max_committed_amt(承诺出资金额范围),
                  is_null_fields(IS NULL 过滤, 可选: committed_amt/flow_amt/ownership_pct),
                  is_not_null_fields(IS NOT NULL 过滤, 同上),
                  subfund_name_prefix(子基金名称前缀匹配, LIKE 'xxx%'),
                  subfund_proj_name_prefix(底层项目名称前缀匹配, LIKE 'xxx%')
        可用排序字段: subfund_id, subfund_name, subfund_proj_id, subfund_proj_name, cap_date, flow_time, committed_amt

        注意: dwd_subfund2proj 视图中没有 biz_line 字段（与 dwd_fund2proj 不同）。

        Args:
            subfund_id: 子基金编号（精确）
            subfund_name: 子基金名称（模糊，LIKE '%xxx%'）
            subfund_proj_id: 子基金底层项目编号（精确）
            subfund_proj_name: 子基金底层项目名称（模糊，LIKE '%xxx%'）
            cap_date_start: 统计日期起始（YYYY-MM-DD，含）
            cap_date_end: 统计日期结束（YYYY-MM-DD，含）
            flow_time_start: 出资流水日期起始（YYYY-MM-DD，含）
            flow_time_end: 出资流水日期结束（YYYY-MM-DD，含）
            min_committed_amt: 最小承诺出资金额（万元，含）
            max_committed_amt: 最大承诺出资金额（万元，含）
            is_null_fields: 需要 IS NULL 过滤的字段列表。可选: committed_amt, flow_amt, ownership_pct
            is_not_null_fields: 需要 IS NOT NULL 过滤的字段列表。可选: committed_amt, flow_amt, ownership_pct
            subfund_name_prefix: 子基金名称前缀（如"某"匹配"某都市圈基金"，LIKE '某%'）
            subfund_proj_name_prefix: 底层项目名称前缀（如"嘉兴"匹配"嘉兴科技"，LIKE '嘉兴%'）
            order_by: 排序字段（默认 cap_date）。可选：committed_amt/cap_date/flow_time 等
            order_direction: 排序方向，"ASC"（升序，如查询承诺出资最小的关系）/ "DESC"（降序，默认）
            limit: 返回行数（1-200）
            offset: 偏移量

        Returns:
            {total, limit, offset, data: [...]}
        """
        filters = {
            "subfund_id": subfund_id,
            "subfund_name": subfund_name,
            "subfund_proj_id": subfund_proj_id,
            "subfund_proj_name": subfund_proj_name,
        }
        prefix_filters: dict[str, str] = {}
        if subfund_name_prefix:
            prefix_filters["subfund_name"] = subfund_name_prefix
        if subfund_proj_name_prefix:
            prefix_filters["subfund_proj_name"] = subfund_proj_name_prefix
        pf = prefix_filters or None
        date_ranges: dict[str, tuple[str | None, str | None]] = {}
        if cap_date_start or cap_date_end:
            date_ranges["cap_date"] = (cap_date_start, cap_date_end)
        if flow_time_start or flow_time_end:
            date_ranges["flow_time"] = (flow_time_start, flow_time_end)
        dr = date_ranges or None
        amount_ranges: dict[str, tuple[float | None, float | None]] = {}
        if min_committed_amt is not None or max_committed_amt is not None:
            amount_ranges["committed_amt"] = (min_committed_amt, max_committed_amt)
        ar = amount_ranges or None
        final_order_by = order_by if order_by else "cap_date"
        data = await query_view("dwd_subfund2proj", filters, limit, offset, order_by=final_order_by,
                                date_ranges=dr, amount_ranges=ar,
                                order_direction=order_direction,
                                null_fields=is_null_fields, not_null_fields=is_not_null_fields,
                                prefix_filters=pf)
        total = await count_view("dwd_subfund2proj", filters, date_ranges=dr, amount_ranges=ar,
                                  null_fields=is_null_fields, not_null_fields=is_not_null_fields,
                                  prefix_filters=pf)
        return {"total": total, "limit": limit, "offset": offset, "data": data}
