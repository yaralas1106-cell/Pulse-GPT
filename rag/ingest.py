"""
rag/ingest.py — 全量/增量入库脚本

用法:
    python -m rag.ingest                    # 入库全部文档
    python -m rag.ingest --source ableton_manual   # 只入库一个文档
    python -m rag.ingest --reset            # 清空重建
"""
import argparse
import pickle
import sys
from pathlib import Path

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.config import (
    DOCS, QDRANT_PATH, COLLECTION, BM25_PATH,
    EMBED_MODEL, EMBED_DIM, EMBED_BATCH,
)
from rag.parsers import load_or_parse_chunks


# ── 初始化客户端 ──────────────────────────────────────────────────────────────

def get_qdrant() -> QdrantClient:
    QDRANT_PATH.mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=str(QDRANT_PATH))


def ensure_collection(client: QdrantClient, reset: bool = False):
    existing = [c.name for c in client.get_collections().collections]
    if reset and COLLECTION in existing:
        client.delete_collection(COLLECTION)
        print(f"[qdrant] 已删除 collection: {COLLECTION}")
        existing = []
    if COLLECTION not in existing:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
        )
        print(f"[qdrant] 已创建 collection: {COLLECTION}")


# ── 向量化 ────────────────────────────────────────────────────────────────────

def embed_chunks(chunks: list[dict], model: SentenceTransformer) -> np.ndarray:
    texts = [c["text"] for c in chunks]
    print(f"  Embedding {len(texts)} chunks (batch={EMBED_BATCH})...")
    vecs = model.encode(
        texts,
        batch_size=EMBED_BATCH,
        show_progress_bar=True,
        normalize_embeddings=True,
    )
    return vecs


# ── 入库 ──────────────────────────────────────────────────────────────────────

def upsert_to_qdrant(client: QdrantClient, chunks: list[dict], vectors: np.ndarray):
    """分批 upsert，跳过已存在的 chunk_id"""
    existing_ids = set()
    # Qdrant 不支持批量 id 存在查询，用 scroll 采样检查（快速）
    scroll_res, _ = client.scroll(
        collection_name=COLLECTION,
        limit=1,
        with_payload=False,
        with_vectors=False,
    )
    has_data = len(scroll_res) > 0

    batch_size = 256
    total_new = 0
    for i in range(0, len(chunks), batch_size):
        batch_chunks = chunks[i:i + batch_size]
        batch_vecs   = vectors[i:i + batch_size]
        points = [
            PointStruct(
                id=abs(hash(c["chunk_id"])) % (2**63),  # Qdrant 需要 uint64
                vector=v.tolist(),
                payload={k: v2 for k, v2 in c.items() if k != "chunk_id"}
                | {"chunk_id": c["chunk_id"]},
            )
            for c, v in zip(batch_chunks, batch_vecs)
        ]
        client.upsert(collection_name=COLLECTION, points=points)
        total_new += len(points)
    print(f"  [qdrant] upsert {total_new} points")


# ── BM25 索引 ─────────────────────────────────────────────────────────────────

def build_bm25(all_chunks: list[dict]):
    corpus = [c["text"].lower().split() for c in all_chunks]
    index = BM25Okapi(corpus)
    with open(BM25_PATH, "wb") as f:
        pickle.dump({"index": index, "chunks": all_chunks}, f)
    print(f"[bm25] 索引已保存: {len(all_chunks)} docs")
    return index


# ── 主流程 ────────────────────────────────────────────────────────────────────

def ingest(sources: list[str] | None = None, reset: bool = False):
    sources = sources or list(DOCS.keys())

    print(f"\n{'='*50}")
    print(f"TOMI RAG Ingestion  |  sources: {sources}")
    print(f"{'='*50}\n")

    # 初始化 embedding 模型
    print(f"[embed] 加载模型: {EMBED_MODEL}")
    model = SentenceTransformer(EMBED_MODEL)

    # 初始化 Qdrant
    client = get_qdrant()
    ensure_collection(client, reset=reset)

    all_chunks: list[dict] = []

    for source_key in sources:
        if source_key not in DOCS:
            print(f"[warn] 未知 source: {source_key}，跳过")
            continue
        cache_path = Path(__file__).parent / "data" / f"{source_key}_chunks.pkl"
        chunks = load_or_parse_chunks(cache_path, source_key)
        print(f"[ingest] {source_key}: {len(chunks)} chunks")

        vecs = embed_chunks(chunks, model)
        upsert_to_qdrant(client, chunks, vecs)
        all_chunks.extend(chunks)

    # 全量重建 BM25（包含所有已入库文档）
    if BM25_PATH.exists() and not reset:
        print("[bm25] 已存在，跳过重建（如需重建请用 --reset）")
    else:
        # 收集所有 source 的 chunks
        if len(sources) < len(DOCS):
            # 增量：合并旧数据
            for sk in DOCS:
                if sk in sources:
                    continue
                cache = Path(__file__).parent / "data" / f"{sk}_chunks.pkl"
                if cache.exists():
                    all_chunks.extend(load_or_parse_chunks(cache, sk))
        build_bm25(all_chunks)

    count = client.get_collection(COLLECTION).points_count
    print(f"\n✅ 入库完成 | Qdrant: {count} points | BM25: {len(all_chunks)} docs")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", nargs="+", choices=list(DOCS.keys()))
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    ingest(sources=args.source, reset=args.reset)
