"""向量库操作（对应《项目开发指导》§4.4）：文献向量检索 + 双路融合。

**数据形态：直接复用既有 Milvus 集合**（``medical_lit``，762 条切片，已就绪）。
该集合由 langchain-milvus 建立，字段固定：:

    text(VARCHAR)  pk(INT64, 主键)  vector(FLOAT_VECTOR, 384)
    doc_title      page_num        chunk_seq          journal

因此本模块**不需要重新切片 / 灌库**：``MilvusVectorStore.load()`` 直连它检索即可；
切片正文与元数据都在库里，稀疏路要用的 BM25 语料由
``export_bm25_docs_from_milvus()`` 从**同一集合**导出，保证两路语料完全一致。

- ``MilvusVectorStore``：稠密路（IP 内积，向量已归一化故等价余弦），字段名与既有集合对齐；
- ``HybridRetriever``：稠密（Milvus）+ 稀疏（本地 BM25 内存索引）→ RRF 融合
  （对应指导文档 §6「两层多路召回」的**内层**）；
- ``prepare_documents`` / ``create``：**可选**的"从 PDF 重建集合"能力（日常用不到，
  既有集合已就绪）；一旦使用，产物与 ``medical_lit`` 同构，可无缝替换。

与指导文档的差异（刻意的，已在 readme 与 docs 说明）：
    指导文档示例用 **Milvus Lite**（嵌入式 ``./milvus_agent.db``），
    本项目沿用**既有 Milvus 服务**（``http://localhost:19530``，集合 ``medical_lit``）。

用法::

    python -m xinglin.domain.rag.vectorstore                 # 从既有集合导出 BM25 语料
    python -m xinglin.domain.rag.vectorstore --rebuild       # （可选）从 PDF 重建集合
"""

import json
import os
from pathlib import Path
from typing import List, Tuple

from langchain_core.documents import Document
from langchain_milvus import Milvus
from langchain_text_splitters import RecursiveCharacterTextSplitter

from xinglin.config import (
    BM25_DOCS_PATH,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    HYBRID_DENSE_WEIGHT,
    HYBRID_SPARSE_WEIGHT,
    MILVUS_CONFIG,
    PDF_DATA_DIR,
    RETRIEVAL_TOP_K,
    SEARCH_SCORE_THRESHOLD,
)
from xinglin.domain.rag.embeddings import create_embeddings

# metric_type: "IP" → 内积（向量已归一化，等价余弦相似度）
# 数据量到百万级、FLAT 查询变慢时可换 HNSW（牺牲少量召回换速度）
DENSE_INDEX = {"metric_type": "IP", "index_type": "FLAT"}

# 既有集合（medical_lit）的字段名 —— 由 langchain-milvus 默认命名，改名即失联
TEXT_FIELD = "text"
PK_FIELD = "pk"
VECTOR_FIELD = "vector"
# 建表时的向量字段：与既有集合同构（单一稠密字段；稀疏路由本地 BM25 承担）
VECTOR_FIELDS = [VECTOR_FIELD]

# Milvus 字段名 → 本项目统一元数据键（文献侧原始字段沿用中文语料的命名习惯）
META_MAP = {
    "doc_title": "source",      # 源文献标题（即文件名，引用与溯源展示用）
    "page_num": "page",         # 页码
    "chunk_seq": "chunk",       # 该页内的切片序号
    "journal": "journal",       # 期刊名
}
# 每个切片带的元数据键（本项目统一口径，供溯源与引用标注）
META_KEYS = ("source", "page", "chunk", "journal")


def normalize_metadata(meta: dict | None) -> dict:
    """把 Milvus 既有字段名（``doc_title`` / ``page_num`` …）翻译成本项目统一键。

    两路检索（Milvus 稠密 / 本地 BM25）的元数据来源不同，在此统一收敛，
    上层（事实护栏、DTO、引用展示）只认 ``source/page/chunk/journal``；
    主键 ``pk`` 属内部实现，不外泄。
    """
    out: dict = {}
    for key, value in (meta or {}).items():
        if value is None or key == PK_FIELD:
            continue
        out[META_MAP.get(key, key)] = value
    return out


