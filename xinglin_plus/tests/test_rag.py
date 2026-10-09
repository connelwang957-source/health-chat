"""向量检索适配：既有集合的字段与元数据口径（全部离线，不连 Milvus）。"""

from xinglin.domain.rag import META_KEYS, META_MAP, HybridRetriever, normalize_metadata


class TestNormalizeMetadata:
    def test_translates_legacy_field_names(self):
        """既有集合存的是 doc_title/page_num/chunk_seq，须翻译成本项目统一键。"""
        meta = normalize_metadata({"doc_title": "A.pdf", "page_num": 3,
                                   "chunk_seq": 2, "journal": "中国全科医学", "pk": 123})
        assert meta == {"source": "A.pdf", "page": 3, "chunk": 2, "journal": "中国全科医学"}

    def test_primary_key_is_internal_only(self):
        assert "pk" not in normalize_metadata({"pk": 1, "page": 2})

    def test_is_idempotent(self):
        once = normalize_metadata({"doc_title": "A.pdf", "page_num": 3})
        assert normalize_metadata(once) == once

    def test_drops_none_values(self):
        assert normalize_metadata({"doc_title": None, "page": None}) == {}

    def test_keeps_unknown_keys(self):
        assert normalize_metadata({"score": 0.5}) == {"score": 0.5}

    def test_handles_none(self):
        assert normalize_metadata(None) == {}

    def test_meta_map_targets_match_declared_keys(self):
        assert set(META_MAP.values()) == set(META_KEYS)


class _StoreWithoutCollection:
    """替身：模拟"Milvus 上没有这个集合"（load 返回 None）。"""

    collection_name = "missing"

    def load(self):
        return None


class TestHybridRetrieverDegrades:
    def test_unavailable_when_both_paths_missing(self, tmp_path):
        retriever = HybridRetriever(store=_StoreWithoutCollection(),
                                    docs_path=str(tmp_path / "missing.json"))
        assert retriever.available is False

    def test_search_returns_empty_when_unavailable(self, tmp_path):
        retriever = HybridRetriever(store=_StoreWithoutCollection(),
                                    docs_path=str(tmp_path / "missing.json"))
        assert retriever.search("任意问题") == []


class TestBm25CorpusExport:
    def test_export_writes_json_with_metadata(self, tmp_path):
        """稀疏路语料导出：正文 + 元数据（供 HybridRetriever 建内存 BM25）。"""
        from langchain_core.documents import Document

        from xinglin.domain.rag.vectorstore import export_bm25_docs

        path = tmp_path / "bm25_docs.json"
        n = export_bm25_docs([Document(page_content="感冒以对症支持为主。",
                                       metadata={"source": "A.pdf", "page": 1})], str(path))
        assert n == 1

        import json
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload[0]["text"] == "感冒以对症支持为主。"
        assert payload[0]["metadata"]["source"] == "A.pdf"


class _FakeLangchainMilvus:
    """假 langchain Milvus：返回固定的 (Document, score) 序列。"""

    def __init__(self, pairs):
        self.pairs = pairs

    def similarity_search_with_score(self, query, k=10):
        return self.pairs[:k]


def _store_with(pairs):
    """不触发 __init__（避免加载嵌入模型），直接装一个假向量库。"""
    from xinglin.domain.rag import MilvusVectorStore

    store = MilvusVectorStore.__new__(MilvusVectorStore)
    store.vectorstore = _FakeLangchainMilvus(pairs)
    return store


class TestScoreThreshold:
    """`SEARCH_SCORE_THRESHOLD`：只作用于单路稠密检索（文档 §11.1.1/§11.1.2）。"""

    def _pairs(self):
        from langchain_core.documents import Document
        return [(Document(page_content="高分片段", metadata={"doc_title": "A.pdf"}), 0.90),
                (Document(page_content="低分片段", metadata={"doc_title": "B.pdf"}), 0.40)]

    def test_filters_below_threshold(self):
        docs = _store_with(self._pairs()).search("任意", k=2, score_threshold=0.65)
        assert [d.page_content for d in docs] == ["高分片段"]

    def test_zero_threshold_disables_filtering(self):
        docs = _store_with(self._pairs()).search("任意", k=2, score_threshold=0)
        assert len(docs) == 2

    def test_keeps_and_annotates_score(self):
        docs = _store_with(self._pairs()).search("任意", k=2, score_threshold=0.65)
        assert docs[0].metadata["score"] == 0.9
        assert docs[0].metadata["source"] == "A.pdf"      # 元数据已统一口径
