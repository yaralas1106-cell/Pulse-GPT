"""
rag/config.py — 集中配置，所有路径/模型/参数在此调整
"""
from pathlib import Path

# ── 项目根 ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent

# ── 文档源 ────────────────────────────────────────────────────────────────────
DOCS = {
    "music_tutorial": {
        "path": Path(r"D:\aespa\Heme\HEME笔记\HEMe 第五届课堂笔记最终版 - 20251107"),
        "type": "tutorial",
        "glob": "*.pdf",
        "desc": "音乐制作课堂笔记（中文PDFs）",
    },
    "pulseformer_paper": {
        "path": ROOT / "docs" / "paper_draft.pdf",
        "type": "paper",
        "glob": None,
        "desc": "PulseFormer学术论文",
    },
    "ableton_manual": {
        "path": ROOT / "docs" / "live11-manual-en.pdf",
        "type": "manual",
        "glob": None,
        "desc": "Ableton Live 11 使用手册",
    },
}

# ── 切分参数 ──────────────────────────────────────────────────────────────────
CHUNK_SIZE   = 512   # 目标token数（用字符数近似，中文×1.5 系数）
CHUNK_OVERLAP = 64

# ── Embedding 模型 ────────────────────────────────────────────────────────────
EMBED_MODEL  = "BAAI/bge-m3"          # 支持中英双语
EMBED_DIM    = 1024
EMBED_BATCH  = 32

# ── Reranker 模型 ─────────────────────────────────────────────────────────────
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"

# ── Qdrant ────────────────────────────────────────────────────────────────────
QDRANT_PATH  = ROOT / "rag" / "data" / "qdrant"
COLLECTION   = "tomi_rag"

# ── BM25 持久化 ───────────────────────────────────────────────────────────────
BM25_PATH    = ROOT / "rag" / "data" / "bm25_corpus.pkl"

# ── 检索参数 ──────────────────────────────────────────────────────────────────
RETRIEVE_TOP_K  = 10   # 每路召回数量
RERANK_TOP_K    = 3    # 最终返回数量
HYBRID_ALPHA    = 0.6  # 向量分占比（1-alpha 给 BM25）

# ── Source routing 关键词 ─────────────────────────────────────────────────────
SOURCE_KEYWORDS = {
    "ableton_manual": [
        "ableton", "live", "session", "arrangement", "clip", "track", "device",
        "plugin", "vst", "midi", "audio", "mixer", "eq", "compressor", "warp",
        "scene", "launch", "tempo", "quantize", "automation", "return", "send",
        "channel", "rack", "drum rack", "instrument rack",
    ],
    "pulseformer_paper": [
        "pulseformer", "elevel", "e_level", "film", "featurewise", "token",
        "time-major", "track-major", "compound", "bpm", "struct", "energy level",
        "stitching", "anchor", "scheduler", "drop", "buildup", "intro", "outro",
        "density", "bar", "inference", "generation", "transformer",
    ],
    "music_tutorial": [
        "混音", "编曲", "音乐理论", "和弦", "调式", "旋律", "节奏", "bass",
        "鼓组", "采样", "音色", "合成器", "效果器", "混响", "延时", "压缩",
        "eq", "饱和", "sidechain", "sidechaining", "制作", "写歌", "乐理",
        "大调", "小调", "五度圈", "贝斯线", "人声", "flow",
    ],
}
