"""本体内省工具 - 供 Agent 运行时动态获取本体定义

本体（ontology/ontology.yaml）是语义单一事实源（SSOT）。本工具让 Agent
在对话中直接拉取对象类型、关系类型、业务规则与视图白名单，从而：
- 无需在指令/SKILL 中写死语义定义，避免随本体变更而过期；
- 构造查询参数时依据「视图白名单」选择合法字段。

不调用数据库，仅返回本体机读投影。
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from ..ontology import get_ontology as _load_ontology

# 允许的 scope 取值
_SCOPES = frozenset({"all", "objects", "relations", "rules", "views"})


def register_ontology_tools(mcp: FastMCP) -> None:
    """注册本体内省工具"""

    @mcp.tool()
    async def get_ontology(
        scope: str = "all",
    ) -> dict[str, Any]:
        """获取本体定义（语义单一事实源 ontology.yaml 的运行时投影）。

        供查询工具动态了解数据语义与字段边界：
        - objects: 对象类型（源视图、主键、属性及类型/单位/说明）
        - relations: 关系类型（投资方→被投资方、承载视图、子类型）
        - rules: 业务口径/语义规则（含 enforce_in 关联工具）
        - views: 视图安全白名单（可过滤/分组/聚合字段，供构造查询参数）

        Args:
            scope: 返回范围。可选 "all"(默认，返回全部) / "objects" /
                   "relations" / "rules" / "views"。

        Returns:
            形如 {"version": str, <scope>: {...}} 的机读字典。
        """
        if scope not in _SCOPES:
            raise ValueError(
                f"未知 scope: {scope}。允许值: {', '.join(sorted(_SCOPES))}"
            )

        ontology = _load_ontology()
        dump = ontology.model_dump()

        result: dict[str, Any] = {"version": ontology.version}
        if scope in ("all", "objects"):
            result["objects"] = dump["object_types"]
        if scope in ("all", "relations"):
            result["relations"] = dump["link_types"]
        if scope in ("all", "rules"):
            result["rules"] = [r.model_dump() for r in ontology.rules]
        if scope in ("all", "views"):
            result["views"] = dump["security"]
        return result