def _extract_pdf_pages(path: str) -> List[Tuple[int, str]]:
    """提取单个 PDF 每页文本，返回 [(页码, 文本), ...]，跳过空白页。

    `pypdf` 采取**延迟导入**：它是只有"重新切片"时才需要的可选依赖，
    不应让整个 rag 模块因缺少它而 import 失败。
    """
    try:
        from pypdf import PdfReader
    except ImportError as e:      # pragma: no cover - 环境问题
        raise RuntimeError(
            "缺少 PDF 解析库，请先安装：.venv\\Scripts\\python.exe -m pip install pypdf") from e

    reader = PdfReader(path)
    pages: List[Tuple[int, str]] = []
    for i, page in enumerate(reader.pages):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append((i + 1, text))
    return pages


def prepare_documents(pdf_dir: str = PDF_DATA_DIR) -> List[Document]:
    """读取目录下的 PDF 医学文献，按页切片后转成 Document 列表（**可选重建路径**）。

    元数据键刻意与既有集合 ``medical_lit`` 对齐（``doc_title/page_num/chunk_seq/journal``），
    保证"重建后的集合"与现有集合同构，可无缝替换。
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
        length_function=len,
    )

    pdf_files = sorted(f for f in os.listdir(pdf_dir) if f.lower().endswith(".pdf"))
    if not pdf_files:
        raise FileNotFoundError(f"目录 {pdf_dir} 下没有找到任何 PDF 文件")

    docs: List[Document] = []
    for filename in pdf_files:
        path = os.path.join(pdf_dir, filename)
        pages = _extract_pdf_pages(path)
        if not pages:
            print(f"[警告] {filename} 未提取到任何文字，可能是扫描版 PDF，跳过（需先 OCR）")
            continue
        for page_no, text in pages:
            for seq, chunk in enumerate(splitter.split_text(text)):
                docs.append(Document(
                    page_content=chunk,
                    metadata={                       # 字段名与既有集合 medical_lit 对齐
                        "doc_title": filename,       # 源文献（即文件名，溯源用）
                        "page_num": page_no,         # 页码
                        "chunk_seq": seq,            # 该页内的切片序号
                        "journal": "",               # PDF 中无期刊字段，留空
                    },
                ))
    return docs


class MilvusVectorStore:
    """Milvus 向量库封装：dense + sparse 双字段，默认 dense 单路打分检索。"""

    def __init__(self, uri: str | None = None, collection_name: str | None = None):
        self.uri = uri or MILVUS_CONFIG["uri"]
        self.collection_name = collection_name or MILVUS_CONFIG["collection"]
        self.embeddings = create_embeddings()
        self.vectorstore = None

    # -- 建库（可选：仅"从 PDF 重建集合"时才用） -----------------------------
    def create(self, docs: List[Document], drop_old: bool = False):
        """**可选**：从文档重建集合（产物与既有 ``medical_lit`` 同构）。

        日常不需要——既有集合已就绪，``load()`` 直连即可；仅在需要更新文献语料时使用。
        """
        init_docs = docs[:10]
        self.vectorstore = Milvus.from_documents(
            documents=init_docs,
            embedding=self.embeddings,
            index_params=[DENSE_INDEX],
            vector_field=VECTOR_FIELD,
            collection_name=self.collection_name,
            connection_args={"uri": self.uri},
            # Bounded：允许读到"有界延迟但不过期"的数据；Milvus 默认推荐级别
            consistency_level="Bounded",
            drop_old=drop_old,
        )
        # 剩余文档分批写入，避免一次性写入过多
        batch_size = 200
        for i in range(10, len(docs), batch_size):
            self.vectorstore.add_documents(docs[i:i + batch_size])
            print(f"已写入 {min(i + batch_size, len(docs))}/{len(docs)} 条")
        # 顺带导出稀疏路要用的切片语料（BM25 内存索引的数据源）
        export_bm25_docs(docs)
        return self.load()

    def load(self):
        """连接**既有** Milvus 集合（检索只用稠密字段）。

        字段名严格对齐既有集合（``vector`` / ``text`` / ``pk``）；
        刻意不传 ``builtin_function``、不传多字段：否则 langchain-milvus 会判定为
        multi-vector 而走 hybrid_search（WeightedRanker），在部分环境下触发
        "weighted merge requires 2 weights" 报错。
        双路融合由 `HybridRetriever` 显式完成（见下），行为可控。
        """
        self.vectorstore = Milvus(
            embedding_function=self.embeddings,
            vector_field=VECTOR_FIELD,
            collection_name=self.collection_name,
            connection_args={"uri": self.uri},
        )
        return self.vectorstore

    # -- 检索 ---------------------------------------------------------------
    def search(self, query: str, k: int = 10,
               score_threshold: float | None = None) -> List[Document]:
        """稠密单路检索，按相似度阈值过滤无关结果。

        score 为内积（向量已归一化故等价余弦），范围 [-1, 1]；低于阈值的片段直接丢弃，
        分数写入 ``metadata["score"]`` 供上层标注。

        ``score_threshold`` 省略时取配置 ``SEARCH_SCORE_THRESHOLD``；显式传 0 可关闭过滤。
        ⚠ 阈值只适用于**单路**的绝对分——`HybridRetriever` 融合后的分数是逐查询相对分，
        量纲不同，套用绝对阈值会误杀（所以融合路不传本参数）。
        """
        threshold = SEARCH_SCORE_THRESHOLD if score_threshold is None else score_threshold
        if self.vectorstore is None:
            self.load()
        results = self.vectorstore.similarity_search_with_score(query, k=k)
        docs: List[Document] = []
        for doc, score in results:
            if threshold and score < threshold:
                continue
            doc.metadata = {**normalize_metadata(doc.metadata), "score": round(score, 4)}
            docs.append(doc)
        return docs


def export_bm25_docs(docs: List[Document], path: str = BM25_DOCS_PATH) -> int:
    """把切片导出成 JSON 语料（稀疏路 BM25 内存索引的数据源），返回切片数。

    仅用于"从 PDF 重建集合"这条可选路径；复用既有集合时请用
    `export_bm25_docs_from_milvus`（它直接从库里取，无需再切 PDF）。
    """
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    payload = [{"text": d.page_content, "metadata": d.metadata} for d in docs]
    Path(path).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return len(payload)


def export_bm25_docs_from_milvus(store: MilvusVectorStore | None = None,
                                 path: str = BM25_DOCS_PATH) -> int:
    """从**既有** Milvus 集合导出 BM25 语料（稀疏路的数据源），返回切片数。

    复用现有集合的好处：正文与元数据都在库里，**不必重新切 PDF**，
    且两路（稠密 / 稀疏）的语料逐条一致，RRF 融合才有意义。
    """
    from pymilvus import MilvusClient

    store = store or MilvusVectorStore()
    client = MilvusClient(uri=store.uri)
    rows = client.query(
        collection_name=store.collection_name,
        filter=f"{PK_FIELD} >= 0",
        output_fields=[TEXT_FIELD, *META_MAP.keys()],
        limit=16384,                     # 一次拉全量（762 条，远低于 Milvus 上限）
    )
    payload = [{"text": row[TEXT_FIELD], "metadata": normalize_metadata(row)}
               for row in rows if row.get(TEXT_FIELD)]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return len(payload)


def _tokenize(text: str) -> list[str]:
    """中文分词（BM25 稀疏路用）：jieba 搜索引擎模式，兼顾长词与子词。"""
    import jieba
    return [w.strip() for w in jieba.cut_for_search(text or "") if w.strip()]


class HybridRetriever:
    """稠密（Milvus）+ 稀疏（BM25）双路检索 → RRF 融合。

    对应《项目开发指导》§6「两层多路召回」的**内层**：向量库内部的 dense + sparse。

    - 两路都可用 → `EnsembleRetriever`（内置 RRF）融合；
    - 只有一路可用 → 直接用单路（降级不阻断）；
    - 都不可用 → `available=False`，由上层走降级链。

    实现领域端口 ``LiteratureSearch``（`available` / `search`）。
    """

    # (稠密, 稀疏)：由 config 提供，可用环境变量覆盖以做**权重消融**。
    # 实测（evals/ablation.py）：原默认 0.6/0.4 下融合结果与"仅 dense"**逐位相同**——
    # 稠密路完全主导，稀疏路对最终名次没有贡献。
    WEIGHTS = (HYBRID_DENSE_WEIGHT, HYBRID_SPARSE_WEIGHT)

    def __init__(self, store: MilvusVectorStore | None = None,
                 docs_path: str = BM25_DOCS_PATH, top_k: int = RETRIEVAL_TOP_K):
        self._store = store
        self._retriever = None
        self._top_k = top_k
        try:
            self._retriever = self._build(docs_path)
        except Exception as e:      # noqa: BLE001 —— 组件不可用即降级
            print(f"[警告] 混合检索组件初始化失败：{type(e).__name__}: {e}")

    def _build(self, docs_path: str):
        from langchain_classic.retrievers import EnsembleRetriever
        from langchain_community.retrievers import BM25Retriever
        from langchain_core.documents import Document

        retrievers, weights, names = [], [], []

        # 稀疏路：本地 BM25（语料由建库脚本导出）
        if Path(docs_path).exists():
            payload = json.loads(Path(docs_path).read_text(encoding="utf-8"))
            docs = [Document(page_content=item["text"], metadata=item.get("metadata") or {})
                    for item in payload if item.get("text")]
            if docs:
                bm25 = BM25Retriever.from_documents(docs, preprocess_func=_tokenize)
                bm25.k = self._top_k
                retrievers.append(bm25)
                weights.append(self.WEIGHTS[1])
                names.append(f"bm25({len(docs)})")

        # 稠密路：Milvus
        # 单独捕获：Milvus 不可用时**只丢这一路**，别把已经建好的 BM25 一起拖垮
        # （否则 `load()` 抛的 MilvusException 会冒泡到 __init__，令整个检索组件
        # 判为"未就绪"——实测 Milvus 停服时就会出现这种"双路一起失效"）
        try:
            store = self._store or MilvusVectorStore()
            vectorstore = store.load()
        except Exception as e:      # noqa: BLE001 —— 单路失败即降级为另一路
            print(f"[警告] 稠密路（Milvus）不可用，降级为稀疏单路：{type(e).__name__}: {e}")
            vectorstore = None
        if vectorstore is not None:
            retrievers.append(vectorstore.as_retriever(search_kwargs={"k": self._top_k}))
            weights.append(self.WEIGHTS[0])
            names.append(f"milvus({store.collection_name})")

        if not retrievers:
            return None
        if len(retrievers) == 1:
            print(f"[混合检索] 单路可用：{names[0]}")
            return retrievers[0]
        print(f"[混合检索] 双路 RRF 融合：{' + '.join(names)}（权重 {weights}）")
        return EnsembleRetriever(retrievers=retrievers, weights=weights)

    @property
    def available(self) -> bool:
        return self._retriever is not None

    def search(self, query: str, k: int = RETRIEVAL_TOP_K) -> list[dict]:
        """返回 ``[{"text": ..., "metadata": {...}}, ...]``（纯 dict，不外泄 langchain 类型）。"""
        if not self.available:
            return []
        docs = self._retriever.invoke(query)[:k]
        # 两路（Milvus / BM25）元数据来源不同，统一成本项目口径后再交给上层
        return [{"text": d.page_content,
                 "metadata": normalize_metadata(d.metadata)} for d in docs]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="文献向量库（默认：从既有集合导出 BM25 语料）")
    parser.add_argument("--export-bm25", action="store_true",
                        help="从既有 Milvus 集合导出 BM25 语料（默认动作）")
    parser.add_argument("--rebuild", action="store_true",
                        help="可选：从 data/pdfs 重新切片并重建集合（会覆盖既有集合）")
    args = parser.parse_args()

    store = MilvusVectorStore()
    if args.rebuild:
        print("从 PDF 医学文献重建集合 ...")
        docs = prepare_documents()
        print(f"共 {len(docs)} 条文献切片")
        store.create(docs, drop_old=True)
        print(f"重建完成：{MILVUS_CONFIG['uri']} / {MILVUS_CONFIG['collection']}")
    else:
        n = export_bm25_docs_from_milvus(store)
        print(f"BM25 语料已从既有集合导出：{BM25_DOCS_PATH}（{n} 条）")
