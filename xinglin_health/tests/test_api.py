"""API 冒烟测试：应用可启动、/health 可用、非法查询被拦截、离线降级链完整。"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_200_with_dependencies():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded")
    assert set(body["dependencies"].keys()) == {"neo4j", "milvus", "redis", "llm"}


def test_ask_rejects_illegal_query():
    """12.7/G-09：非法查询拒绝执行，不暴露内部错误。"""
    r = client.post("/ask", json={"question": "drop table 疾病"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "rejected"


def test_ask_offline_degrades_gracefully():
    """依赖全离线时：不抛 500，走降级链给兜底回答（FR-026/027）。"""
    r = client.post("/ask", json={"question": "感冒不能吃什么？"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("insufficient_info", "service_unavailable", "ok")
    assert body["answer"]


def test_ask_validation():
    r = client.post("/ask", json={"question": ""})
    assert r.status_code == 400
