"""共享测试夹具：**全部离线**（零网络、零数据库、零真实 LLM）。

这些 Fake 同时用于 `tests/test_ports.py` 的结构化契约检查——
只要它们满足 `xinglin.domain.ports` 里的 Protocol，端口与适配器的约定就没被破坏。
"""

import pytest


class FakeLLM:
    """`LLM` 端口的最小实现：返回预置文本，并记录调用参数。"""

    def __init__(self, reply: str = "", available: bool = True):
        self.reply = reply
        self._available = available
        self.calls: list[tuple[str, str]] = []

    @property
    def available(self) -> bool:
        return self._available

    def complete(self, system: str, user: str,
                 temperature: float = 0.0, max_tokens: int = 2048) -> str:
        self.calls.append((system, user))
        return self.reply


class FakeGraph:
    """`GraphStore` 端口的最小实现：返回预置记录，并记录查询语句。"""

    def __init__(self, rows: list[dict] | None = None):
        self.rows = rows if rows is not None else []
        self.queries: list[tuple[str, dict | None]] = []

    def query(self, cypher: str, params: dict | None = None) -> list[dict]:
        self.queries.append((cypher, params))
        return self.rows

    def explain(self, cypher: str, params: dict | None = None) -> None:
        return None

    def close(self) -> None:
        return None


class FakeRecognizer:
    """`EntityRecognizer` 端口的最小实现：按预置映射做子串匹配。"""

    def __init__(self, mapping: dict[str, str] | None = None, available: bool = True):
        self.mapping = mapping or {}
        self._available = available

    @property
    def available(self) -> bool:
        return self._available

    def find_entity(self, text: str,
                    roles: tuple[str, ...] | None = None) -> tuple[str, str] | None:
        for name, label in self.mapping.items():
            if name in (text or ""):
                return name, label
        return None


class FakeLiterature:
    """`LiteratureSearch` 端口的最小实现。"""

    def __init__(self, docs: list[dict] | None = None, available: bool = True):
        self.docs = docs if docs is not None else []
        self._available = available

    @property
    def available(self) -> bool:
        return self._available

    def search(self, query: str, k: int = 8) -> list[dict]:
        return self.docs[:k]


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def fake_graph() -> FakeGraph:
    return FakeGraph()


@pytest.fixture
def fake_recognizer() -> FakeRecognizer:
    return FakeRecognizer({"感冒": "Disease"})


@pytest.fixture
def fake_literature() -> FakeLiterature:
    return FakeLiterature([{"text": "感冒以对症支持为主。",
                            "metadata": {"source": "文献A", "page": 3}}])
