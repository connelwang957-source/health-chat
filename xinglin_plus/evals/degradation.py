"""降级与容错测试（对应需求 12.1~12.6、FR-026）。

架构里到处写着"降级不阻断"，那就逐个把依赖拉闸，验证承诺是否成立：

    停 Neo4j            → hybrid 退化为纯文献，direct 仍可用
    停 Milvus + 无 BM25 → hybrid 退化为纯图谱
    清空 LLM Key        → 意图走规则通道、生成走模板（最狠的一条）
    停 Redis            → 问答照常，只是没有缓存加速
    护栏 LLM 超时       → fail-open 放行，答案正常返回
    护栏 LLM 返回乱码   → 判"跳过"，生成照常

**统一判据**：服务仍能给出非空回答、不抛异常，且如实反映能力下降
（状态/可靠性级别变化）。

**为什么用"改环境变量"而不是 `docker stop`**：
① 依赖端口可配置（`NEO4J_URI` / `MILVUS_URI` / `REDIS_URL` / `BM25_DOCS_PATH`），
指向一个没人监听的端口即可，零副作用、可重复、可在 CI 跑；
② 停容器会连带影响别人在本机跑的其它服务。

**每个场景跑在独立子进程**：环境变量只在 import 时被 `config` 读一次，
同进程内改环境对已加载的模块无效——必须"先设环境，再 import"。

用法::

    python -m evals.degradation              # 跑全部 6 个场景 + 出报告
    python -m evals.degradation --scene no_api_key   # 只跑一个（供调试）
"""

import argparse
import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

REPORT_DIR = Path(__file__).parent / "reports"

# 覆盖三种通路：kg（模板）/ direct（寒暄）/ 开放式（双路或纯文献）
PROBE_QUESTIONS = (
    "感冒有什么症状？",
    "你好",
    "2型糖尿病患者日常应该怎么控制血糖？",
)

# 场景 → (标题, 拉闸方式, 期望行为)
SCENES: dict[str, tuple[str, str, str]] = {
    "neo4j_down": (
        "停 Neo4j",
        "NEO4J_URI 指向无人监听的端口",
        "hybrid 退化为纯文献；direct 仍可用；不抛异常",
    ),
    "milvus_bm25_down": (
        "停 Milvus 且无 BM25 语料",
        "MILVUS_URI 指向坏端口 + BM25_DOCS_PATH 指向不存在文件",
        "hybrid 退化为纯图谱；不抛异常",
    ),
    "no_api_key": (
        "LLM Key 失效（清空）",
        "LLM_API_KEY 置为无效值",
        "意图走规则通道、生成走模板回答；仍能回答（最狠的一条）",
    ),
    "redis_down": (
        "停 Redis",
        "REDIS_URL 指向坏端口",
        "问答照常，缓存读写不抛异常（只是没有加速）",
    ),
    "guardrail_timeout": (
        "护栏 LLM 超时",
        "注入一个必抛 TimeoutError 的护栏",
        "fail-open 放行，答案正常返回",
    ),
    "guardrail_bad_json": (
        "护栏 LLM 返回非法 JSON",
        "注入一个返回普通文本的护栏",
        "判『跳过核查』，生成照常",
    ),
}


class _BrokenLLM:
    """护栏专用的坏 LLM：按场景抛异常或返回非 JSON。"""

    available = True

    def __init__(self, mode: str):
        self.mode = mode

    def complete(self, system: str, user: str,
                 temperature: float = 0.0, max_tokens: int = 2048) -> str:
        if self.mode == "timeout":
            raise TimeoutError("模拟护栏 LLM 超时")
        return "这不是 JSON，只是一段普通文本。"


