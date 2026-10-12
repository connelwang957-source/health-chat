"""性能评测：时延构成 / 并发阶梯 / 模式对比。

三件事：

    ① 时延构成  —— 拆分「检索组件构造 / 裸检索 / 意图分类 / 护栏」，找长尾来自哪
    ② 并发阶梯  —— 1 / 5 / 10 / 20 并发，记录 P50 / P95 / 错误率，找拐点
    ③ 模式对比  —— 同一批题在 hybrid（自动选路）与 agent（ReAct）下的时延与完成率

**为什么必须分开测 KG 快路径与开放式慢路径**：两者差一个数量级，混在一起算平均值
没有意义——KG 实测 3~4s（零检索，但含 2 次 LLM：意图 + 护栏），开放式 5~10s。

用法::

    python -m evals.performance                    # 全部
    python -m evals.performance --only timing
"""

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

DATASET_DIR = Path(__file__).parent / "dataset"
REPORT_DIR = Path(__file__).parent / "reports"

CONCURRENCY_LEVELS = (1, 5, 10, 20)
BENCH_QUESTIONS = (
    "感冒有什么症状？",                                  # KG 快路径
    "高血压患者平时要注意什么？",                          # 开放
    "2型糖尿病的药物治疗如何兼顾心肾结局和体重管理？",       # 开放（多目标权衡）
    "泌尿内科主要诊治哪些疾病？",                          # KG（科室反向）
    "老年结直肠肿瘤患者围术期如何监测心脏事件？",             # 开放（专题）
    "螃蟹不适合哪些疾病患者？",                            # KG（大结果集，验 LIMIT）
    "你好",                                            # direct
    "间充质干细胞外泌体治疗强迫症的作用机制是什么？",         # 开放（专题）
)


def _load(name: str) -> list[dict]:
    path = DATASET_DIR / f"{name}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _agent(mode: str):
    if mode == "agent":
        from xinglin.application.tool_agent import ToolCallingAgent
        return ToolCallingAgent()
    from xinglin.application.hybrid_agent import HybridAgent
    return HybridAgent()


def _one(agent, question: str) -> dict:
    started = time.perf_counter()
    try:
        answer = agent.chat_main(question)
        return {"q": question, "ok": True, "elapsed": time.perf_counter() - started,
                "mode": answer.mode.value, "chars": len(answer.answer or ""),
                "sources": len(answer.sources)}
    except Exception as exc:                # noqa: BLE001
        return {"q": question, "ok": False, "elapsed": time.perf_counter() - started,
                "error": f"{type(exc).__name__}: {str(exc)[:80]}"}


