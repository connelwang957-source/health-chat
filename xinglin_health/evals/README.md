# 评测目录

按技术文档第 12 章建设：

- `intent_v1.jsonl` —— 意图分类评测集：18 类 × 30 条 + 开放式 50 条 + 非法/兜底 30 条（≈620 条）
  字段：{"question": "...", "expect_mode": "kg|rag|hybrid|direct", "expect_qa_code": 1-18|null}
- `retrieval_v1.jsonl` —— 检索命中评测：{"question": "...", "expect_doc": "文献标题子串"}
- 运行方式（I5 实现）：`python -m evals.run --set intent_v1`

阈值：意图 acc ≥ 90%（NFR-R01）｜ 路由一致率 ≥ 85% ｜ hit@5 ≥ 80% ｜ 抽检无依据陈述 ≤ 10%
