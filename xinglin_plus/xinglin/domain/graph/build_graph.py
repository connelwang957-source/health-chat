"""知识图谱离线建库（对应《项目开发指导》§4.1 的 `MedicalGraph` / `create_graphnodes_and_graphrels`）。

把种子数据 `data/medical.json`（每行一个疾病对象，JSONL）解析成**节点 + 关系**并写入 Neo4j：

    7 类节点：Disease / Symptom / Drug / Food / Check / Department / Producer
    10 类关系：has_symptom / acompany_with / no_eat / do_eat / recommand_eat /
              recommand_drug / command_drug / need_check / belongs_to / drugs_of

安全默认：**不加 `--write` 只做干跑统计**，绝不写库；写入统一用 ``MERGE``，可重复执行（幂等）。

用法（项目根目录）::

    python -m xinglin.domain.graph.build_graph                # 干跑：统计节点/关系
    python -m xinglin.domain.graph.build_graph --limit 100    # 干跑前 100 条
    python -m xinglin.domain.graph.build_graph --write        # 真正落库
"""

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Iterator

from xinglin.config import MEDICAL_DATA_PATH, NEO4J_CONFIG

DISEASE = "Disease"
DRUG, PRODUCER, DRUGS_OF = "Drug", "Producer", "drugs_of"

# 疾病属性（源字段 → 图谱属性名；cured_prob 统一改名为 cure_prob）
PROP_FIELDS: dict[str, str] = {
    "desc": "desc", "cause": "cause", "prevent": "prevent",
    "cure_lasttime": "cure_lasttime", "easy_get": "easy_get",
    "cure_way": "cure_way", "cured_prob": "cure_prob",
    "cost_money": "cost_money", "get_way": "get_way",
}

# 疾病 → 目标节点的关系（源字段, 关系名, 目标标签）
REL_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("symptom", "has_symptom", "Symptom"),
    ("acompany", "acompany_with", "Disease"),
    ("not_eat", "no_eat", "Food"),
    ("do_eat", "do_eat", "Food"),
    ("recommand_eat", "recommand_eat", "Food"),
    ("recommand_drug", "recommand_drug", "Drug"),
    ("common_drug", "command_drug", "Drug"),
    ("check", "need_check", "Check"),
    ("cure_department", "belongs_to", "Department"),
)

# 第 10 类关系：药品 → 厂商（源字段 drug_detail，格式「品牌名(通用名)」）
DRUG_DETAIL_FIELD = "drug_detail"

NODE_CYPHER = "UNWIND $rows AS row MERGE (n:`{label}` {{name: row.name}}) SET n += row.props"
REL_CYPHER = ("UNWIND $rows AS row MATCH (a:`{src}` {{name: row.src}}) "
              "MERGE (b:`{dst}` {{name: row.dst}}) MERGE (a)-[:`{rel}`]->(b)")


def _as_text(value) -> str:
    """列表 → 「、」拼接；标量 → str；空值 → 空串。"""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "、".join(str(x).strip() for x in value if str(x).strip())
    return str(value).strip()


def parse_drug_detail(item: str) -> tuple[str, str] | None:
    """``品牌名(通用名)`` → ``(通用名, 品牌名)``；无法解析返回 None。"""
    text = (item or "").strip()
    if not text:
        return None
    if "(" in text and text.endswith(")"):
        producer, _, generic = text.partition("(")
        return (generic[:-1].strip() or producer.strip(), producer.strip())
    return (text, text)


def parse_disease(obj: dict) -> tuple[dict, list[dict]]:
    """源记录 → ``(疾病属性, 关系行列表)``；关系行为 ``{src_label,src,rel,dst_label,dst}``。"""
    name = (obj.get("name") or "").strip()
    if not name:
        return {}, []

    props = {"name": name}
    for src, dst in PROP_FIELDS.items():
        text = _as_text(obj.get(src))
        if text:
            props[dst] = text

    rels: list[dict] = []
    for src, rel, label in REL_FIELDS:
        for item in obj.get(src) or []:
            target = str(item).strip()
            if target and target != name:
                rels.append({"src_label": DISEASE, "src": name, "rel": rel,
                             "dst_label": label, "dst": target})

    for item in obj.get(DRUG_DETAIL_FIELD) or []:
        if (parsed := parse_drug_detail(str(item))) is None:
            continue
        generic, producer = parsed
        rels.append({"src_label": DRUG, "src": generic, "rel": DRUGS_OF,
                     "dst_label": PRODUCER, "dst": producer})
    return props, rels


