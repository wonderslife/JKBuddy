"""本体投影生成器

core 三元组的两个投影：
1. 机读投影（machine projection）：从 ontology.yaml 的 security 段生成
   base.py 所需的全部白名单字典（WHITELIST_* 常量）。
2. 人读投影（human projection）：从 object_types / link_types / rules 段
   渲染 SKILL 语义段（字段含义 / 关系语义 / 业务规则）。

本项目 Phase 1 采用"生成 + 校验"双保险：生成器产出权威的机读投影对象，
漂移检查器（drift.py）负责比对生成结果与 base.py 已提交内容是否零 diff。
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import Ontology


@dataclass(frozen=True)
class Whitelists:
    """从本体 security 段生成的机读投影（与 base.py 白名单常量一一对应）。"""

    ALLOWED_FIELDS: dict[str, set[str]]
    DATE_RANGE_FIELDS: dict[str, set[str]]
    AMOUNT_RANGE_FIELDS: dict[str, set[str]]
    GROUP_BY_FIELDS: dict[str, set[str]]
    AGG_FIELDS: dict[str, set[str]]
    NULL_CHECK_FIELDS: dict[str, set[str]]
    PREFIX_MATCH_FIELDS: dict[str, set[str]]
    ALLOWED_GROUP_BY_EXPRS: dict[str, set[str]]
    STABLE_ORDER_FIELDS: dict[str, str]
    DEFAULT_FIELDS: dict[str, list[str]]


def generate_whitelists(ontology: Ontology) -> Whitelists:
    """由本体生成全部机读白名单投影。

    Args:
        ontology: 已校验的本体模型

    Returns:
        Whitelists: 与 base.py 白名单常量结构一致的数据容器
    """
    allowed: dict[str, set[str]] = {}
    date_range: dict[str, set[str]] = {}
    amount_range: dict[str, set[str]] = {}
    group_by: dict[str, set[str]] = {}
    agg: dict[str, set[str]] = {}
    null_check: dict[str, set[str]] = {}
    prefix: dict[str, set[str]] = {}
    exprs: dict[str, set[str]] = {}
    stable: dict[str, str] = {}
    defaults: dict[str, list[str]] = {}

    for view, sec in ontology.security.items():
        allowed[view] = set(sec.allowed_fields)
        date_range[view] = set(sec.date_range_fields)
        amount_range[view] = set(sec.amount_range_fields)
        group_by[view] = set(sec.group_by_fields)
        agg[view] = set(sec.agg_fields)
        null_check[view] = set(sec.null_check_fields)
        prefix[view] = set(sec.prefix_match_fields)
        exprs[view] = set(sec.group_by_exprs)
        stable[view] = sec.stable_order_field
        defaults[view] = list(sec.default_fields)

    return Whitelists(
        ALLOWED_FIELDS=allowed,
        DATE_RANGE_FIELDS=date_range,
        AMOUNT_RANGE_FIELDS=amount_range,
        GROUP_BY_FIELDS=group_by,
        AGG_FIELDS=agg,
        NULL_CHECK_FIELDS=null_check,
        PREFIX_MATCH_FIELDS=prefix,
        ALLOWED_GROUP_BY_EXPRS=exprs,
        STABLE_ORDER_FIELDS=stable,
        DEFAULT_FIELDS=defaults,
    )


def render_skill_semantics(ontology: Ontology) -> str:
    """渲染人读投影：SKILL 语义段（Markdown）。

    该段描述对象类型、关系类型与业务规则，供 SKILL/A2 引用，
    避免在各处重复手写语义定义。生成结果由漂移检查器约束一致性。

    Args:
        ontology: 已校验的本体模型

    Returns:
        Markdown 语义段文本
    """
    lines: list[str] = []
    lines.append(
        "<!-- 本段由 scripts/generate_from_ontology.py 从 ontology.yaml 自动生成，"
        "禁止手工编辑。如下划线以上内容不一致，请重跑生成器。 -->"
    )
    lines.append("")
    lines.append("## 本体语义段（Ontology Projection）")
    lines.append("")
    lines.append(
        "> 语义单一事实源：`mcp-inv-server-v2/ontology/ontology.yaml`。"
        "字段/关系/规则的定义以本体为准，此处为渲染副本。"
    )
    lines.append("")

    # 对象类型
    lines.append("### 对象类型")
    lines.append("")
    lines.append("| 对象 | 视图 | 主键 | 属性 |")
    lines.append("|------|------|------|------|")
    for name, obj in ontology.object_types.items():
        props = "、".join(f"`{p.name}`" for p in obj.properties)
        lines.append(f"| **{name}**（{obj.label}） | `{obj.source_view}` | `{obj.primary_key}` | {props} |")
    lines.append("")

    # 关系类型
    lines.append("### 关系类型")
    lines.append("")
    lines.append("| 关系 | 视图 | 投资方 | 被投资方 | 子类型 |")
    lines.append("|------|------|--------|---------|--------|")
    for name, link in ontology.link_types.items():
        subtypes = "、".join(link.subtypes) if link.subtypes else "—"
        lines.append(
            f"| **{name}**（{link.label}） | `{link.source_view}` | "
            f"{', '.join(link.source_object)} | {', '.join(link.target_object)} | {subtypes} |"
        )
    lines.append("")

    # 业务规则
    lines.append("### 业务规则")
    lines.append("")
    for rule in ontology.rules:
        lines.append(f"- **{rule.id}**（作用域 `{rule.scope}`）：{rule.definition}"
                     + (f"〔enforce_in: {', '.join(rule.enforce_in)}〕" if rule.enforce_in else ""))
    lines.append("")

    return "\n".join(lines)


def render_whitelists_python(ontology: Ontology) -> str:
    """渲染机读投影的 Python 源码片段（供人工/CI 对照 base.py 结构）。

    该片段展示本体应生成的 base.py 白名单常量，供 review 与文档引用；
    运行时白名单仍以 base.py 为准，并由漂移检查器保证两者一致。
    """
    wl = generate_whitelists(ontology)
    blocks: list[str] = []

    def _set_block(name: str, value: dict[str, set[str]]) -> str:
        out = [f'{name}: dict[str, set[str]] = {{']
        for view in sorted(value):
            fields = ", ".join(f'"{f}"' for f in sorted(value[view]))
            out.append(f'    "{view}": {{{fields}}},')
        out.append("}")
        return "\n".join(out)

    def _stable_block() -> str:
        out = ['STABLE_ORDER_FIELDS: dict[str, str] = {']
        for view in sorted(wl.STABLE_ORDER_FIELDS):
            out.append(f'    "{view}": "{wl.STABLE_ORDER_FIELDS[view]}",')
        out.append("}")
        return "\n".join(out)

    def _defaults_block() -> str:
        out = ['DEFAULT_FIELDS: dict[str, list[str]] = {']
        for view in sorted(wl.DEFAULT_FIELDS):
            fields = ", ".join(f'"{f}"' for f in wl.DEFAULT_FIELDS[view])
            out.append(f'    "{view}": [{fields}],')
        out.append("}")
        return "\n".join(out)

    blocks.append(_set_block("ALLOWED_FIELDS", wl.ALLOWED_FIELDS))
    blocks.append(_set_block("DATE_RANGE_FIELDS", wl.DATE_RANGE_FIELDS))
    blocks.append(_set_block("AMOUNT_RANGE_FIELDS", wl.AMOUNT_RANGE_FIELDS))
    blocks.append(_set_block("GROUP_BY_FIELDS", wl.GROUP_BY_FIELDS))
    blocks.append(_set_block("AGG_FIELDS", wl.AGG_FIELDS))
    blocks.append(_set_block("NULL_CHECK_FIELDS", wl.NULL_CHECK_FIELDS))
    blocks.append(_set_block("PREFIX_MATCH_FIELDS", wl.PREFIX_MATCH_FIELDS))
    blocks.append(_set_block("ALLOWED_GROUP_BY_EXPRS", wl.ALLOWED_GROUP_BY_EXPRS))
    blocks.append(_stable_block())
    blocks.append(_defaults_block())
    return "\n\n".join(blocks)


def view_ids(ontology: Ontology) -> list[str]:
    """返回本体中全部承载数据的视图名（对象视图 + 关系视图）。"""
    views = {o.source_view for o in ontology.object_types.values()}
    views |= {link.source_view for link in ontology.link_types.values()}
    return sorted(views)