"""端口契约测试：确认领域端口与"实现/测试替身"的结构一致性。

`domain/ports.py` 用 `Protocol`（隐式抽象）定义契约 —— 好处是适配器不必显式继承，
代价是契约只能靠**测试**保证。本文件就是那道保险：一旦端口方法改名或改签名，
`isinstance` 结构化检查会立刻失败。
"""

from xinglin.domain.ports import (
    CacheStore,
    EntityRecognizer,
    GraphStore,
    LLM,
    LiteratureSearch,
)
from tests.conftest import FakeGraph, FakeLLM, FakeLiterature, FakeRecognizer


def test_fake_llm_satisfies_llm_port():
    assert isinstance(FakeLLM(), LLM)


def test_fake_graph_satisfies_graph_store_port():
    assert isinstance(FakeGraph(), GraphStore)


def test_fake_literature_satisfies_literature_search_port():
    assert isinstance(FakeLiterature(), LiteratureSearch)


def test_fake_recognizer_satisfies_entity_recognizer_port():
    assert isinstance(FakeRecognizer(), EntityRecognizer)


def test_ports_are_runtime_checkable():
    """端口必须是 runtime_checkable，否则 isinstance 会直接抛 TypeError。"""
    for port in (LLM, GraphStore, LiteratureSearch, CacheStore, EntityRecognizer):
        assert hasattr(port, "_is_runtime_protocol")