def iter_diseases(path: Path, limit: int | None = None) -> Iterator[dict]:
    """逐行读取 JSONL（大文件不整载入内存）。"""
    with path.open(encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if limit is not None and i >= limit:
                break
            line = line.strip()
            if line:
                yield json.loads(line)


def load(path: Path, limit: int | None = None) -> tuple[list[dict], list[dict]]:
    """返回 ``(节点行, 关系行)``。

    节点按 ``(标签, 名称)`` 去重：疾病节点带完整属性，其余节点只带 ``name``
    （MERGE 幂等，重复只会多写一次而不会产生重复节点）。
    """
    nodes: dict[tuple[str, str], dict] = {}
    rels: list[dict] = []
    for obj in iter_diseases(path, limit):
        props, items = parse_disease(obj)
        if not props:
            continue
        nodes[(DISEASE, props["name"])] = {
            "label": DISEASE, "name": props["name"], "props": props}
        for r in items:
            rels.append(r)
            if r["src_label"] != DISEASE:          # 疾病端已在上方建好
                nodes.setdefault((r["src_label"], r["src"]),
                                 {"label": r["src_label"], "name": r["src"],
                                  "props": {"name": r["src"]}})
            nodes.setdefault((r["dst_label"], r["dst"]),
                             {"label": r["dst_label"], "name": r["dst"],
                              "props": {"name": r["dst"]}})
    return list(nodes.values()), rels


def summarize(nodes: list[dict], rels: list[dict]) -> dict[str, int]:
    stats = Counter(f"node:{n['label']}" for n in nodes)
    stats.update(f"rel:{r['rel']}" for r in rels)
    return dict(stats)


class MedicalGraph:
    """medical.json → Neo4j 的离线建图器。"""

    def __init__(self, config: dict | None = None, data_path: str | None = None):
        self.config = config or NEO4J_CONFIG
        self.data_path = Path(data_path or MEDICAL_DATA_PATH)
        self._driver = None

    @property
    def driver(self):
        """惰性建立驱动（导入时不连库，方便干跑与单测）。"""
        if self._driver is None:
            from neo4j import GraphDatabase
            self._driver = GraphDatabase.driver(
                self.config["uri"],
                auth=(self.config["user"], self.config["password"]),
                connection_timeout=5)
        return self._driver

    # -- 主流程 -------------------------------------------------------------
    def create_graphnodes_and_graphrels(self, limit: int | None = None,
                                        write: bool = False, batch: int = 500
                                        ) -> dict[str, int]:
        """读 JSON → 建 7 类节点 → 建 10 类关系；``write=False`` 时只统计不落库。"""
        nodes, rels = load(self.data_path, limit)
        if not write:
            return summarize(nodes, rels)
        return self._write(nodes, rels, batch)

    def _write(self, nodes: list[dict], rels: list[dict], batch: int) -> dict[str, int]:
        """MERGE 幂等写入：节点按标签分组、关系按 (起点, 关系, 终点) 分组。"""
        counts: Counter = Counter()
        try:
            with self.driver.session(database=self.config["database"]) as session:
                by_label: dict[str, list[dict]] = {}
                for n in nodes:
                    by_label.setdefault(n["label"], []).append(n)
                for label, rows in by_label.items():
                    for i in range(0, len(rows), batch):
                        chunk = rows[i:i + batch]
                        session.run(NODE_CYPHER.format(label=label), rows=chunk)
                        counts[f"node:{label}"] += len(chunk)

                by_rel: dict[tuple[str, str, str], list[dict]] = {}
                for r in rels:
                    by_rel.setdefault((r["src_label"], r["rel"], r["dst_label"]), []).append(r)
                for (src, rel, dst), rows in by_rel.items():
                    for i in range(0, len(rows), batch):
                        chunk = rows[i:i + batch]
                        session.run(REL_CYPHER.format(src=src, rel=rel, dst=dst), rows=chunk)
                        counts[f"rel:{rel}"] += len(chunk)
        finally:
            self.close()
        return dict(counts)

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="medical.json → Neo4j 离线建图")
    ap.add_argument("--input", default=str(MEDICAL_DATA_PATH), help="medical.json 路径")
    ap.add_argument("--limit", type=int, default=None, help="只处理前 N 条疾病")
    ap.add_argument("--write", action="store_true", help="真正落库（默认只干跑统计）")
    args = ap.parse_args(argv)

    path = Path(args.input)
    if not path.exists():
        print(f"[错误] 数据源不存在：{path}")
        return 1

    graph = MedicalGraph(data_path=str(path))
    stats = graph.create_graphnodes_and_graphrels(limit=args.limit, write=args.write)
    print(f"解析完成：源={path.name}，limit={args.limit or '全部'}")
    for key, n in sorted(stats.items()):
        print(f"  {key:<28}{n}")

    if not args.write:
        print("\n[干跑] 未写入数据库；确认无误后加 --write 落库（MERGE 幂等）")
        return 0
    print(f"\n[写入完成] {NEO4J_CONFIG['uri']} / {NEO4J_CONFIG['database']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
