"""
rag/retriever.py — 混合检索 + Reranking + Source Routing

检索管线:
  1. Source Routing  → 确定搜哪些文档源
  2. 向量检索        → Qdrant cosine top-K（带 source filter）
  3. BM25 检索       → rank_bm25 top-K
  4. RRF 融合        → Reciprocal Rank Fusion 合并两路结果
  5. Reranking       → BGE cross-encoder 重排序
  6. 返回 top-N
"""
import pickle
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchAny
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer, CrossEncoder

from rag.config import (
    QDRANT_PATH, COLLECTION, BM25_PATH,
    EMBED_MODEL, RERANK_MODEL,
    RETRIEVE_TOP_K, RERANK_TOP_K, HYBRID_ALPHA,
    SOURCE_KEYWORDS,
)


# ── 懒加载单例 ────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_embedder() -> SentenceTransformer:
    print(f"[retriever] 加载 embedder: {EMBED_MODEL}")
    return SentenceTransformer(EMBED_MODEL, device="cuda")


@lru_cache(maxsize=1)
def _get_reranker() -> CrossEncoder:
    print(f"[retriever] 加载 reranker: {RERANK_MODEL}")
    return CrossEncoder(RERANK_MODEL)


@lru_cache(maxsize=1)
def _get_qdrant() -> QdrantClient:
    return QdrantClient(path=str(QDRANT_PATH))


@lru_cache(maxsize=1)
def _get_bm25() -> tuple[BM25Okapi, list[dict]]:
    if not BM25_PATH.exists():
        raise FileNotFoundError(f"BM25 索引不存在: {BM25_PATH}，请先运行 rag/ingest.py")
    with open(BM25_PATH, "rb") as f:
        data = pickle.load(f)
    return data["index"], data["chunks"]


# ── Source Routing ────────────────────────────────────────────────────────────

def route_sources(query: str) -> list[str]:
    """
    根据 query 关键词决定搜哪些文档源。
    返回 source_key 列表；空列表 = 全部搜。
    """
    q_lower = query.lower()
    scores: dict[str, int] = {}
    for source, keywords in SOURCE_KEYWORDS.items():
        hit = sum(1 for kw in keywords if kw in q_lower)
        if hit > 0:
            scores[source] = hit

    if not scores:
        return []  # 全部搜

    max_score = max(scores.values())
    # 允许命中分 >= max_score*0.6 的 source 一起参与
    selected = [s for s, sc in scores.items() if sc >= max_score * 0.6]
    return selected


# ── 向量检索 ──────────────────────────────────────────────────────────────────

def vector_search(query: str, sources: list[str]) -> list[dict]:
    embedder = _get_embedder()
    q_vec = embedder.encode(query, normalize_embeddings=True).tolist()
    client = _get_qdrant()

    query_filter = None
    if sources:
        query_filter = Filter(
            must=[FieldCondition(key="source", match=MatchAny(any=sources))]
        )

    response = client.query_points(
        collection_name=COLLECTION,
        query=q_vec,
        limit=RETRIEVE_TOP_K,
        query_filter=query_filter,
        with_payload=True,
    )
    results = []
    for rank, hit in enumerate(response.points):
        payload = dict(hit.payload)
        payload["_vector_score"] = hit.score
        payload["_vector_rank"]  = rank
        results.append(payload)
    return results


# ── BM25 检索 ─────────────────────────────────────────────────────────────────

def bm25_search(query: str, sources: list[str]) -> list[dict]:
    index, chunks = _get_bm25()
    tokens = query.lower().split()
    scores = index.get_scores(tokens)

    # source filter
    if sources:
        for i, c in enumerate(chunks):
            if c.get("source") not in sources:
                scores[i] = 0.0

    top_indices = np.argsort(scores)[::-1][:RETRIEVE_TOP_K]
    results = []
    for rank, idx in enumerate(top_indices):
        if scores[idx] <= 0:
            break
        result = dict(chunks[idx])
        result["_bm25_score"] = float(scores[idx])
        result["_bm25_rank"]  = rank
        results.append(result)
    return results


# ── RRF 融合 ──────────────────────────────────────────────────────────────────

def reciprocal_rank_fusion(
    vec_results: list[dict],
    bm25_results: list[dict],
    k: int = 60,
) -> list[dict]:
    """Reciprocal Rank Fusion — 合并两路排名"""
    scores: dict[str, float] = {}
    docs: dict[str, dict]    = {}

    for rank, doc in enumerate(vec_results):
        cid = doc.get("chunk_id", str(rank))
        scores[cid] = scores.get(cid, 0) + HYBRID_ALPHA / (k + rank + 1)
        docs[cid] = doc

    for rank, doc in enumerate(bm25_results):
        cid = doc.get("chunk_id", str(rank))
        scores[cid] = scores.get(cid, 0) + (1 - HYBRID_ALPHA) / (k + rank + 1)
        if cid not in docs:
            docs[cid] = doc

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    fused = []
    for cid, rrf_score in ranked:
        doc = dict(docs[cid])
        doc["_rrf_score"] = rrf_score
        fused.append(doc)
    return fused


# ── Reranking ─────────────────────────────────────────────────────────────────

def rerank(query: str, candidates: list[dict], top_n: int = RERANK_TOP_K) -> list[dict]:
    if not candidates:
        return []
    reranker = _get_reranker()
    pairs = [(query, c["text"]) for c in candidates]
    scores = reranker.predict(pairs)
    ranked = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)
    results = []
    for score, doc in ranked[:top_n]:
        doc = dict(doc)
        doc["_rerank_score"] = float(score)
        results.append(doc)
    return results


# ── 主入口 ────────────────────────────────────────────────────────────────────

def retrieve(
    query: str,
    top_k: int = RERANK_TOP_K,
    sources: Optional[list[str]] = None,
    use_routing: bool = True,
    use_rerank: bool = True,
) -> list[dict]:
    """
    完整检索管线。

    Args:
        query:       用户 query（已经过 rewriting 或原始）
        top_k:       最终返回数量
        sources:     强制指定文档源（None = 自动路由）
        use_routing: 是否启用 source routing
        use_rerank:  是否启用 reranker

    Returns:
        list of chunk dicts，含 text / source / page / section 及各阶段分数
    """
    # 1. Source Routing
    if sources is None:
        sources = route_sources(query) if use_routing else []

    # 2. 双路检索
    vec_res  = vector_search(query, sources)
    bm25_res = bm25_search(query, sources)

    # 3. RRF 融合
    fused = reciprocal_rank_fusion(vec_res, bm25_res)
    candidates = fused[:RETRIEVE_TOP_K * 2]  # 送给 reranker 的候选池

    # 4. Reranking
    if use_rerank and candidates:
        results = rerank(query, candidates, top_n=top_k)
    else:
        results = candidates[:top_k]

    return results


def format_context(results: list[dict]) -> str:
    """将检索结果格式化为 LLM 可用的 context 字符串"""
    parts = []
    for i, r in enumerate(results, 1):
        source  = r.get("source", "unknown")
        page    = r.get("page", "?")
        section = r.get("section", "")
        text    = r.get("text", "")
        parts.append(
            f"[{i}] 来源: {source} | 第{page}页 | {section}\n{text}"
        )
    return "\n\n---\n\n".join(parts)
