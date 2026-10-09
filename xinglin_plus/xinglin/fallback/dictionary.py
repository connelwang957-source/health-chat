"""8 类医学词典与实体识别（第 1 代规则兜底链的词表层）。

词表来源：`dict/*.txt`（由 `domain/graph` 的图谱导出，或既有工程直接提供）。
本模块**只做纯逻辑**；读文件由 `load_words()` 提供，由组合根（`xing_lin()`）调用一次。

识别策略：**最长优先匹配**；同长度按 ``ROLE_PRIORITY``（与图谱标签一致）取第一个命中的。

本类实现领域端口 ``EntityRecognizer``。
"""

from pathlib import Path

from xinglin.domain.values import EntityRole

# 角色优先级：越靠前越优先（同一个词可能同时出现在多张表里）
ROLE_PRIORITY: tuple[str, ...] = tuple(role.node_label for role in EntityRole) \
    + ("Department", "Producer")
DENY_ROLE = "deny"

# dict/*.txt 文件名 → 角色（与图谱标签一致；deny 为否定词，不属于实体）
FILE_ROLES: tuple[tuple[str, str], ...] = (
    ("disease", "Disease"),
    ("symptom", "Symptom"),
    ("drug", "Drug"),
    ("food", "Food"),
    ("check", "Check"),
    ("department", "Department"),
    ("producer", "Producer"),
    ("deny", DENY_ROLE),
)


def load_words(dict_dir: str | Path) -> dict[str, list[str]]:
    """读取 ``dict/*.txt`` → ``{角色: [词, ...]}``。

    文件缺失时静默跳过（词典不可用 → 规则链自行降级），不抛异常阻断启动。
    """
    base = Path(dict_dir)
    words: dict[str, list[str]] = {}
    for filename, role in FILE_ROLES:
        path = base / f"{filename}.txt"
        if not path.exists():
            continue
        items = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
        words[role] = [w for w in items if w]
    return words


class MedicalDictionary:
    """医学词典：实体词识别 + 否定词判定。"""

    def __init__(self, words: dict[str, list[str]] | None = None):
        self._by_role: dict[str, set[str]] = {
            role: set(word_list or []) for role, word_list in (words or {}).items()
        }
        self._max_len = max((len(w) for ws in self._by_role.values() for w in ws), default=0)

    # -- 基本信息 -----------------------------------------------------------
    @property
    def size(self) -> int:
        """实体词总数（不含否定词）。"""
        return sum(len(ws) for role, ws in self._by_role.items() if role != DENY_ROLE)

    @property
    def available(self) -> bool:
        return self.size > 0

    def role_counts(self) -> dict[str, int]:
        return {role: len(ws) for role, ws in self._by_role.items() if ws}

    # -- 查询 ---------------------------------------------------------------
    def lookup(self, word: str, roles: tuple[str, ...] | None = None) -> str | None:
        """词 → 角色（按 ``ROLE_PRIORITY`` 顺序）。"""
        allowed = roles or ROLE_PRIORITY
        for role in allowed:
            if word in self._by_role.get(role, ()):
                return role
        return None

    def is_denied(self, text: str) -> bool:
        """是否含否定 / 限制表述（如「不能吃」「不适合」）。"""
        deny = self._by_role.get(DENY_ROLE, set())
        return any(w in (text or "") for w in deny if w)

    def find_entity(self, text: str, roles: tuple[str, ...] | None = None
                    ) -> tuple[str, str] | None:
        """最长优先匹配一个实体，返回 ``(实体, 角色)``；未命中返回 None。"""
        t = text or ""
        best: tuple[str, str, int, int] | None = None
        for start in range(len(t)):
            upper = min(len(t), start + self._max_len)
            for end in range(upper, start, -1):
                role = self.lookup(t[start:end], roles)
                if role:
                    if best is None or (end - start) > (best[3] - best[2]):
                        best = (t[start:end], role, start, end)
                    break
        return (best[0], best[1]) if best else None

    def find_all(self, text: str, roles: tuple[str, ...] | None = None,
                 limit: int = 5) -> list[tuple[str, str]]:
        """非重叠地找出全部实体（长词优先）。"""
        t = text or ""
        found: list[tuple[str, str]] = []
        spans: list[tuple[int, int]] = []
        for start in range(len(t)):
            if any(s <= start < e for s, e in spans):
                continue
            upper = min(len(t), start + self._max_len)
            for end in range(upper, start, -1):
                role = self.lookup(t[start:end], roles)
                if role:
                    found.append((t[start:end], role))
                    spans.append((start, end))
                    break
            if len(found) >= limit:
                break
        return found


__all__ = ["MedicalDictionary", "load_words", "ROLE_PRIORITY", "DENY_ROLE", "FILE_ROLES"]
