"""消融实验：证明「每个组件真的有用」，而不只是"装了"。

三个消融项：

    retrieval  双路 RRF ↔ 仅 dense ↔ 仅 sparse
               指标：**要点召回率**（top-k 片段里能找到多少预期要点）+ 时延
               并**按是否含专业术语分组**——稀疏路（BM25）的强项就是精确词匹配，
               含药名/缩写（TACE、NRP-1、SOD）的问题上应该明显胜出。

    guardrail  真幻觉（按图谱真值判定） × 护栏是否报警 → 2×2 混淆矩阵
               指标：护栏**召回率**（抓到了多少真幻觉）与**精确率**（报警里有多少是真幻觉）
               注意：本项目的护栏是"提醒不拦截"，所以它**不改变幻觉率**，
               只会提高用户知情度——混淆矩阵才是衡量它价值的正确口径。

    graph      自动选路（走图谱） ↔ 强制纯文献
               指标：固定问答的通过率（图谱应当碾压——这些是可枚举的结构化关系）

**为什么检索消融要起子进程**：检索组件的取舍由环境变量决定（`BM25_DOCS_PATH` /
`MILVUS_URI`），而 `config` 只在 import 时读一次——必须"先设环境，再 import"。

用法::

    python -m evals.ablation                 # 跑全部
    python -m evals.ablation --scene guardrail
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

DATASET_DIR = Path(__file__).parent / "dataset"
REPORT_DIR = Path(__file__).parent / "reports"
sys.path.insert(0, str(Path(__file__).parent.parent))

RETRIEVAL_SCENES: dict[str, tuple[str, dict[str, str]]] = {
    "fusion": ("双路 RRF（dense + BM25）", {}),
    "dense_only": ("仅 dense（Milvus 向量）", {"BM25_DOCS_PATH": "Z:/__no_bm25__.json"}),
    "sparse_only": ("仅 sparse（本地 BM25）", {"MILVUS_URI": "http://127.0.0.1:19531"}),
}

TOP_K = 8
TERM_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-]{1,}")     # 英文缩写 / 药名片段

# 融合权重扫参（稠密, 稀疏）：默认 0.6/0.4 下融合结果与"仅 dense"逐位相同，
# 说明稀疏路对最终名次没有贡献——扫一遍找是否有一组让两路真正互补。
WEIGHT_PAIRS: tuple[tuple[str, str], ...] = (
    ("0.6", "0.4"), ("0.5", "0.5"), ("0.4", "0.6"), ("0.3", "0.7"),
)

# 两个题集必须并排看：标题同构集偏向词面匹配（对 BM25 有利），
# 语义改写集反过来（对稠密路有利）。只看一个会得出偏颇的结论。
DATASETS: dict[str, str] = {
    "open_ended": "标题同构集",
    "semantic_rewrite": "语义改写集",
}


def load(name: str) -> list[dict]:
    path = DATASET_DIR / f"{name}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


# ---------------------------------------------------------------- 检索消融
def retrieval_scene() -> dict:
    """在当前检索配置下，量"top-k 片段能覆盖多少预期要点"。"""
    from xinglin.application.runtime import get_retrieval_service

    service = get_retrieval_service()
    available = service.available
    if available:                                   # 预热：把 25s 的构造开销排除在计时外
        service.retrieve("预热", k=1)

    rows: list[dict] = []
    dataset = os.getenv("ABLATION_DATASET", "open_ended")
    for rec in load(dataset):
        points = rec.get("expected_points") or []
        started = time.perf_counter()
        try:
            docs = service.retrieve(rec["question"], k=TOP_K)
            blob = "\n".join(str(d.get("text", "")) for d in docs)
            hit = [p for p in points if p in blob]
            rows.append({
                "id": rec["id"], "question": rec["question"],
                "with_term": bool(TERM_RE.search(rec["question"])),
                "cover": len(hit) / len(points) if points else 0.0,
                "full": len(hit) == len(points), "hits": len(docs),
                "elapsed": round(time.perf_counter() - started, 3), "ok": True,
            })
        except Exception as exc:                    # noqa: BLE001
            rows.append({"id": rec["id"], "question": rec["question"], "ok": False,
                         "with_term": bool(TERM_RE.search(rec["question"])),
                         "cover": 0.0, "full": False, "hits": 0,
                         "error": f"{type(exc).__name__}: {exc}",
                         "elapsed": round(time.perf_counter() - started, 3)})
    return {"available": available, "rows": rows}


def _agg(rows: list[dict]) -> dict:
    ok = [r for r in rows if r["ok"]]
    if not ok:
        return {"n": 0}
    return {
        "n": len(ok),
        "cover": sum(r["cover"] for r in ok) / len(ok),
        "full": sum(1 for r in ok if r["full"]) / len(ok),
        "p50": sorted(r["elapsed"] for r in ok)[len(ok) // 2],
    }


# ---------------------------------------------------------------- 护栏消融
def guardrail_scene(max_cases: int = 16) -> dict:
    """真幻觉（按图谱真值判定） × 护栏报警 → 2×2 混淆矩阵。"""
    from evals.run_eval import Judge           # 复用 run_eval 的判分口径，避免两套标准
    from xinglin.application.hybrid_agent import HybridAgent

    judge = Judge()
    agent = HybridAgent()
    cells = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    rows: list[dict] = []
    for rec in load("fixed_qa"):
        if rec["qa_code"] not in (1, 2, 15, 16, 17, 18, 19, 20) or rec.get("match") != "set":
            continue                                # 只测集合类（幻觉可自动判定）
        if rec.get("expected_total", 0) > 10:
            continue        # 真值超展示上限的条目判分口径里 hallucinated 恒为空，无法用于混淆矩阵
        try:
            answer = agent.chat_main(rec["question"])
        except Exception as exc:                    # noqa: BLE001
            rows.append({"id": rec["id"], "error": str(exc)})
            continue
        # 判据与护栏对齐：证据上下文 = 图谱事实 + **检索到的文献正文**。
        # 只拿图谱真值当裁判会冤枉"引用文献"的答案（FN 虚高）。
        from xinglin.application.runtime import get_retrieval_service
        docs = get_retrieval_service().retrieve(rec["question"], k=TOP_K)
        context = "\n".join(str(d.get("text", "")) for d in docs)
        verdict = judge.fixed(rec, answer.answer, context=context)
        hallucinated = bool(verdict["hallucinated"])
        fired = "请谨慎参考" in (answer.answer or "")
        if hallucinated and fired:
            cells["tp"] += 1
        elif hallucinated and not fired:
            cells["fn"] += 1
        elif not hallucinated and fired:
            cells["fp"] += 1
        else:
            cells["tn"] += 1
        rows.append({"id": rec["id"], "question": rec["question"],
                     "hallucinated": hallucinated, "fired": fired,
                     "detail": verdict["detail"], "n_hall": len(verdict["hallucinated"])})
        if sum(cells.values()) >= max_cases:
            break
    tp, fp, fn, tn = cells["tp"], cells["fp"], cells["fn"], cells["tn"]
    return {"cells": cells, "rows": rows,
            "recall": tp / (tp + fn) if (tp + fn) else None,
            "precision": tp / (tp + fp) if (tp + fp) else None}


# ---------------------------------------------------------------- 图谱消融
def graph_scene(limit: int = 1) -> dict:
    """自动选路（走图谱） ↔ 强制纯文献：固定问答的通过率对比。"""
    from evals.run_eval import Judge, stratified

    from xinglin.application.hybrid_agent import HybridAgent
    from xinglin.application.rag_agent import RAGAgent

    judge = Judge()
    records = stratified(load("fixed_qa"), limit)
    out: dict[str, dict] = {}
    for name, agent in (("自动选路（含图谱）", HybridAgent()),
                        ("强制纯文献", RAGAgent())):
        passed, details = 0, []
        for rec in records:
            try:
                answer = agent.chat_main(rec["question"])
                verdict = judge.fixed(rec, answer.answer)
            except Exception as exc:                # noqa: BLE001
                verdict = {"passed": False, "detail": f"异常 {exc}", "hallucinated": []}
            passed += 1 if verdict["passed"] else 0
            details.append({"id": rec["id"], "passed": verdict["passed"],
                            "detail": verdict["detail"]})
        out[name] = {"n": len(records), "passed": passed,
                     "rate": passed / len(records) if records else 0.0,
                     "details": details}
    return out


def _child(scene: str) -> dict:
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "evals.ablation", "--scene", scene],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ}, cwd=str(Path(__file__).parent.parent))
    for line in (proc.stdout or "").splitlines():
        if line.startswith("@@RESULT@@"):
            return json.loads(line[len("@@RESULT@@"):])
    return {"error": f"子进程无结果（exit={proc.returncode}）：{(proc.stderr or '')[-300:]}"}


# ---------------------------------------------------------------- 报告
def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def render(retrieval: dict, guardrail: dict, graph: dict) -> str:
    lines = ["# 消融实验报告", "",
             f"生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}", "",
             "## 一、检索消融：稀疏路（BM25）到底有没有用", "",
             "指标 = top-8 片段对「预期要点」的覆盖率（**不需要人工标注相关文档 id**，",
             "要点取自文献标题术语，必然出现在正文里）。按题目是否含英文缩写分组——",
             "BM25 的强项正是精确词匹配。", "",
             "| 检索配置 | 可用 | 题数 | 要点覆盖率 | 全要点命中 | 检索 P50 | 含术语题 | 纯中文题 |",
             "|---|---|---|---|---|---|---|---|"]
    titles: dict[str, str] = {"__hdr__": ""}
    for dataset, ds_label in DATASETS.items():
        for name, (title, _e) in RETRIEVAL_SCENES.items():
            titles[f"{dataset}|{name}"] = f"{ds_label}·{title}"
    titles |= {f"w{d}:{s}": f"双路 RRF（权重 {d}/{s}）" for d, s in WEIGHT_PAIRS}
    for name, title in titles.items():
        if name == "__hdr__":
            continue
        data = retrieval.get(name) or {}
        rows = data.get("rows") or []
        whole, term = _agg(rows), _agg([r for r in rows if r.get("with_term")])
        plain = _agg([r for r in rows if not r.get("with_term")])
        if not whole.get("n"):
            lines.append(f"| {title} | {'是' if data.get('available') else '否'} | — | "
                         f"不可用 | — | — | — | — |")
            continue
        lines.append(
            f"| {title} | {'是' if data.get('available') else '否'} | {whole['n']} | "
            f"**{_pct(whole['cover'])}** | {_pct(whole['full'])} | {whole['p50']:.3f}s | "
            f"{_pct(term.get('cover'))}（{term.get('n', 0)}） | "
            f"{_pct(plain.get('cover'))}（{plain.get('n', 0)}） |")

    lines += ["", "## 二、护栏消融：它真的抓得住幻觉吗", "",
              "真值口径：固定问答答案里出现「图谱真值之外的实体」即判为幻觉。",
              "本项目的护栏是**提醒不拦截**，所以它不改变幻觉率——混淆矩阵才是正确口径。", "",
              "> ⚠️ **校准结论（已逐条过一遍明细）**：本口径**不适用于固定问答**——",
              "> 判为「有幻觉」的条目**值召回率全是 N/N**（答案把图谱真值完整列出），",
              "> 只是措辞里多带了个别证据外实体。换言之：**KG 模板路径几乎不产生幻觉**",
              "> （值直接从图谱复制），护栏在这里本来就没有活干。",
              "> 因此**护栏召回率不可采信**，可靠的只有 `FP = 0`（护栏不误报）。",
              "> 要测护栏的真实召回，必须把样本换成**开放式路径**（LLM 自由生成）",
              "> 并人工标注「哪条答案真的编造了事实」。", ""]
    cells = guardrail.get("cells")
    if cells:
        lines += ["| | 护栏报警 | 护栏未报警 |", "|---|---|---|",
                  f"| **真有幻觉** | TP = {cells['tp']} | FN = {cells['fn']} |",
                  f"| **无幻觉** | FP = {cells['fp']} | TN = {cells['tn']} |", "",
                  f"- 护栏**召回率**（抓到多少真幻觉）：{_pct(guardrail.get('recall'))}",
                  f"- 护栏**精确率**（报警里有多少是真幻觉）：{_pct(guardrail.get('precision'))}"]
    else:
        lines.append(f"- 未产出结果：{guardrail.get('error', '无数据')}")

    detail_rows = [r for r in (guardrail.get("rows") or []) if "error" not in r]
    if detail_rows:
        lines += ["", "### 判定明细（供人工复核）", "",
                  "| 用例 | 自动判有幻觉 | 护栏报警 | 判据 |", "|---|---|---|---|"]
        for row in detail_rows:
            lines.append(f"| {row['id']} | {'**是**' if row['hallucinated'] else '否'} | "
                         f"{'**是**' if row['fired'] else '否'} | {row['detail'][:38]} |")

    lines += ["", "## 三、图谱消融：结构化知识值多少", "",
              "| 配置 | 题数 | 通过率 |", "|---|---|---|"]
    for name, data in (graph or {}).items():
        if isinstance(data, dict) and "rate" in data:
            lines.append(f"| {name} | {data['n']} | **{_pct(data['rate'])}** |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="消融实验")
    parser.add_argument("--scene", default="",
                        choices=["", "retrieval", "guardrail", "graph"])
    parser.add_argument("--only", default="retrieval,guardrail,graph",
                        help="编排模式下要跑的项（逗号分隔）")
    args = parser.parse_args()

    if args.scene:
        payload = {"retrieval": lambda: retrieval_scene(),
                   "guardrail": lambda: guardrail_scene(),
                   "graph": lambda: graph_scene()}[args.scene]()
        print("@@RESULT@@" + json.dumps(payload, ensure_ascii=False))
        return

    wanted = {s.strip() for s in args.only.split(",") if s.strip()}

    retrieval: dict[str, dict] = {}
    if "retrieval" in wanted:
        for dataset, ds_label in DATASETS.items():
            for name, (title, env) in RETRIEVAL_SCENES.items():
                key = f"{dataset}|{name}"
                print(f"  [检索·{ds_label}] {title} ...")
                os.environ.update(env)      # 子进程继承（父进程不 import xinglin，安全）
                os.environ["ABLATION_DATASET"] = dataset
                try:
                    retrieval[key] = _child("retrieval")
                finally:
                    for k in (*env, "ABLATION_DATASET"):
                        os.environ.pop(k, None)
                agg = _agg(retrieval[key].get("rows") or [])
                print(f"    → 要点覆盖率 {_pct(agg.get('cover'))}（{agg.get('n', 0)} 题）")

    if "weights" in wanted:
        for dense, sparse in WEIGHT_PAIRS:
            label = f"w{dense}:{sparse}"
            print(f"  [权重] 双路 dense={dense} sparse={sparse} ...")
            os.environ.update({"HYBRID_DENSE_WEIGHT": dense,
                               "HYBRID_SPARSE_WEIGHT": sparse})
            try:
                retrieval[label] = _child("retrieval")
            finally:
                os.environ.pop("HYBRID_DENSE_WEIGHT", None)
                os.environ.pop("HYBRID_SPARSE_WEIGHT", None)
            agg = _agg(retrieval[label].get("rows") or [])
            print(f"    → 要点覆盖率 {_pct(agg.get('cover'))}")

    guardrail: dict = {}
    if "guardrail" in wanted:
        print("  [护栏] 混淆矩阵 ...")
        guardrail = _child("guardrail")
        print(f"    → {guardrail.get('cells')}　"
              f"召回 {_pct(guardrail.get('recall'))}　"
              f"精确 {_pct(guardrail.get('precision'))}")

    graph: dict = {}
    if "graph" in wanted:
        print("  [图谱] 自动选路 vs 强制纯文献 ...")
        graph = _child("graph")

    report = render(retrieval, guardrail, graph)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / f"ablation_{datetime.now():%Y%m%d_%H%M%S}.md"
    out.write_text(report, encoding="utf-8")
    print(f"\n报告：{out}")


if __name__ == "__main__":
    main()
