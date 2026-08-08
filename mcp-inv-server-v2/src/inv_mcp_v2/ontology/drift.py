"""漂移检查器：本体(SSOT) vs base.py 已提交白名单 的一致性比对

核心思想（对应设计文档 §5.1 漂移检查锁）：
- 本体是语义单一事实源，只能改本体。
- base.py 白名单是运行时的机读投影，不得手工双写。
- 本检查器从本体重新生成白名单，与 base.py 实际加载的白名单做零 diff 比对；
  任一不一致即判定"漂移"，供 CI 阻断发布。

一致性保证：
- DEFAULT_FIELDS 为有序 list，其余白名单为无序 set，分别精确比较。
- 覆盖 base.py 中全部 10 个白名单常量，不漏维度。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

from .generator import Whitelists, generate_whitelists, render_skill_semantics
from .model import Ontology


@dataclass
class DriftItem:
    """单条漂移记录。"""

    view: str
    whitelist: str
    detail: str


@dataclass
class DriftReport:
    """漂移检查结果。"""

    ok: bool
    items: list[DriftItem] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if self.ok:
            return "✅ 零漂移：本体生成的白名单与 base.py 已提交内容完全一致"
        return f"❌ 发现 {len(self.items)} 处漂移，请先修改 ontology.yaml 并重跑生成器"


def _diff_set(view: str, wl_name: str, generated: set[str], actual: set[str], items: list[DriftItem]) -> None:
    if generated == actual:
        return
    only_gen = generated - actual
    only_act = actual - generated
    detail = "生成有而 base.py 无: " + (", ".join(sorted(only_gen)) or "无")
    detail += "；base.py 有而生成无: " + (", ".join(sorted(only_act)) or "无")
    items.append(DriftItem(view=view, whitelist=wl_name, detail=detail))


def _diff_list(view: str, wl_name: str, generated: list[str], actual: list[str], items: list[DriftItem]) -> None:
    if generated == actual:
        return
    detail = f"生成: [{', '.join(generated)}]；base.py: [{', '.join(actual)}]"
    items.append(DriftItem(view=view, whitelist=wl_name, detail=detail))


def compare_whitelists(generated: Whitelists, actual: dict[str, object]) -> DriftReport:
    """比对生成投影与 base.py 实际白名单。

    Args:
        generated: 由本体生成的机读投影
        actual: base.py 中实际加载的白名单常量字典
            key 为常量名（如 ALLOWED_FIELDS），value 为对应 dict。

    Returns:
        DriftReport: 含全部漂移项
    """
    items: list[DriftItem] = []

    # 集合类白名单（无序）：常量名 → 生成的一组白名单
    set_specs: list[tuple[str, dict[str, set[str]]]] = [
        ("ALLOWED_FIELDS", generated.ALLOWED_FIELDS),
        ("DATE_RANGE_FIELDS", generated.DATE_RANGE_FIELDS),
        ("AMOUNT_RANGE_FIELDS", generated.AMOUNT_RANGE_FIELDS),
        ("GROUP_BY_FIELDS", generated.GROUP_BY_FIELDS),
        ("AGG_FIELDS", generated.AGG_FIELDS),
        ("NULL_CHECK_FIELDS", generated.NULL_CHECK_FIELDS),
        ("PREFIX_MATCH_FIELDS", generated.PREFIX_MATCH_FIELDS),
        ("ALLOWED_GROUP_BY_EXPRS", generated.ALLOWED_GROUP_BY_EXPRS),
    ]
    for name, gen in set_specs:
        act = cast(dict[str, set[str]], actual.get(name, {}))
        for view in sorted(set(gen) | set(act)):
            _diff_set(view, name, gen.get(view, set()), act.get(view, set()), items)

    # 稳定排序字段（标量映射）
    gen_stable = generated.STABLE_ORDER_FIELDS
    act_stable = cast(dict[str, str], actual.get("STABLE_ORDER_FIELDS", {}))
    for view in sorted(set(gen_stable) | set(act_stable)):
        stable_gen = gen_stable.get(view)
        stable_act = act_stable.get(view)
        if stable_gen != stable_act:
            items.append(DriftItem(view=view, whitelist="STABLE_ORDER_FIELDS",
                                   detail=f"生成: {stable_gen}；base.py: {stable_act}"))

    # 默认返回字段（有序 list）
    gen_defaults = generated.DEFAULT_FIELDS
    act_defaults = cast(dict[str, list[str]], actual.get("DEFAULT_FIELDS", {}))
    for view in sorted(set(gen_defaults) | set(act_defaults)):
        default_gen = gen_defaults.get(view, [])
        default_act = act_defaults.get(view, [])
        _diff_list(view, "DEFAULT_FIELDS", default_gen, default_act, items)

    return DriftReport(ok=not items, items=items)


def check_drift(ontology: Ontology, actual: dict[str, object]) -> DriftReport:
    """从本体生成投影并与 base.py 实际白名单比对（便捷入口）。

    Args:
        ontology: 已校验的本体模型
        actual: base.py 实际白名单常量字典

    Returns:
        DriftReport
    """
    generated = generate_whitelists(ontology)
    return compare_whitelists(generated, actual)


def actual_whitelists_from_module(module: object) -> dict[str, object]:
    """从 base.py 模块对象提取实际白名单常量。

    Args:
        module: 已 import 的 base 模块（含 ALLOWED_FIELDS 等常量）

    Returns:
        常量名 → 常量值的字典
    """
    names = [
        "ALLOWED_FIELDS",
        "DATE_RANGE_FIELDS",
        "AMOUNT_RANGE_FIELDS",
        "GROUP_BY_FIELDS",
        "AGG_FIELDS",
        "NULL_CHECK_FIELDS",
        "PREFIX_MATCH_FIELDS",
        "ALLOWED_GROUP_BY_EXPRS",
        "STABLE_ORDER_FIELDS",
        "DEFAULT_FIELDS",
    ]
    return {name: getattr(module, name) for name in names}


def compare_skill_semantics(ontology: Ontology, committed_text: str) -> DriftReport:
    """比对本体渲染的 SKILL 语义段与已提交的人读投影产物。

    Args:
        ontology: 已校验的本体模型
        committed_text: 已提交的 SKILL 语义段文本（如 ontology/generated/skill-semantics.md）

    Returns:
        DriftReport: 语义段不一致时 ok=False
    """
    generated = render_skill_semantics(ontology)
    if generated == committed_text:
        return DriftReport(ok=True)
    items = [
        DriftItem(
            view="SKILL",
            whitelist="语义段",
            detail="本体渲染的 SKILL 语义段与已提交产物不一致，请重跑生成器（render-skill --write）",
        )
    ]
    return DriftReport(ok=False, items=items)