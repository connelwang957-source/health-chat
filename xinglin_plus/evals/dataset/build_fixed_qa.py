"""构建「固定问答」评测集：从图谱直取真值，自动生成期望答案。

**为什么要自动生成**：固定问答的本质是"可枚举的结构化查询"，真值本来就在图谱里。
手工造 160 条既慢又容易抄错，自动生成可无限扩量、可重复、可随图谱演进重跑。

**独立性（关键）**：真值 Cypher **手写在本文件内**，不 import 生产的
`kg_query_service.build_cypher`。否则代码把关系名写错时（例如曾经把图谱里的
`acompany_with` 写成 `accompany_with`），真值会一起错，评测永远"通过"。

**分层抽样**：按"真值条数"分三层（信息多 / 中 / 少），避免只抽到最热门的那批实体，
让指标能反映长尾表现。

用法::

    python -m evals.dataset.build_fixed_qa          # 默认每类 8 条，共约 160 条
    python -m evals.dataset.build_fixed_qa --per 10
"""

import argparse
import json
import random
from pathlib import Path

from xinglin.application.runtime import get_graph

OUT_PATH = Path(__file__).parent / "fixed_qa.jsonl"
SEED = 20261012          # 固定种子：同一份图谱上重跑得到同一份数据集

# ---- 真值来源（20 类固定问答；关系名以图谱实建为准）--------------------------
# code → (中文名, 锚点标签, 真值 Cypher：返回 e=锚点实体, v=答案值)
TRUTH: dict[int, tuple[str, str, str]] = {
    1: ("疾病—症状", "Disease",
        "MATCH (n:Disease)-[:has_symptom]->(m:Symptom) RETURN n.name AS e, m.name AS v"),
    2: ("症状—疾病", "Symptom",
        "MATCH (m:Disease)-[:has_symptom]->(n:Symptom) RETURN n.name AS e, m.name AS v"),
    3: ("疾病—病因", "Disease",
        "MATCH (n:Disease) WHERE n.cause IS NOT NULL AND n.cause <> '' "
        "RETURN n.name AS e, n.cause AS v"),
    4: ("疾病—预防", "Disease",
        "MATCH (n:Disease) WHERE n.prevent IS NOT NULL AND n.prevent <> '' "
        "RETURN n.name AS e, n.prevent AS v"),
    5: ("疾病—治疗周期", "Disease",
        "MATCH (n:Disease) WHERE n.cure_lasttime IS NOT NULL AND n.cure_lasttime <> '' "
        "RETURN n.name AS e, n.cure_lasttime AS v"),
    6: ("疾病—治疗方式", "Disease",
        "MATCH (n:Disease) WHERE n.cure_way IS NOT NULL RETURN n.name AS e, n.cure_way AS v"),
    7: ("疾病—治愈相关", "Disease",
        "MATCH (n:Disease) WHERE n.cure_prob IS NOT NULL AND n.cure_prob <> '' "
        "RETURN n.name AS e, n.cure_prob AS v"),
    8: ("疾病—易感人群", "Disease",
        "MATCH (n:Disease) WHERE n.easy_get IS NOT NULL AND n.easy_get <> '' "
        "RETURN n.name AS e, n.easy_get AS v"),
    9: ("疾病—描述", "Disease",
        "MATCH (n:Disease) WHERE n.desc IS NOT NULL AND n.desc <> '' "
        "RETURN n.name AS e, n.desc AS v"),
    10: ("疾病—并发症", "Disease",
         "MATCH (n:Disease)-[:acompany_with]->(m:Disease) RETURN n.name AS e, m.name AS v"),
    11: ("疾病—忌吃食品", "Disease",
         "MATCH (n:Disease)-[:no_eat]->(m:Food) RETURN n.name AS e, m.name AS v"),
    12: ("疾病—宜吃食品", "Disease",
         "MATCH (n:Disease)-[:do_eat]->(m:Food) RETURN n.name AS e, m.name AS v"),
    13: ("食品—疾病（限制）", "Food",
         "MATCH (m:Disease)-[:no_eat]->(n:Food) RETURN n.name AS e, m.name AS v"),
    14: ("食品—疾病（推荐）", "Food",
         "MATCH (m:Disease)-[:do_eat]->(n:Food) RETURN n.name AS e, m.name AS v"),
    15: ("疾病—药品", "Disease",
         "MATCH (n:Disease)-[:recommand_drug]->(m:Drug) RETURN n.name AS e, m.name AS v"),
    16: ("药品—疾病", "Drug",
         "MATCH (m:Disease)-[:recommand_drug]->(n:Drug) RETURN n.name AS e, m.name AS v"),
    17: ("疾病—检查", "Disease",
         "MATCH (n:Disease)-[:need_check]->(m:Check) RETURN n.name AS e, m.name AS v"),
    18: ("检查—疾病", "Check",
         "MATCH (m:Disease)-[:need_check]->(n:Check) RETURN n.name AS e, m.name AS v"),
    19: ("疾病—科室", "Disease",
         "MATCH (n:Disease)-[:belongs_to]->(m:Department) RETURN n.name AS e, m.name AS v"),
    20: ("科室—疾病", "Department",
         "MATCH (m:Disease)-[:belongs_to]->(n:Department) RETURN n.name AS e, m.name AS v"),
}

