"""application：应用编排层（用例编排 + 组合根）。

四个并列的问答 Agent（对应《项目开发指导》§5.4），**薄编排**：装配依赖 + 决定"什么时候
走哪条路"，真正的业务能力都在 `xinglin.domain`。

    nl2cypher_agent.py   NL2CypherAgent   图谱路（模板 → NL2Cypher → 规则兜底链）
    rag_agent.py         RAGAgent         文献路（稠密 + BM25 → RRF）
    hybrid_agent.py      HybridAgent     【默认】双路融合 + FR-024 自动选路 + FR-026 换路重试
    tool_agent.py        ToolCallingAgent ReAct 自主决策（create_react_agent）
    tools.py             build_tools      给 ReAct 用的 @tool（图谱 / 文献）
    prompts.py           生成提示词（应用层资产，注入给 GenerationService）
    runtime.py           运行时装配（组合根）：唯一 import infrastructure 的业务模块
"""

from xinglin.application.hybrid_agent import HybridAgent
from xinglin.application.nl2cypher_agent import NL2CypherAgent
from xinglin.application.rag_agent import RAGAgent
from xinglin.application.tool_agent import ToolCallingAgent
from xinglin.application.tools import build_tools

__all__ = ["HybridAgent", "NL2CypherAgent", "RAGAgent", "ToolCallingAgent", "build_tools"]
