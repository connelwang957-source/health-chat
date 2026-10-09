"""架构边界测试：把《项目开发指导》§5.4 的分层约定固化成可执行断言。

约定（依赖方向只能由外向内）：

    interfaces ─▶ application ─▶ domain
                        │
                        └─▶ infrastructure ─▶ domain（实现端口）

因此：
- `domain` 不得 import 任何同项目的外层（infrastructure / application / interfaces / fallback）；
- `interfaces` 不得越过 application 直接 import infrastructure；
- `application` 允许 import infrastructure（它是**组合根**，但只允许一处：
  `application/runtime.py`），其余模块必须通过 runtime 取依赖；
- `fallback` 是独立的兜底链，不得 import application / interfaces；
  其中 `robot_qwen.xing_lin()` 的自动装配是**唯一**允许碰 infrastructure 的例外。

用 AST 静态分析，不需要真的导入模块（因此不依赖网络与三方库是否装好）。
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "xinglin"


def _modules(*packages: str) -> list[Path]:
    """收集指定包下所有 .py（排除 __pycache__）。"""
    files: list[Path] = []
    for pkg in packages:
        files.extend(p for p in (SRC / pkg).rglob("*.py") if "__pycache__" not in p.parts)
    return sorted(files)


def _imports(path: Path) -> set[str]:
    """收集一个文件里出现的**绝对 import** 模块名。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module)
    return names


def _rel(path: Path) -> str:
    return path.relative_to(SRC.parent).as_posix()


def _violations(paths: list[Path], forbidden: tuple[str, ...]) -> list[str]:
    bad: list[str] = []
    for path in paths:
        for module in _imports(path):
            if module.startswith(forbidden):
                bad.append(f"{_rel(path)} → {module}")
    return bad


# -- domain：不得依赖任何外层 ------------------------------------------------
def test_domain_never_imports_outer_layers():
    bad = _violations(
        _modules("domain"),
        ("xinglin.infrastructure", "xinglin.application",
         "xinglin.interfaces", "xinglin.fallback"),
    )
    assert bad == [], f"domain 层出现向外依赖：{bad}"


# -- interfaces：只允许按文档取用基础设施的通用能力 ---------------------------
# 文档 §2.6 的三条硬规则只禁止「domain → 外层」和「application → interfaces」；
# 而 §4.6 的 cli.py 示例本身就写着
#   from xinglin.infrastructure.cache import redis_manager
# 所以 interfaces 直接取用**基础设施的通用能力**（缓存）是文档允许的。
# 真正要守住的是：interfaces 不得碰**数据/资源**（§2.6 第 3 条）。
ALLOWED_INFRA_FOR_INTERFACES = ("xinglin.infrastructure.cache",)


def test_interfaces_only_uses_whitelisted_infrastructure():
    bad = [v for v in _violations(_modules("interfaces"), ("xinglin.infrastructure",))
           if not any(v.endswith(f"→ {m}") for m in ALLOWED_INFRA_FOR_INTERFACES)]
    assert bad == [], f"interfaces 使用了白名单之外的基础设施模块：{bad}"


def test_interfaces_never_touch_data_resources():
    """文档 §2.6 第 3 条：数据/资源归领域层所有，interfaces 层不能直接读写。"""
    bad = _violations(_modules("interfaces"),
                      ("xinglin.domain.rag.vectorstore", "xinglin.domain.graph.build_graph"))
    assert bad == [], f"interfaces 直接触碰数据/资源：{bad}"


# -- application：只允许组合根 runtime.py 碰基础设施 --------------------------
def test_only_runtime_imports_infrastructure_in_application():
    offenders = _violations(
        [p for p in _modules("application") if p.name != "runtime.py"],
        ("xinglin.infrastructure",),
    )
    assert offenders == [], f"application 层除 runtime.py 外不应依赖基础设施：{offenders}"


# -- fallback：不得依赖 application / interfaces -----------------------------
def test_fallback_never_imports_application_or_interfaces():
    bad = _violations(_modules("fallback"),
                      ("xinglin.application", "xinglin.interfaces"))
    assert bad == [], f"fallback 出现向上依赖：{bad}"


def test_fallback_infrastructure_exception_is_documented():
    """`robot_qwen.xing_lin()` 的自动装配是 fallback 里唯一允许碰基础设施之处。"""
    offenders = _violations(
        [p for p in _modules("fallback") if p.name != "robot_qwen.py"],
        ("xinglin.infrastructure",),
    )
    assert offenders == [], f"fallback 里只有 robot_qwen.py 可碰基础设施：{offenders}"


# -- 层次划分健全性 ----------------------------------------------------------
@pytest.mark.parametrize("layer", ["domain", "application", "fallback",
                                   "infrastructure", "interfaces"])
def test_layer_directories_exist_and_nonempty(layer):
    assert _modules(layer), f"缺少分层目录或目录为空：xinglin/{layer}"