# 问题模板：刻意用不同说法，顺带测意图识别的鲁棒性
QUESTIONS: dict[int, str] = {
    1: "{e}有什么症状？", 2: "{e}可能是什么疾病？", 3: "{e}是什么原因引起的？",
    4: "{e}怎么预防？", 5: "{e}的治疗周期是多久？", 6: "{e}怎么治疗？",
    7: "{e}能治好吗？", 8: "{e}的易感人群是哪些？", 9: "{e}是什么病？",
    10: "{e}有哪些并发症？", 11: "{e}不能吃什么？", 12: "{e}适合吃什么？",
    13: "{e}不适合哪些疾病患者？", 14: "{e}适合哪些疾病患者？",
    15: "{e}用什么药？", 16: "{e}主要用于治疗哪些疾病？",
    17: "{e}需要做哪些检查？", 18: "{e}能查出哪些疾病？",
    19: "{e}应该看什么科？", 20: "{e}主要诊治哪些疾病？",
}

# 判分方式：set=实体集合比召回；text=自由文本比要点命中
TEXT_CODES = frozenset({3, 4, 5, 6, 7, 8, 9})
MAX_VALUES = 10           # 与生产的口径一致（answer_template.DEFAULT_LIMIT）
MAX_TEXT = 200            # 文本类期望值截断长度


def _group(graph, cypher: str) -> dict[str, list[str]]:
    """一次查询取回"锚点实体 → 去重后的真值列表"（避免逐个实体查询）。"""
    grouped: dict[str, list[str]] = {}
    for row in graph.query(cypher):
        entity, value = row.get("e"), row.get("v")
        if not entity or value is None:
            continue
        items = value if isinstance(value, list) else [value]
        texts = [str(i).strip() for i in items]
        texts = [t for t in texts if t and t.lower() != "null"]
        if not texts:
            continue          # 空数组（如 cure_way = []）不建桶，否则会产出"无真值"的用例
        bucket = grouped.setdefault(str(entity), [])
        for text in texts:
            if text not in bucket:
                bucket.append(text)
    return grouped


def _stratified(candidates: list[str], grouped: dict[str, list[str]],
                count: int, rng: random.Random) -> list[str]:
    """按真值条数分三层抽样：信息丰富 / 中等 / 稀疏，各取 1/3。"""
    if len(candidates) <= count:
        return list(candidates)
    ordered = sorted(candidates, key=lambda e: -len(grouped[e]))
    third = max(1, len(ordered) // 3)
    layers = [ordered[:third], ordered[third:2 * third], ordered[2 * third:]]
    per = max(1, count // 3)
    picked: list[str] = []
    for layer in layers:
        picked.extend(rng.sample(layer, min(per, len(layer))))
    rest = [e for e in ordered if e not in picked]
    while len(picked) < count and rest:
        picked.append(rest.pop())
    return picked[:count]


def build(per_type: int = 8) -> list[dict]:
    graph = get_graph()
    rng = random.Random(SEED)
    records: list[dict] = []

    print(f"{'编号':>4}  {'类型':<16} {'锚点':<11} 收录  候选")
    print("-" * 52)
    for code, (cn_name, role, cypher) in TRUTH.items():
        grouped = _group(graph, cypher)
        picked = _stratified(list(grouped), grouped, per_type, rng)
        for entity in picked:
            values = grouped[entity]
            record = {
                "id": f"fx{code:02d}-{entity}",
                "category": "fixed_qa",
                "qa_code": code,
                "qa_name": cn_name,
                "role": role,
                "entity": entity,
                "question": QUESTIONS[code].format(e=entity),
                "expected_mode": "kg",
            }
            if code in TEXT_CODES:
                record |= {"match": "text", "expected_text": values[0][:MAX_TEXT]}
            else:
                # 真值**存全量**（不解 10 条）：答案可能列出远超模板上限的条目，
                # 只存前 10 条会让"答案里的值"全被判成幻觉。
                # expected_total 供判分选择口径——见 run_eval.Judge.fixed。
                record |= {"match": "set", "expected_values": values[:MAX_VALUES],
                           "expected_total": len(values), "expected_all": values}
            records.append(record)
        print(f"{code:>4}  {cn_name:<16} {role:<11} {len(picked):>4}  {len(grouped):>6}")

    print("-" * 52)
    print(f"合计 {len(records)} 条 → {OUT_PATH}")
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="生成固定问答评测集")
    parser.add_argument("--per", type=int, default=8, help="每类条数（默认 8）")
    args = parser.parse_args()

    records = build(args.per)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8")
    print(f"已写入 {OUT_PATH}")


if __name__ == "__main__":
    main()
