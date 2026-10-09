"""从 Neo4j 图谱导出 8 类医学词典到 `dict/*.txt`。

词典是**图谱的派生产物**：第 1 代规则兜底链（`xinglin.fallback.dictionary`）
用它做实体最长匹配，因此必须以图谱为准，由本脚本生成而不是手工维护。

    7 类实体词：disease / symptom / drug / food / check / department / producer
    1 类否定词：deny（内置保留字，脚本写入默认值）

用法::

    python -m xinglin.infrastructure.init_data.export_dict            # 导出到 dict/
    python -m xinglin.infrastructure.init_data.export_dict --dry-run  # 只看统计
"""

import argparse
from pathlib import Path

from xinglin.config import DICT_DIR
from xinglin.infrastructure.graph import Neo4jGraph

# 图谱标签 → 词典文件名
LABEL_FILES: tuple[tuple[str, str], ...] = (
    ("Disease", "disease"),
    ("Symptom", "symptom"),
    ("Drug", "drug"),
    ("Food", "food"),
    ("Check", "check"),
    ("Department", "department"),
    ("Producer", "producer"),
)

# 否定 / 限制表述（供 `MedicalDictionary.is_denied` 判定宜忌方向）
DENY_WORDS: tuple[str, ...] = (
    "不能", "不可以", "不宜", "不适合", "不适宜", "忌食", "忌口", "忌用",
    "禁食", "禁用", "避免", "少吃", "别吃", "不要吃", "不能吃",
)


def export(graph: Neo4jGraph | None = None, dict_dir: str | Path = DICT_DIR,
           dry_run: bool = False) -> dict[str, int]:
    """按标签导出实体词表；返回 ``{文件名: 词数}``。"""
    graph = graph or Neo4jGraph()
    base = Path(dict_dir)
    if not dry_run:
        base.mkdir(parents=True, exist_ok=True)

    counts: dict[str, int] = {}
    for label, filename in LABEL_FILES:
        rows = graph.query(f"MATCH (n:`{label}`) WHERE n.name IS NOT NULL "
                           f"RETURN n.name AS name")
        words = sorted({str(r["name"]).strip() for r in rows if str(r["name"]).strip()})
        counts[filename] = len(words)
        if not dry_run:
            (base / f"{filename}.txt").write_text("\n".join(words) + "\n", encoding="utf-8")

    counts["deny"] = len(DENY_WORDS)
    if not dry_run:
        (base / "deny.txt").write_text("\n".join(DENY_WORDS) + "\n", encoding="utf-8")

    if not dry_run:
        graph.close()
    return counts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="从 Neo4j 图谱导出 dict/*.txt")
    parser.add_argument("--dict-dir", default=DICT_DIR)
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写文件")
    args = parser.parse_args(argv)

    counts = export(dict_dir=args.dict_dir, dry_run=args.dry_run)
    print(f"导出目录：{args.dict_dir}" + ("（dry-run）" if args.dry_run else ""))
    total = 0
    for name, n in counts.items():
        print(f"  {name + '.txt':<18}{n:>7}")
        total += n
    print(f"  {'合计':<16}{total:>7}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
