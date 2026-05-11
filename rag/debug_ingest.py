"""快速诊断 ingest 各步骤是否正常"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

print("Step 1: import qdrant_client...", flush=True)
from qdrant_client import QdrantClient
print("  OK", flush=True)

print("Step 2: import sentence_transformers...", flush=True)
from sentence_transformers import SentenceTransformer
print("  OK", flush=True)

print("Step 3: load BGE-M3 model...", flush=True)
model = SentenceTransformer("BAAI/bge-m3")
print("  OK", flush=True)

print("Step 4: encode test sentence...", flush=True)
vec = model.encode(["hello world"], normalize_embeddings=True)
print(f"  OK, shape={vec.shape}", flush=True)

print("Step 5: parse PulseFormer PDF...", flush=True)
from rag.parsers import load_or_parse_chunks
cache_path = Path(__file__).parent / "data" / "pulseformer_paper_chunks.pkl"
chunks = load_or_parse_chunks(cache_path, "pulseformer_paper")
print(f"  OK, {len(chunks)} chunks", flush=True)

print("\n✅ 所有步骤正常", flush=True)
