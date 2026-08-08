"""本体定义加载与校验模型

使用 pydantic 对 ontology.yaml（单一事实源 SSOT）做结构校验，
确保本体定义在编译期即被正确约束，避免非法定义进入生成链路。
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, Field, field_validator, model_validator

# 允许的属性类型（对应 SQL / 领域语义）
PropertyType = Literal["string", "decimal", "datetime", "boolean", "int"]


class Property(BaseModel):
    """对象 / 关系类型的单个属性定义。"""

    name: str
    type: PropertyType
    desc: str = ""
    unit: str | None = None


class ObjectType(BaseModel):
    """对象类型定义（对应一个独立实体视图）。"""

    source_view: str
    primary_key: str
    label: str
    properties: list[Property]

    @field_validator("properties")
    @classmethod
    def _unique_property_names(cls, v: list[Property]) -> list[Property]:
        names = [p.name for p in v]
        if len(names) != len(set(names)):
            raise ValueError(f"对象类型属性存在重复名称: {names}")
        return v


class LinkType(BaseModel):
    """关系类型定义（投资方 → 被投资方）。"""

    source_view: str
    source_object: list[str]
    target_object: list[str]
    subtypes: list[str] = []
    label: str
    properties: list[Property]

    @field_validator("properties")
    @classmethod
    def _unique_property_names(cls, v: list[Property]) -> list[Property]:
        names = [p.name for p in v]
        if len(names) != len(set(names)):
            raise ValueError(f"关系类型属性存在重复名称: {names}")
        return v


class Rule(BaseModel):
    """业务规则定义（仅语义/口径类，禁止行为规则）。"""

    id: str
    scope: str
    desc: str = ""
    definition: str
    enforce_in: list[str] = []

    @field_validator("definition")
    @classmethod
    def _reject_behavior_rules(cls, v: str) -> str:
        # 反模式二检测：行为规则（输出/去重/过滤/分页）不得进入本体
        behavior_markers = ("禁止过滤", "不得去重", "必须原样输出", "不得自行过滤", "禁止去重")
        for marker in behavior_markers:
            if marker in v:
                raise ValueError(
                    f"规则 definition 疑似行为规则（包含「{marker}」），"
                    "行为规则应迁移至 A2 指令，不得写入本体 rules 段"
                )
        return v


class ViewSecurity(BaseModel):
    """单个视图的安全白名单约束（生成 base.py 白名单的唯一依据）。"""

    allowed_fields: list[str]
    date_range_fields: list[str] = []
    amount_range_fields: list[str] = []
    group_by_fields: list[str] = []
    agg_fields: list[str] = []
    null_check_fields: list[str] = []
    prefix_match_fields: list[str] = []
    group_by_exprs: list[str] = []
    stable_order_field: str
    default_fields: list[str]

    @model_validator(mode="after")
    def _validate_subset_rules(self) -> ViewSecurity:
        allowed = set(self.allowed_fields)

        def _check(name: str, fields: list[str]) -> None:
            for f in fields:
                if f not in allowed:
                    raise ValueError(
                        f"白名单维度 {name} 中的字段 `{f}` 不在 allowed_fields 中"
                    )

        _check("date_range_fields", self.date_range_fields)
        _check("amount_range_fields", self.amount_range_fields)
        _check("group_by_fields", self.group_by_fields)
        _check("agg_fields", self.agg_fields)
        _check("null_check_fields", self.null_check_fields)
        _check("prefix_match_fields", self.prefix_match_fields)
        # stable_order_field 必须为合法字段或特殊约定（如 biz_type）
        if self.stable_order_field not in allowed:
            raise ValueError(
                f"stable_order_field `{self.stable_order_field}` 不在 allowed_fields 中"
            )
        return self


class Ontology(BaseModel):
    """本体根模型。"""

    version: str
    object_types: dict[str, ObjectType]
    link_types: dict[str, LinkType]
    rules: list[Rule] = []
    security: dict[str, ViewSecurity] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_cross_references(self) -> Ontology:
        object_views = {o.source_view for o in self.object_types.values()}
        link_views = {link.source_view for link in self.link_types.values()}
        security_views = set(self.security.keys())

        # 每个安全约束视图必须属于对象或关系承载视图（data 视图）
        known_views = object_views | link_views
        unknown = security_views - known_views
        if unknown:
            raise ValueError(f"security 中存在未定义的对象/关系视图: {sorted(unknown)}")
        return self


def load_ontology(path: Path | str) -> Ontology:
    """加载并校验本体定义文件。

    Args:
        path: ontology.yaml 的绝对路径

    Returns:
        校验通过后的 Ontology 模型

    Raises:
        FileNotFoundError: 文件不存在
        yaml.YAMLError: YAML 语法错误
        pydantic.ValidationError: 结构不符合 Schema
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"本体定义文件不存在: {p}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"本体文件顶层必须是映射结构: {p}")
    return Ontology.model_validate(raw)