"""文献入库脚本：knowledge_base.txt → 切块（langchain-text-splitters）
→ BGE-M3 向量化 → Milvus（langchain-milvus），同步产出 BM25 语料。

用法：
  .venv/Scripts/python.exe scripts/ingest_docs.py [--input path] [--rebuild]
依赖：pip install langchain-huggingface sentence-transformers（本地向量化）
"""

import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

DOC_SEP = re.compile(r"={60}\n【文档 \d+】(.+?)\n(?:元数据标题: .*\n)?来源路径: .*? \| 页数: \d+\n={60}")
PAGE_SEP = re.compile(r"--- 第 (\d+) 页 ---")


def load_documents(kb_path: Path):
    """解析 knowledge_base.txt → [(标题, [(页码, 文本), ...]), ...]。"""
    text = kb_path.read_text(encoding="utf-8")
    blocks = DOC_SEP.split(text)
    # split 后结构：[前言, 标题1, 正文1, 标题2, 正文2, ...]
    docs = []
    for i in range(1, len(blocks) - 1, 2):
        title, body = blocks[i].strip(), blocks[i + 1]
        pages = []
        parts = PAGE_SEP.split(body)
        for j in range(1, len(parts) - 1, 2):
            pages.append((int(parts[j]), parts[j + 1].strip()))
        if not pages and body.strip():
            pages.append((1, body.strip()))
        docs.append((title, pages))
    return docs


def make_chunks(docs, size=700, overlap=120):
    """页文本 → LangChain Document（langchain-text-splitters 切块，保留来源元数据）。"""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=size, chunk_overlap=overlap,
        separators=["\n\n", "。\n", "。", "；", "\n", "，", " "],
    )
    out = []
    for title, pages in docs:
        for page_no, page_text in pages:
            if len(page_text) < 50:
                continue
            for k, piece in enumerate(splitter.split_text(page_text)):
                out.append({
                    "text": piece,
                    "metadata": {
                        "doc_title": title[:200],
                        "page_num": page_no,
                        "chunk_seq": k,
                        "journal": "中国全科医学" if "chinagp" in page_text else "",
                    },
                })
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(BASE.parent / "medical" / "knowledge_base.txt"))
    ap.add_argument("--rebuild", action="store_true", help="删除并重建集合")
    args = ap.parse_args()

    kb = Path(args.input)
    if not kb.exists():
        print(f"[错误] 语料文件不存在: {kb}")
        sys.exit(1)

    docs = load_documents(kb)
    chunks = make_chunks(docs)
    print(f"解析 {len(docs)} 篇文献 → {len(chunks)} 个片段")

    # ① BM25 语料（内存索引数据源，随时可用）
    from app.infrastructure.config import get_settings
    bm25_path = Path(get_settings().bm25_docs_path)
    bm25_path.parent.mkdir(parents=True, exist_ok=True)
    bm25_path.write_text(json.dumps(chunks, ensure_ascii=False), encoding="utf-8")
    print(f"BM25 语料已写出: {bm25_path}")

    # ② Milvus 稠密入库（langchain-milvus + 本地向量化模型）
    try:
        from langchain_core.documents import Document
        from langchain_milvus import Milvus

        from app.infrastructure.config import get_settings
        from app.infrastructure.embedder import get_embeddings
        s = get_settings()
        embeddings = get_embeddings()
        lc_docs = [Document(page_content=c["text"], metadata=c["metadata"]) for c in chunks]
        if args.rebuild:
            Milvus(embedding_function=embeddings,
                   collection_name=s.milvus_collection,
                   connection_args={"uri": s.milvus_uri}).delete_collection()
        vs = Milvus(embedding_function=embeddings,
                    collection_name=s.milvus_collection,
                    connection_args={"uri": s.milvus_uri},
                    auto_id=True,
                    index_params={"index_type": "HNSW", "metric_type": "COSINE",
                                  "params": {"M": 16, "efConstruction": 200}})
        ids = vs.add_documents(lc_docs)
        print(f"Milvus 入库完成: {len(ids)} 条向量 → collection={s.milvus_collection}")
    except Exception as e:  # noqa: BLE001
        print(f"[警告] Milvus 入库失败（{e}）\nBM25 语料已就绪，服务仍可启动（RAG 通路待 Milvus 就绪后重跑）")


if __name__ == "__main__":
    main()
