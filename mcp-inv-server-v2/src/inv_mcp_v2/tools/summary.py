"""跨业务域汇总工具 - 对应 dwd_all_biz 视图

⚠️ 依据 Gemma4_DWD_Design_Doc_v2.md §三 工具约束矩阵:
仅用于全集团跨域宏观数据统计，禁止用于查询特定项目或基金列表。
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from .base import (
    query_view,
    count_view,
    stat_group_by,
    GROUP_BY_FIELDS,
    AGG_FIELDS,
)
from ..db import execute_query


def register_summary_tools(mcp: FastMCP) -> None:
    """注册汇总统计相关工具"""

    @mcp.tool()
    async def query_all_biz(
        biz_type: str | None = None,
        investor_name: str | None = None,
        investee_name: str | None = None,
        company_name: str | None = None,
        biz_line: str | None = None,
        flow_time_start: str | None = None,
        flow_time_end: str | None = None,
        min_committed_amt: float | None = None,
        max_committed_amt: float | None = None,
        min_flow_amt: float | None = None,
        max_flow_amt: float | None = None,
        is_null_fields: list[str] | None = None,
        is_not_null_fields: list[str] | None = None,
        investor_name_prefix: str | None = None,
        investee_name_prefix: str | None = None,
        company_name_prefix: str | None = None,
        order_by: str | None = None,
        order_direction: str = "DESC",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """查询跨业务域投资总揽数据（仅用于宏观统计）。

        ⚠️ 本工具仅用于全集团跨域宏观数据统计。禁止用于查询特定项目或基金列表！
        如需查询具体项目，请使用 query_project / query_fund2proj 等专用工具。

        视图: dwd_all_biz
        单位: 金额均为万元
        可用过滤: biz_type, investor_name(模糊), investee_name(模糊), company_name(模糊,
                 该投资所负责的金控内部公司), biz_line,
                 flow_time_start/flow_time_end(出资流水日期范围),
                 min/max_committed_amt(承诺出资金额范围),
                 min/max_flow_amt(实际出资金额范围),
                 is_null_fields(IS NULL 过滤, 可选: committed_amt/flow_amt),
                 is_not_null_fields(IS NOT NULL 过滤, 同上),
                 investor_name_prefix(投资方名称前缀匹配, LIKE 'xxx%'),
                 investee_name_prefix(被投资方名称前缀匹配, LIKE 'xxx%'),
                 company_name_prefix(金控公司名前缀匹配, LIKE 'xxx%')
        可用排序字段: biz_type, investor_id, investor_name, investee_id, investee_name,
                     biz_line, flow_time, committed_amt, flow_amt

        Args:
            biz_type: 业务类型英文代码：FUND2PROJ(基金投项目) / SUBFUND2PROJ(子基金投资项目) / FUND2SUBFUND(母基金投子基金) / LP2FUND(LP出资基金)
            investor_name: 投资方名称（模糊，LIKE '%xxx%'）
            investee_name: 被投资方名称（模糊，LIKE '%xxx%'）
            biz_line: 业务线（注意：FUND2SUBFUND 类型为 'FUND'，LP2FUND 类型为 'LP'，
                      FUND2PROJ 类型为项目的 biz_line 中文值，SUBFUND2PROJ 类型为 NULL）
            flow_time_start: 出资流水日期起始（YYYY-MM-DD，含）
            flow_time_end: 出资流水日期结束（YYYY-MM-DD，含）
            min_committed_amt: 最小承诺出资金额（万元，含）
            max_committed_amt: 最大承诺出资金额（万元，含）
            min_flow_amt: 最小实际出资金额（万元，含）
            max_flow_amt: 最大实际出资金额（万元，含）
            is_null_fields: 需要 IS NULL 过滤的字段列表。可选: committed_amt, flow_amt
            is_not_null_fields: 需要 IS NOT NULL 过滤的字段列表。可选: committed_amt, flow_amt
            investor_name_prefix: 投资方名称前缀（如"市"匹配"某市投资基金"，LIKE '市%'）
            investee_name_prefix: 被投资方名称前缀（如"嘉兴"匹配"嘉兴科技"，LIKE '嘉兴%'）
            order_by: 排序字段（默认 flow_time）。可选：committed_amt/flow_amt/flow_time 等
            order_direction: 排序方向，"ASC"（升序，如查询承诺出资最小的关系）/ "DESC"（降序，默认）
            limit: 返回行数（1-200，默认50）
            offset: 偏移量

        Returns:
            {total, limit, offset, data: [...]}
        """
        filters = {
            "biz_type": biz_type,
            "investor_name": investor_name,
            "investee_name": investee_name,
            "company_name": company_name,
            "biz_line": biz_line,
        }
        prefix_filters: dict[str, str] = {}
        if investor_name_prefix:
            prefix_filters["investor_name"] = investor_name_prefix
        if investee_name_prefix:
            prefix_filters["investee_name"] = investee_name_prefix
        if company_name_prefix:
            prefix_filters["company_name"] = company_name_prefix
        pf = prefix_filters or None
        date_ranges = {
            "flow_time": (flow_time_start, flow_time_end),
        } if (flow_time_start or flow_time_end) else None
        amount_ranges: dict[str, tuple[float | None, float | None]] = {}
        if min_committed_amt is not None or max_committed_amt is not None:
            amount_ranges["committed_amt"] = (min_committed_amt, max_committed_amt)
        if min_flow_amt is not None or max_flow_amt is not None:
            amount_ranges["flow_amt"] = (min_flow_amt, max_flow_amt)
        ar = amount_ranges or None
        final_order_by = order_by if order_by else "flow_time"
        data = await query_view("dwd_all_biz", filters, limit, offset, order_by=final_order_by,
                                date_ranges=date_ranges, amount_ranges=ar,
                                order_direction=order_direction,
                                null_fields=is_null_fields, not_null_fields=is_not_null_fields,
                                prefix_filters=pf)
        total = await count_view("dwd_all_biz", filters, date_ranges=date_ranges, amount_ranges=ar,
                                  null_fields=is_null_fields, not_null_fields=is_not_null_fields,
                                  prefix_filters=pf)
        return {"total": total, "limit": limit, "offset": offset, "data": data}

    @mcp.tool()
    async def stat_investment_summary(
        biz_type: str | None = None,
        biz_line: str | None = None,
    ) -> dict[str, Any]:
        """统计投资汇总数据（按业务类型/业务线分组）。

        ⚠️ 不同 biz_line 的 invest_amount 语义不同，本工具按 biz_line 分组统计，不会跨业务线加总。

        Args:
            biz_type: 业务类型英文代码：FUND2PROJ / SUBFUND2PROJ / FUND2SUBFUND / LP2FUND
            biz_line: 业务线

        Returns:
            {summary: [{biz_line, committed_total, flow_total, count}], total_count}
        """
        where_parts: list[str] = []
        params: dict[str, Any] = {}
        if biz_type:
            where_parts.append("biz_type = :biz_type")
            params["biz_type"] = biz_type
        if biz_line:
            where_parts.append("biz_line = :biz_line")
            params["biz_line"] = biz_line

        where_clause = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

        sql = f"""
        SELECT
            biz_line,
            COUNT(*) AS cnt,
            COALESCE(SUM(committed_amt), 0) AS committed_total,
            COALESCE(SUM(flow_amt), 0) AS flow_total
        FROM dwd_all_biz{where_clause}
        GROUP BY biz_line
        ORDER BY committed_total DESC
        """
        rows = await execute_query(sql, params, query_type="agg")
        total_count = sum(int(r["cnt"]) for r in rows)
        return {
            "summary": [
                {
                    "biz_line": r["biz_line"],
                    "count": int(r["cnt"]),
                    "committed_total": float(r["committed_total"]),
                    "flow_total": float(r["flow_total"]),
                }
                for r in rows
            ],
            "total_count": total_count,
        }

    @mcp.tool()
    async def stat_group_by_tool(
        view: str,
        group_by: str | None = None,
        group_by_expr: str | None = None,
        agg_func: str = "SUM",
        agg_field: str | None = None,
        biz_line: str | None = None,
        biz_type: str | None = None,
        fund_type: str | None = None,
        fund_phase: str | None = None,
        phase: str | None = None,
        lp_type: str | None = None,
        subfund_type: str | None = None,
        company_name: str | None = None,
        investor_name: str | None = None,
        investee_name: str | None = None,
        dept_id: str | None = None,
        cap_date_start: str | None = None,
        cap_date_end: str | None = None,
        flow_time_start: str | None = None,
        flow_time_end: str | None = None,
        in_date_start: str | None = None,
        in_date_end: str | None = None,
        is_null_fields: list[str] | None = None,
        is_not_null_fields: list[str] | None = None,
        fund_name_prefix: str | None = None,
        subfund_name_prefix: str | None = None,
        subfund_proj_name_prefix: str | None = None,
        proj_name_prefix: str | None = None,
        lp_name_prefix: str | None = None,
        company_name_prefix: str | None = None,
        investor_name_prefix: str | None = None,
        investee_name_prefix: str | None = None,
        order_by: str | None = None,
        order_direction: str = "DESC",
        limit: int = 50,
    ) -> dict[str, Any]:
        """按指定字段或表达式分组统计（GROUP BY + 聚合）。

        ⚠️ 仅支持白名单字段/表达式分组；聚合字段自动选取该视图的金额字段。
        ⚠️ 对于 dwd_project 视图，biz_line 为必填（防止跨业务域误聚合）。
        ⚠️ group_by 与 group_by_expr 二选一，优先使用 group_by_expr。

        分组方式一：按字段分组（group_by）
            各视图可用字段:
                dwd_fund:           fund_type, fund_phase, company_name, dept_id
                dwd_subfund:        subfund_type, phase, company_name, dept_id
                dwd_project:        biz_line, phase, company_name, dept_id, deal_stage
                dwd_subfund_proj:   subfund_id, subfund_name, company_name, dept_id
                dwd_lp2fund:        lp_type, fund_id, fund_name, lp_id, lp_name
                dwd_fund2subfund:   fund_id, fund_name, subfund_id, subfund_name
                dwd_fund2proj:      fund_id, fund_name, proj_id, proj_name, biz_line
                dwd_subfund2proj:   subfund_id, subfund_name, subfund_proj_id, subfund_proj_name
                dwd_all_biz:        biz_type, biz_line, investor_name, investee_name, company_name

        分组方式二：按表达式分组（group_by_expr）
            各视图可用表达式:
                dwd_fund:           YEAR(cap_date), MONTH(cap_date)
                dwd_subfund:        YEAR(in_date), MONTH(in_date)
                dwd_project:        YEAR(in_date), MONTH(in_date)
                dwd_subfund_proj:   YEAR(time_value), MONTH(time_value)
                dwd_lp2fund:        YEAR(cap_date), YEAR(flow_time)
                dwd_fund2subfund:   YEAR(cap_date), YEAR(flow_time)
                dwd_fund2proj:      YEAR(cap_date), YEAR(flow_time)
                dwd_subfund2proj:   YEAR(cap_date), YEAR(flow_time)
                dwd_all_biz:        YEAR(flow_time), MONTH(flow_time)

        聚合字段别名规则: {func_lower}_{field}（如 sum_invest_amount、avg_total_size），
        并始终返回 count 字段表示该分组下的记录数。
        表达式分组的结果中，分组字段别名为表达式的小写形式（如 year_cap_date、month_in_date）。

        Args:
            view: 视图名（dwd_fund/dwd_subfund/dwd_project/dwd_subfund_proj/dwd_lp2fund/
                  dwd_fund2subfund/dwd_fund2proj/dwd_subfund2proj/dwd_all_biz）
            group_by: 分组字段（必须在白名单中，与 group_by_expr 二选一）
            group_by_expr: 分组表达式（必须在白名单中，与 group_by 二选一，优先使用）
                支持的表达式：YEAR(cap_date), MONTH(cap_date), YEAR(in_date), YEAR(flow_time) 等
            agg_func: 聚合函数，可选 SUM（默认）/AVG/MIN/MAX/COUNT
            agg_field: 聚合字段。None=对该视图所有金额字段做 agg_func。
                       指定时仅对该字段聚合。COUNT 时可传 "*" 表示 COUNT(*)。
            biz_line: 业务线过滤（dwd_project 必填；dwd_fund2proj/dwd_all_biz 可选）
                      dwd_project 中文值: 股权项目/委托贷款/融资租赁/商业保理/应急转贷/助保贷
                      dwd_fund2proj 英文代码: stock/debt/rzzl/bl/elo/egl
            biz_type: 业务类型过滤（仅 dwd_all_biz）
                      FUND2PROJ / SUBFUND2PROJ / FUND2SUBFUND / LP2FUND
            fund_type: 基金类型过滤（仅 dwd_fund）：自管基金 / 自有资金
            fund_phase: 基金阶段过滤（仅 dwd_fund）：筹备 / 募集 / 投资 / 退出
            phase: 阶段过滤（dwd_subfund/dwd_project）
                   dwd_subfund: 项目储备/项目推进中/投后管理/项目退出
                   dwd_project: 项目储备/项目推进中/投后管理/项目退出
            lp_type: LP 类型过滤（仅 dwd_lp2fund）：FUND / IR_INVESTOR / FUND_MANAGER
            subfund_type: 子基金类型过滤（仅 dwd_subfund）
            company_name: 金控公司名称过滤（模糊匹配，多个视图可用）
            investor_name: 投资方名称过滤（仅 dwd_all_biz，模糊）
            investee_name: 被投资方名称过滤（仅 dwd_all_biz，模糊）
            dept_id: 金控公司编号过滤（精确）
            cap_date_start: 统计日期起始（YYYY-MM-DD，含）
            cap_date_end: 统计日期结束（YYYY-MM-DD，含）
            flow_time_start: 出资流水日期起始（YYYY-MM-DD，含）
            flow_time_end: 出资流水日期结束（YYYY-MM-DD，含）
            in_date_start: 入库日期起始（YYYY-MM-DD，含，dwd_subfund/dwd_project）
            in_date_end: 入库日期结束（YYYY-MM-DD，含，dwd_subfund/dwd_project）
            is_null_fields: 需要 IS NULL 过滤的字段列表。各视图可用字段:
                dwd_fund: cap_date, invest_amount, exit_amount
                dwd_subfund: invest_amount, exit_amount
                dwd_project: invest_amount, exit_amount
                dwd_subfund_proj: time_value
                dwd_lp2fund/dwd_fund2subfund/dwd_fund2proj/dwd_subfund2proj: committed_amt, flow_amt, ownership_pct
                dwd_all_biz: committed_amt, flow_amt
            is_not_null_fields: 需要 IS NOT NULL 过滤的字段列表（同上）
            fund_name_prefix: 基金名称前缀匹配（仅 dwd_fund/dwd_lp2fund/dwd_fund2subfund/dwd_fund2proj 可用，LIKE 'xxx%'）
            subfund_name_prefix: 子基金名称前缀匹配（仅 dwd_subfund/dwd_subfund_proj/dwd_fund2subfund/dwd_subfund2proj 可用，LIKE 'xxx%'）
            subfund_proj_name_prefix: 底层项目名称前缀匹配（仅 dwd_subfund_proj/dwd_subfund2proj 可用，LIKE 'xxx%'）
            proj_name_prefix: 项目名称前缀匹配（仅 dwd_project/dwd_fund2proj 可用，LIKE 'xxx%'）
            lp_name_prefix: LP 名称前缀匹配（仅 dwd_lp2fund 可用，LIKE 'xxx%'）
            company_name_prefix: 公司名称前缀匹配（dwd_fund/dwd_subfund/dwd_project/dwd_subfund_proj 可用，LIKE 'xxx%'）
            investor_name_prefix: 投资方名称前缀匹配（仅 dwd_all_biz 可用，LIKE 'xxx%'）
            investee_name_prefix: 被投资方名称前缀匹配（仅 dwd_all_biz 可用，LIKE 'xxx%'）
            order_by: 排序字段（分组字段/表达式别名或聚合别名，如 sum_invest_amount, year_cap_date）
                      None 时默认按 count DESC 排序
            order_direction: 排序方向，"ASC"（升序）/ "DESC"（降序，默认）
            limit: 返回分组数上限（1-200，默认50）

        Returns:
            {
                "view": str, "group_by": str, "group_by_expr": str | None,
                "agg_funcs": {field: func},
                "count": int,  # 分组数
                "data": [{<分组字段>, "count", <聚合别名>, ...}]
            }

        Examples:
            # 统计各基金类型的数量和总规模
            await stat_group_by_tool(view="dwd_fund", group_by="fund_type")

            # 统计各业务线项目数量（仅股权项目）
            await stat_group_by_tool(
                view="dwd_project", group_by="phase", biz_line="股权项目"
            )

            # 按年份统计基金成立数量
            await stat_group_by_tool(
                view="dwd_fund", group_by_expr="YEAR(cap_date)",
                agg_func="COUNT", agg_field="*"
            )

            # 按月份统计子基金入库数量
            await stat_group_by_tool(
                view="dwd_subfund", group_by_expr="MONTH(in_date)",
                agg_func="COUNT", agg_field="*"
            )

            # 按年份统计 LP→基金关系的承诺出资总额
            await stat_group_by_tool(
                view="dwd_lp2fund", group_by_expr="YEAR(cap_date)",
                agg_func="SUM", agg_field="committed_amt"
            )

            # 统计 cap_date 为空的基金按 fund_type 分组数量
            await stat_group_by_tool(
                view="dwd_fund", group_by="fund_type",
                agg_func="COUNT", agg_field="*",
                is_null_fields=["cap_date"]
            )
        """
        # 构建 filters 字典（仅包含非空值，自动忽略不适用字段）
        filters = {
            "biz_line": biz_line,
            "biz_type": biz_type,
            "fund_type": fund_type,
            "fund_phase": fund_phase,
            "phase": phase,
            "lp_type": lp_type,
            "subfund_type": subfund_type,
            "company_name": company_name,
            "investor_name": investor_name,
            "investee_name": investee_name,
            "dept_id": dept_id,
        }

        # 构建前缀匹配字典（仅包含非空值，自动忽略不适用字段）
        prefix_filters: dict[str, str] = {}
        if fund_name_prefix:
            prefix_filters["fund_name"] = fund_name_prefix
        if subfund_name_prefix:
            prefix_filters["subfund_name"] = subfund_name_prefix
        if subfund_proj_name_prefix:
            prefix_filters["subfund_proj_name"] = subfund_proj_name_prefix
        if proj_name_prefix:
            prefix_filters["proj_name"] = proj_name_prefix
        if lp_name_prefix:
            prefix_filters["lp_name"] = lp_name_prefix
        if company_name_prefix:
            prefix_filters["company_name"] = company_name_prefix
        if investor_name_prefix:
            prefix_filters["investor_name"] = investor_name_prefix
        if investee_name_prefix:
            prefix_filters["investee_name"] = investee_name_prefix
        pf = prefix_filters or None

        # 构建日期范围
        date_ranges: dict[str, tuple[str | None, str | None]] = {}
        if cap_date_start or cap_date_end:
            date_ranges["cap_date"] = (cap_date_start, cap_date_end)
        if flow_time_start or flow_time_end:
            date_ranges["flow_time"] = (flow_time_start, flow_time_end)
        if in_date_start or in_date_end:
            date_ranges["in_date"] = (in_date_start, in_date_end)
        dr = date_ranges or None

        # 构建 agg_funcs 配置
        agg_funcs: dict[str, str] | None = None
        if agg_field is not None:
            agg_funcs = {agg_field: agg_func}

        # 调用通用函数
        return await stat_group_by(
            view=view,
            group_by=group_by,
            group_by_expr=group_by_expr,
            filters=filters,
            date_ranges=dr,
            agg_funcs=agg_funcs,
            order_by=order_by,
            order_direction=order_direction,
            limit=limit,
            null_fields=is_null_fields,
            not_null_fields=is_not_null_fields,
            prefix_filters=pf,
        )