def scene_env(scene: str) -> dict[str, str]:
    """把依赖"拉闸"——指向无人监听的端口 / 无效凭据。"""
    if scene == "neo4j_down":
        return {"NEO4J_URI": "neo4j://127.0.0.1:7699"}
    if scene == "milvus_bm25_down":
        return {"MILVUS_URI": "http://127.0.0.1:19531",
                "BM25_DOCS_PATH": str(Path("Z:/__no_such_bm25__.json"))}
    if scene == "no_api_key":
        return {"LLM_API_KEY": "invalid-key-for-degradation-test",
                "DEEPSEEK_API_KEY": "invalid-key-for-degradation-test"}
    if scene == "redis_down":
        return {"REDIS_URL": "redis://127.0.0.1:6399/0"}
    return {}


def _agent_kwargs(scene: str) -> dict:
    """护栏场景用**构造注入**替换护栏，其余场景不干预。"""
    if scene in ("guardrail_timeout", "guardrail_bad_json"):
        from xinglin.domain.guardrail.fact_guardrail import FactGuardrail
        mode = "timeout" if scene == "guardrail_timeout" else "bad_json"
        return {"guardrail": FactGuardrail(_BrokenLLM(mode))}
    return {}


def run_scene(scene: str) -> dict:
    """在**已设好环境变量**的进程里跑问题集（调用方负责"先设环境再 import"）。"""
    from xinglin.application.hybrid_agent import HybridAgent

    rows: list[dict] = []

    if scene == "redis_down":
        rows.append(_probe_cache())

    agent = HybridAgent(**_agent_kwargs(scene))
    for question in PROBE_QUESTIONS:
        started = time.perf_counter()
        try:
            answer = agent.chat_main(question)
            rows.append({
                "kind": "qa", "question": question, "ok": True,
                "mode": answer.mode.value, "status": answer.status,
                "reliability": answer.reliability.value,
                "chars": len(answer.answer or ""), "sources": len(answer.sources),
                "elapsed": round(time.perf_counter() - started, 2),
            })
        except Exception as exc:                # noqa: BLE001 —— 这里就是要抓"崩没崩"
            # 只留**我们自己的**帧——openai SDK 内部的帧对定位没帮助
            frames = [f for f in traceback.extract_tb(exc.__traceback__)
                      if "site-packages" not in f.filename.replace("\\", "/")]
            where = " ← ".join(f"{Path(f.filename).name}:{f.lineno}({f.name})"
                               for f in frames[-4:]) or "（全部在第三方库内）"
            rows.append({
                "kind": "qa", "question": question, "ok": False,
                "error": f"{type(exc).__name__}: {str(exc)[:120]}", "where": where,
                "elapsed": round(time.perf_counter() - started, 2),
            })
    return {"scene": scene, "rows": rows}


def _probe_cache() -> dict:
    """Redis 拉闸时，缓存读写应"静默降级"而不是抛异常。"""
    from xinglin.application.runtime import get_cache_service

    cache = get_cache_service()
    try:
        hit = cache.get("降级测试问题", "hybrid")
        cache.put("降级测试问题", {"probe": True}, "hybrid")
        return {"kind": "cache", "ok": True, "question": "缓存读写",
                "mode": "-", "status": f"get={'hit' if hit else 'miss'}",
                "reliability": "-", "chars": 0, "sources": 0, "elapsed": 0.0}
    except Exception as exc:                    # noqa: BLE001
        return {"kind": "cache", "ok": False, "question": "缓存读写",
                "error": f"{type(exc).__name__}: {exc}", "elapsed": 0.0}


def verdict(rows: list[dict]) -> tuple[str, str]:
    """判据：不抛异常 + 非空回答；并报告"能力下降是否被如实反映"。"""
    broken = [r for r in rows if not r["ok"]]
    if broken:
        return "FAIL", f"抛异常：{broken[0]['error']}"
    empty = [r for r in rows if r.get("kind") == "qa" and r["chars"] == 0]
    if empty:
        return "FAIL", f"空答案：{empty[0]['question']}"

    qa = [r for r in rows if r.get("kind") == "qa"]
    degraded = [r for r in qa if r["status"] != "ok" or r["reliability"] == "low"]
    note = f"{len(qa) - len(degraded)}/{len(qa)} 条正常作答"
    if degraded:
        reasons = sorted({f"status={r['status']}/reliability={r['reliability']}"
                          for r in degraded})
        note += f"，{len(degraded)} 条如实反映能力下降（{'；'.join(reasons)}）"
    return "PASS", note


