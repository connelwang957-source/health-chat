"""接口层：统一命令行入口（对应文档 §5.2 的 `xinglin/interfaces/cli.py`）。

用法（在项目根目录运行）::

    python main.py                       # 默认 hybrid 双路融合
    python main.py --mode rag            # 仅 RAG 召回
    python main.py --mode nl2cypher      # 仅图谱（模板 → NL2Cypher → 规则兜底）
    python main.py --mode agent          # 工具调用 ReAct Agent
    python main.py --cache               # 用 Redis 缓存包裹问答结果

Agent 与缓存都**延迟导入/按需装配**，避免加载用不到的重量级依赖。
"""

import argparse
import json
import sys

from xinglin.domain.entities import Answer

MODES = ("hybrid", "rag", "nl2cypher", "agent")
QUIT_WORDS = ("q", "quit", "exit")
MODE_LABELS = {
    "hybrid": "双路融合（图谱 + 文献，默认）",
    "rag": "仅文献（稠密 + BM25 → RRF）",
    "nl2cypher": "仅图谱（模板 → NL2Cypher → 规则兜底）",
    "agent": "工具调用 ReAct（LLM 自主决策）",
}


def _force_utf8_stdout() -> None:
    """Windows GBK 控制台输出中文会乱码，尽量切到 UTF-8（仅显示层）。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:      # noqa: BLE001
            pass


def _build_agent(mode: str):
    """按模式延迟导入并实例化对应 Agent（避免加载用不到的重量级依赖）。"""
    if mode == "hybrid":
        from xinglin.application.hybrid_agent import HybridAgent
        return HybridAgent()
    if mode == "rag":
        from xinglin.application.rag_agent import RAGAgent
        return RAGAgent()
    if mode == "nl2cypher":
        from xinglin.application.nl2cypher_agent import NL2CypherAgent
        return NL2CypherAgent()
    if mode == "agent":
        from xinglin.application.tool_agent import ToolCallingAgent
        return ToolCallingAgent()
    raise ValueError(f"未知模式: {mode}")


def _print_answer(question: str, answer: Answer) -> None:
    print(f"\n[模式] {getattr(answer.mode, 'value', answer.mode)}   "
          f"[状态] {answer.status}   "
          f"[可靠性] {getattr(answer.reliability, 'value', answer.reliability)}")
    print(f"用户: {question}")
    print(f"AI 杏林: {answer.answer.strip()}")

    if answer.sources:
        print(f"来源[{len(answer.sources)}]: " + json.dumps(
            [s.type.value for s in answer.sources], ensure_ascii=False))

    if answer.risk_notice:
        print(f"提示: {answer.risk_notice}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="杏林大健康 AI 问答系统（第二代）")
    parser.add_argument("--mode", choices=MODES, default="hybrid",
                        help="问答模式：hybrid=双路融合(默认) / rag=RAG召回 / "
                             "nl2cypher=图谱 / agent=工具调用")
    parser.add_argument("--cache", action="store_true",
                        help="用 Redis 缓存包裹问答结果（需 redis 服务）")
    parser.add_argument("-q", "--question", default=None,
                        help="单次提问后退出（便于脚本化验证）")
    return parser


def main(argv=None) -> int:
    _force_utf8_stdout()
    args = build_parser().parse_args(argv)

    bot = _build_agent(args.mode)

    # 可选缓存：仅在开启时导入，避免未装 redis 时影响其他模式（文档 §4.6 的用法）
    cache_manager = None
    if args.cache:
        from xinglin.infrastructure.cache import redis_manager

        cache_manager = redis_manager

    def ask(question: str) -> Answer:
        if cache_manager is None:
            return bot.chat_main(question)
        key = f"kb:cli:{args.mode}:{question}"
        payload = cache_manager.get_or_compute(
            key, lambda: bot.chat_main(question).model_dump(mode="json"))
        return Answer(**payload) if isinstance(payload, dict) else payload

    if args.question:
        _print_answer(args.question.strip(), ask(args.question.strip()))
        return 0

    print(f"\n===== 欢迎使用杏林医疗 AI 问答系统（{args.mode} 模式：{MODE_LABELS[args.mode]}）=====")
    print("输入 Q 或 q 退出系统\n")

    while True:
        try:
            question = input(f"用户[{args.mode}]:").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n感谢您的使用，再见！")
            return 0
        if not question:
            continue
        if question.lower() in QUIT_WORDS:
            print("感谢您的使用，再见！")
            return 0

        try:
            answer = ask(question)
        except Exception:      # noqa: BLE001 —— 内部错误不外泄（ACC-031/14.5.4）
            print("AI 杏林: 服务暂时不可用，请稍后再试。")
            continue
        _print_answer(question, answer)
        print()


if __name__ == "__main__":
    raise SystemExit(main())
