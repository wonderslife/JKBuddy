"""本体层（Ontology）子包：语义单一事实源 + 双投影生成与漂移校验。

- model.py     ：ontology.yaml 的 pydantic 校验模型与加载器
- generator.py ：机读投影（base.py 白名单）+ 人读投影（SKILL 语义段）
- drift.py     ：漂移检查器（本体 vs base.py 实际白名单一致性）

设计约束：本子包只做"生成/校验"，不改动任何运行时查询逻辑，
保证本体层落地不影响现有 MCP 功能。
"""

from functools import lru_cache
from pathlib import Path

from .drift import (
    DriftReport,
    actual_whitelists_from_module,
    check_drift,
    compare_skill_semantics,
    compare_whitelists,
)
from .generator import (
    Whitelists,
    generate_whitelists,
    render_skill_semantics,
    render_whitelists_python,
)
from .model import Ontology, load_ontology


def _candidate_paths() -> list[Path]:
    """按优先级返回候选本体路径。

    部署差异：源码运行时 `__file__` 在项目内，`parents[3]` 即项目根；
    但 pip 安装到 site-packages 后 `__file__` 指向 site-packages，
    `parents[3]` 不再等于项目根。因此优先使用进程 CWD（run_mcp.py
    已 chdir 到项目根），再回退到基于 `__file__` 的推断。
    """
    return [
        Path.cwd() / "ontology" / "ontology.yaml",
        Path(__file__).resolve().parents[3] / "ontology" / "ontology.yaml",
    ]


def _default_ontology_path() -> Path:
    """本体默认路径：优先 CWD 下的 ontology/ontology.yaml，否则按包位置推断。"""
    for candidate in _candidate_paths():
        if candidate.exists():
            return candidate
    return _candidate_paths()[0]


def get_ontology_path() -> Path:
    """解析本体实际路径：INV_MCP_ONTOLOGY_PATH → .env 配置 → 默认候选路径。"""
    from ..config import get_settings

    configured = get_settings().ontology_path
    if configured:
        return Path(configured)
    return _default_ontology_path()


@lru_cache(maxsize=1)
def get_ontology() -> Ontology:
    """加载并缓存本体（进程内单例，fail-fast）。

    路径优先取 INV_MCP_ONTOLOGY_PATH，否则用默认相对路径。
    本体加载失败时抛错，禁止静默降级。进程内同一本体只解析一次，供
    运行时白名单（base.py）与本体内省工具（get_ontology_tool）复用。
    """
    return load_ontology(get_ontology_path())


__all__ = [
    "Ontology",
    "load_ontology",
    "get_ontology",
    "get_ontology_path",
    "Whitelists",
    "generate_whitelists",
    "render_skill_semantics",
    "render_whitelists_python",
    "DriftReport",
    "check_drift",
    "compare_whitelists",
    "compare_skill_semantics",
    "actual_whitelists_from_module",
]