def _run_child(scene: str) -> dict:
    """子进程跑单个场景，避免环境变量串味。"""
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "evals.degradation", "--scene", scene],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ}, cwd=str(Path(__file__).parent.parent),
    )
    for line in (proc.stdout or "").splitlines():
        if line.startswith("@@RESULT@@"):
            return json.loads(line[len("@@RESULT@@"):])
    return {"scene": scene, "rows": [],
            "error": f"子进程未返回结果（exit={proc.returncode}）：{(proc.stderr or '')[-300:]}"}


def render(results: dict[str, dict]) -> str:
    lines = [
        f"# 降级与容错测试报告（需求 12.1~12.6 / FR-026）", "",
        f"生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}", "",
        "**统一判据**：服务仍能给出非空回答、不抛异常，且如实反映能力下降。", "",
        "| 场景 | 拉闸方式 | 结果 | 说明 | 实测通路 | 耗时 |",
        "|---|---|---|---|---|---|",
    ]
    for scene, (title, how, _expect) in SCENES.items():
        result = results.get(scene) or {}
        rows = result.get("rows") or []
        state, note = verdict(rows) if rows else ("FAIL", result.get("error", "无结果"))
        qa = [r for r in rows if r.get("kind") == "qa"]
        modes = " / ".join(f"{r.get('mode', 'ERR')}({r.get('chars', 0)}字)" for r in qa)
        elapsed = " / ".join(f"{r['elapsed']}s" for r in qa)
        lines.append(f"| {'✅' if state == 'PASS' else '❌'} {title} | {how} | **{state}** | "
                     f"{note} | {modes} | {elapsed} |")

    lines += ["", "## 逐场景明细", ""]
    for scene, (title, _how, expect) in SCENES.items():
        rows = (results.get(scene) or {}).get("rows") or []
        lines.append(f"### {title}")
        lines.append(f"- 期望：{expect}")
        for row in rows:
            if row.get("kind") == "cache":
                lines.append(f"  - [缓存] {'OK' if row['ok'] else 'FAIL'} "
                             f"{row.get('status') or row.get('error')}")
            else:
                detail = (f"mode={row['mode']} status={row['status']} "
                          f"reliability={row['reliability']} {row['chars']}字 "
                          f"{row['elapsed']}s") if row["ok"] else \
                    f"异常：{row['error']}　位置：{row.get('where', '?')}"
                lines.append(f"  - [{row['question']}] {detail}")
        lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="降级与容错测试")
    parser.add_argument("--scene", default="", help="只跑单个场景（内部使用）")
    args = parser.parse_args()

    if args.scene:
        os.environ.update(scene_env(args.scene))      # 必须在 import xinglin 之前
        print("@@RESULT@@" + json.dumps(run_scene(args.scene), ensure_ascii=False))
        return

    print(f"开始降级测试：{len(SCENES)} 个场景\n")
    results: dict[str, dict] = {}
    for scene, (title, how, _expect) in SCENES.items():
        print(f"  [{title}] {how} ...")
        results[scene] = _run_child(scene)
        state, note = verdict(results[scene]["rows"]) if results[scene]["rows"] \
            else ("FAIL", results[scene].get("error", "无结果"))
        print(f"    → {state}：{note}")

    report = render(results)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / f"degradation_{datetime.now():%Y%m%d_%H%M%S}.md"
    out.write_text(report, encoding="utf-8")

    passed = sum(1 for s in SCENES if verdict((results[s].get("rows") or []))[0] == "PASS")
    print(f"\n通过 {passed}/{len(SCENES)} 个场景")
    print(f"报告：{out}")


if __name__ == "__main__":
    main()