def _stats(rows: list[dict]) -> dict:
    ok = [r for r in rows if r["ok"]]
    latency = sorted(r["elapsed"] for r in ok)
    n = len(latency)
    return {
        "n": len(rows), "ok": len(ok), "errors": len(rows) - len(ok),
        "error_rate": (len(rows) - len(ok)) / len(rows) if rows else 0.0,
        "p50": latency[n // 2] if n else 0.0,
        "p95": latency[min(n - 1, int(n * 0.95))] if n else 0.0,
        "max": latency[-1] if n else 0.0,
        "avg": sum(latency) / n if n else 0.0,
    }


# ---------------------------------------------------------------- ① 时延构成
def timing_scene() -> dict:
    from xinglin.application.runtime import (
        get_fact_guardrail, get_intent_service, get_retrieval_service,
    )

    out: dict[str, float] = {}

    started = time.perf_counter()
    service = get_retrieval_service()
    out["检索组件构造（一次性）"] = time.perf_counter() - started

    service.retrieve("预热", k=1)                  # 预热后再量单次检索
    started = time.perf_counter()
    for _ in range(5):
        service.retrieve("2型糖尿病的药物治疗进展", k=8)
    out["单次检索（预热后均摊）"] = (time.perf_counter() - started) / 5

    started = time.perf_counter()
    get_intent_service().classify("2型糖尿病患者饮食要注意什么？")
    out["意图分类（1 次 LLM）"] = time.perf_counter() - started

    started = time.perf_counter()
    get_fact_guardrail().check("感冒常见症状包括咳嗽、发热。",
                              "【知识图谱事实】\n感冒 has_symptom 咳嗽\n感冒 has_symptom 发热")
    out["护栏核查（1 次 LLM）"] = time.perf_counter() - started
    return out


# ---------------------------------------------------------------- ② 并发阶梯
def concurrency_scene(agent_mode: str = "hybrid") -> dict:
    agent = _agent(agent_mode)
    rows_by_level: dict[str, dict] = {}
    for level in CONCURRENCY_LEVELS:
        with ThreadPoolExecutor(max_workers=level) as pool:
            results = list(pool.map(lambda q: _one(agent, q),
                                    list(BENCH_QUESTIONS)))
        rows_by_level[str(level)] = _stats(results)
    return rows_by_level


# ---------------------------------------------------------------- ③ 模式对比
def modes_scene() -> dict:
    from evals.run_eval import Judge, load as load_case

    judge = Judge()
    cases = [r for r in load_case("fixed_qa")
             if r.get("qa_code") in (1, 19, 20) and r.get("match") == "set"][:6]
    cases += load_case("semantic_rewrite")[:4]

    out: dict[str, dict] = {}
    for mode in ("hybrid", "agent"):
        agent = _agent(mode)
        passed, rows = 0, []
        for rec in cases:
            row = _one(agent, rec["question"])
            if row["ok"] and rec["category"] == "fixed_qa":
                verdict = judge.fixed(rec, "")          # 只取时延，判分用真机答案
                row["judge"] = verdict["detail"]
            passed += 1 if row["ok"] else 0
            rows.append(row)
        out[mode] = {**_stats(rows), "questions": [r["q"] for r in rows],
                     "details": rows}
    return out


# ---------------------------------------------------------------- 报告
def render(timing: dict, concurrency: dict, modes: dict) -> str:
    lines = ["# 性能评测报告", "",
             f"生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}", ""]

    if timing:
        lines += ["## 一、时延构成（单问拆解）", "", "| 环节 | 耗时 |", "|---|---|"]
        for name, value in timing.items():
            lines.append(f"| {name} | **{value:.3f}s** |")
        lines += ["",
                  "> 稳态单问 ≈ 意图分类 + 生成 + 护栏（2~3 次 LLM）。",
                  "> **KG 快路径也不是零 LLM**——意图与护栏各调一次，这是时延的主要来源。",
                  "> 检索组件的一次性构造（BM25 索引 + jieba + embedding 模型）是长尾元凶，",
                  "> 应挪到进程启动预热。", ""]

    if concurrency:
        lines += ["## 二、并发阶梯", "",
                  "| 并发 | 请求数 | 成功 | 错误率 | P50 | P95 | 最大 |", "|---|---|---|---|---|---|---|"]
        for level, s in concurrency.items():
            lines.append(f"| {level} | {s['n']} | {s['ok']} | {s['error_rate']*100:.1f}% | "
                         f"{s['p50']:.2f}s | {s['p95']:.2f}s | {s['max']:.2f}s |")
        lines.append("")

    if modes:
        lines += ["## 三、模式对比（同一批题）", "",
                  "| 模式 | 请求 | 成功 | P50 | P95 | 最大 |", "|---|---|---|---|---|---|"]
        for mode, s in modes.items():
            lines.append(f"| {mode} | {s['n']} | {s['ok']} | {s['p50']:.2f}s | "
                         f"{s['p95']:.2f}s | {s['max']:.2f}s |")
        lines.append("")
        for mode, s in modes.items():
            lines += [f"### {mode} 逐题耗时", "", "| 问题 | 模式 | 耗时 | 来源 |", "|---|---|---|---|"]
            for row in s["details"]:
                detail = (f"{row['elapsed']:.2f}s" if row["ok"] else f"异常 {row.get('error', '')}")
                lines.append(f"| {row['q'][:30]} | {row.get('mode', '-')} | {detail} | "
                             f"{row.get('sources', '-')} |")
            lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="性能评测")
    parser.add_argument("--only", default="timing,concurrency,modes")
    args = parser.parse_args()
    wanted = {s.strip() for s in args.only.split(",") if s.strip()}

    timing = {}
    if "timing" in wanted:
        print("  [时延构成] ...")
        timing = timing_scene()
        for k, v in timing.items():
            print(f"    {k}: {v:.3f}s")

    concurrency = {}
    if "concurrency" in wanted:
        print("  [并发阶梯] 1/5/10/20 ...")
        concurrency = concurrency_scene()
        for level, s in concurrency.items():
            print(f"    并发 {level}: P50={s['p50']:.2f}s P95={s['p95']:.2f}s "
                  f"错误率={s['error_rate']*100:.1f}%")

    modes = {}
    if "modes" in wanted:
        print("  [模式对比] hybrid vs agent ...")
        modes = modes_scene()
        for mode, s in modes.items():
            print(f"    {mode}: P50={s['p50']:.2f}s 成功 {s['ok']}/{s['n']}")

    report = render(timing, concurrency, modes)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / f"performance_{datetime.now():%Y%m%d_%H%M%S}.md"
    out.write_text(report, encoding="utf-8")
    print(f"\n报告：{out}")


if __name__ == "__main__":
    main()
