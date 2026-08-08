"""工具包初始化

集中导出所有工具注册函数，供 server.py 调用。
"""

from .fund import register_fund_tools
from .project import register_project_tools
from .subfund import register_subfund_tools
from .subfund_proj import register_subfund_proj_tools
from .relations import register_relation_tools
from .summary import register_summary_tools
from .auth_tools import register_auth_tools
from .ontology_tools import register_ontology_tools


def register_all_tools(mcp) -> None:
    """注册全部工具到 FastMCP 实例"""
    register_auth_tools(mcp)
    register_fund_tools(mcp)
    register_subfund_tools(mcp)
    register_subfund_proj_tools(mcp)
    register_project_tools(mcp)
    register_relation_tools(mcp)
    register_summary_tools(mcp)
    register_ontology_tools(mcp)


__all__ = ["register_all_tools"]
