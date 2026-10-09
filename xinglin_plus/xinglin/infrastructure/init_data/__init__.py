"""init_data：离线数据构建脚本（基础设施层）。

    kg_build.py      —— 见 `xinglin.domain.graph.build_graph`（图谱建库主流程）
    vectorstore.py   —— 见 `xinglin.domain.rag.vectorstore`（文献切片与向量化）
    export_dict.py   —— 从图谱导出 8 类医学词典（`dict/*.txt`）

为什么不把建库脚本都堆在本目录：指导文档 §4.1 要求建库脚本归"基础设施"，
本项目进一步让**能力与被复用的代码同址**——建图逻辑在 `domain/graph`（干跑统计也被
测试与文档引用），向量化在 `domain/rag`（检索侧同样复用它），本目录只保留派生产物脚本。
"""

__all__ = ["export_dict"]
