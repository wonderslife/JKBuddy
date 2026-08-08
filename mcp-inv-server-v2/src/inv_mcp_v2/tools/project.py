"""直投项目查询工具 - 对应 dwd_project 视图

⚠️ 关键设计：biz_line 为必填参数，防止跨业务域误聚合。
依据 small-model-data-structure-design.md §3.3 决策三。

dwd_project 视图中 biz_line 字段已通过 CASE 转换为中文值（如"股权项目"），
phase 字段也已转换为中文值（如"项目储备"），故本工具直接使用中文值过滤。
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from .base import query_view, count_view


# biz_line 允许的中文枚举值（与 dwd_views.sql 中 CASE 的输出对齐）
BIZ_LINE_VALUES = frozenset({
    "股权项目",
    "委托贷款",
    "融资租赁",
    "商业保理",
    "应急转贷",
    "助保贷",
})


def register_project_tools(mcp: FastMCP) -> None:
    """注册直投项目相关工具"""

    @mcp.tool()
    async def query_project(
        biz_line: str,
        proj_id: str | None = None,
        proj_name: str | None = None,
        phase: str | None = None,
        dept_id: str | None = None,
        company_name: str | None = None,
        deal_stage: str | None = None,
        min_invest_amount: float | None = None,
        max_invest_amount: float | None = None,
        min_exit_amount: float | None = None,
        max_exit_amount: float | None = None,
        in_date_start: str | None = None,
        in_date_end: str | None = None,
        is_null_fields: list[str] | None = None,
        is_not_null_fields: list[str] | None = None,
        proj_name_prefix: str | None = None,
        company_name_prefix: str | None = None,
        order_by: str | None = None,
        order_direction: str = "DESC",
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """查询直投项目信息（含阶段和行业信息）.

        视图: dwd_project
        单位: 金额均为万元

        ⚠️ biz_line 为必填参数，不同业务类型的 invest_amount 语义不同，不可跨 biz_line 直接 SUM.
        可选值: 股权项目 / 委托贷款 / 融资租赁 / 商业保理 / 应急转贷 / 助保贷
        可用排序字段: proj_id, proj_name, phase, biz_line, in_date,
                     invest_amount, exit_amount

        Args:
            biz_line: 【必填】业务类型（中文值）.可选值: 股权项目/委托贷款/融资租赁/商业保理/应急转贷/助保贷
            proj_id: 项目编号（精确）
            proj_name: 项目名称（模糊，LIKE '%xxx%'）
            phase: 项目阶段中文值：项目储备/项目推进中/投后管理/项目退出
            dept_id: 金控公司编号
            company_name: 金控公司名称（模糊，LIKE '%xxx%'）
            deal_stage: 当前阶段名称
            min_invest_amount: 最小投资金额（万元，含）
            max_invest_amount: 最大投资金额（万元，含）
            min_exit_amount: 最小退出金额（万元，含）
            max_exit_amount: 最大退出金额（万元，含）
            in_date_start: 入库日期起始（YYYY-MM-DD，含）
            in_date_end: 入库日期结束（YYYY-MM-DD，含）
            is_null_fields: 需要 IS NULL 过滤的字段列表。可选: invest_amount, exit_amount
            is_not_null_fields: 需要 IS NOT NULL 过滤的字段列表。可选: invest_amount, exit_amount
            proj_name_prefix: 项目名称前缀（如"某"匹配"某科技"开头，LIKE '某%'）
            company_name_prefix: 公司名称前缀（如"科技"匹配"某科技风投"开头，LIKE '科技%'）
            order_by: 排序字段（默认 in_date）。可选：invest_amount/exit_amount/in_date 等
            order_direction: 排序方向，"ASC"（升序，如查询最小投资金额的项目）/ "DESC"（降序，默认）
            limit: 返回行数（1-200）
            offset: 偏移量

        Returns:
            {total, limit, offset, biz_line, data: [...]}

        Raises:
            ValueError: 当 biz_line 不在允许的枚举值中

        Note:
            plan_amt 字段（计划金额）在原始设计文档中提及，
            但 v_cockpit_project 源表无此字段，dwd_views.sql 中 DDL 实际未定义，
            故本工具不暴露 plan_amt 相关参数。
        """
        if biz_line not in BIZ_LINE_VALUES:
            valid = "、".join(sorted(BIZ_LINE_VALUES))
            raise ValueError(
                f"无效的 biz_line: '{biz_line}'.可选值: {valid}"
            )

        filters = {
            "biz_line": biz_line,
            "proj_id": proj_id,
            "proj_name": proj_name,
            "phase": phase,
            "dept_id": dept_id,
            "company_name": company_name,
            "deal_stage": deal_stage,
        }
        prefix_filters: dict[str, str] = {}
        if proj_name_prefix:
            prefix_filters["proj_name"] = proj_name_prefix
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
        ar = amount_ranges or None

        final_order_by = order_by if order_by else "in_date"
        data = await query_view("dwd_project", filters, limit, offset, order_by=final_order_by,
                                date_ranges=date_ranges, amount_ranges=ar,
                                order_direction=order_direction,
                                null_fields=is_null_fields, not_null_fields=is_not_null_fields,
                                prefix_filters=pf)
        total = await count_view("dwd_project", filters, date_ranges=date_ranges, amount_ranges=ar,
                                  null_fields=is_null_fields, not_null_fields=is_not_null_fields,
                                  prefix_filters=pf)
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "biz_line": biz_line,
            "data": data,
        }
