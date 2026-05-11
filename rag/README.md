# TOMI RAG — 多源音乐知识检索系统

## 架构图

```
用户 Query
    │
    ▼
[Query Rewriter]  ─── Claude Haiku ──→ 专业术语 query + source hint
    │
    ▼
[Source Router]   ─── 关键词匹配 ──→  目标文档源 {ableton / pulseformer / tutorial}
    │
    ├──→ [Vector Search]  Qdrant cosine top-10  (BGE-M3 embedding)
    │
    └──→ [BM25 Search]    rank_bm25 keyword top-10
              │
              ▼
         [RRF Fusion]     Reciprocal Rank Fusion  α=0.6 向量 / 0.4 BM25
              │
              ▼
         [Reranker]       BGE-reranker-v2-m3 cross-encoder
              │
              ▼
         top-3 chunks  → FastAPI /retrieve 返回
```

## 文档源

| Key                | 内容                    | 语言    |
|--------------------|------------------------|---------|
| `music_tutorial`   | HEME 音乐制作课堂笔记（162 PDF）| 中文    |
| `pulseformer_paper`| PulseFormer 学术论文     | 英文    |
| `ableton_manual`   | Ableton Live 11 手册    | 英文    |

## 快速开始

```bash
# 1. 安装依赖
pip install -r rag/requirements.txt

# 2. 入库所有文档（首次运行，~15-30分钟，含模型下载）
python -m rag.ingest

# 3. 启动检索服务（端口 8001）
python -m rag.server

# 4. 测试
curl -X POST http://localhost:8001/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query": "E_level 设多少才有 buildup 感", "top_k": 3}'

# 5. 运行评测（需先完成入库）
python -m rag.evaluate
```

## API

### POST /retrieve

```json
{
  "query": "string",          // 用户 query
  "top_k": 3,                 // 返回数量 (1-20)
  "sources": null,            // 强制指定 source，null=自动路由
  "rewrite": true,            // 是否改写 query
  "use_routing": true,        // 是否 source routing
  "use_rerank": true,         // 是否 reranking
  "return_context": true      // 是否返回拼接好的 context 字符串
}
```

返回：
```json
{
  "query": "原始 query",
  "rewritten_query": "改写后 query",
  "original_intent": "意图描述",
  "routed_sources": ["ableton_manual"],
  "chunks": [
    {
      "text": "chunk 内容",
      "source": "ableton_manual",
      "doc_type": "manual",
      "page": 42,
      "section": "MIDI Editor",
      "rerank_score": 0.95
    }
  ],
  "context": "拼接好的 LLM context 字符串",
  "latency_ms": 120.5
}
```

## 高级 RAG 技术点

1. **Query Rewriting** — Claude Haiku 把口语化描述改写为专业术语，few-shot 示例驱动
2. **Source Routing** — 关键词匹配定向到相关文档子集，降低噪声
3. **Hybrid Search** — 向量（语义）+ BM25（关键词）双路召回，RRF 融合
4. **Cross-Encoder Reranking** — BGE-reranker-v2-m3 精排，比双塔 embedding 更精准
5. **元数据过滤** — Qdrant payload filter 按 source 限定，避免无关文档干扰
6. **缓存层** — 解析结果 pickle 缓存，避免重复解析 867 页 PDF
