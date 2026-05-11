"""
rag/evaluate.py — RAG 评测脚本

指标:
  - Recall@K    : 30 个测试 query，期望 source 出现在 top-K 中的比例
  - MRR         : Mean Reciprocal Rank（期望 source 首次出现的排名倒数均值）
  - Latency P50/P95

用法:
    python -m rag.evaluate
    python -m rag.evaluate --server http://localhost:8001  # 调用已启动的服务
"""
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── 测试集：30 个 query ──────────────────────────────────────────────────────
TEST_QUERIES = [
    # ── Ableton Manual (10 queries) ──────────────────────────────────────────
    {"query": "How do I record MIDI in Ableton arrangement view?",
     "expected_source": "ableton_manual"},
    {"query": "Ableton Live session view clip launch quantization settings",
     "expected_source": "ableton_manual"},
    {"query": "How to use the Ableton EQ Eight equalizer",
     "expected_source": "ableton_manual"},
    {"query": "Ableton drum rack pad routing MIDI note",
     "expected_source": "ableton_manual"},
    {"query": "Warp modes in Ableton audio clips",
     "expected_source": "ableton_manual"},
    {"query": "Ableton compressor threshold ratio attack release",
     "expected_source": "ableton_manual"},
    {"query": "How to use return tracks and sends in Ableton",
     "expected_source": "ableton_manual"},
    {"query": "Ableton automation recording draw mode",
     "expected_source": "ableton_manual"},
    {"query": "MIDI instrument rack chain selector macro",
     "expected_source": "ableton_manual"},
    {"query": "How to bounce tracks to audio in Ableton",
     "expected_source": "ableton_manual"},

    # ── PulseFormer Paper (10 queries) ───────────────────────────────────────
    {"query": "What is E_level in PulseFormer and how does it control density?",
     "expected_source": "pulseformer_paper"},
    {"query": "PulseFormer Time-Major token representation cross-track coordination",
     "expected_source": "pulseformer_paper"},
    {"query": "FiLM conditioning energy level affine transformation Transformer",
     "expected_source": "pulseformer_paper"},
    {"query": "Temporal Anchor Stitching section boundary generation",
     "expected_source": "pulseformer_paper"},
    {"query": "PulseFormer structural density score Dt formula features",
     "expected_source": "pulseformer_paper"},
    {"query": "Soft harmonic penalty diatonic scale mask inference",
     "expected_source": "pulseformer_paper"},
    {"query": "Groove Pattern Similarity GPS metric evaluation",
     "expected_source": "pulseformer_paper"},
    {"query": "PulseFormer DAW MCP integration workflow export",
     "expected_source": "pulseformer_paper"},
    {"query": "Ramp Scheduler buildup drop energy transition bars",
     "expected_source": "pulseformer_paper"},
    {"query": "MOS listening test structural coherence groove tightness results",
     "expected_source": "pulseformer_paper"},

    # ── Music Tutorial (10 queries) ──────────────────────────────────────────
    {"query": "如何用压缩器控制鼓组的动态",
     "expected_source": "music_tutorial"},
    {"query": "EDM 中 sidechain 侧链压缩的制作方法",
     "expected_source": "music_tutorial"},
    {"query": "C 大调和 A 小调的关系 平行调",
     "expected_source": "music_tutorial"},
    {"query": "混响的 pre-delay 和 decay 参数如何设置",
     "expected_source": "music_tutorial"},
    {"query": "如何写一个有律动的 bassline 贝斯线",
     "expected_source": "music_tutorial"},
    {"query": "七和弦和延伸音在爵士乐中的使用",
     "expected_source": "music_tutorial"},
    {"query": "EQ 低切 high pass filter 消除低频噪音",
     "expected_source": "music_tutorial"},
    {"query": "如何设计原创鼓组 kick snare hihat 节奏型",
     "expected_source": "music_tutorial"},
    {"query": "合成器 ADSR 包络 音色设计基础",
     "expected_source": "music_tutorial"},
    {"query": "Ableton 中如何使用 Operator 合成器做 acid bass 音色",
     "expected_source": "music_tutorial"},
]


def evaluate_local(top_k: int = 5):
    """直接调用 retriever（不启动服务）"""
    from rag.retriever import retrieve

    recall_hits = []
    mrr_scores  = []
    latencies   = []

    print(f"\n{'='*60}")
    print(f"RAG Evaluation  |  30 queries  |  Recall@{top_k} + MRR")
    print(f"{'='*60}\n")

    for i, item in enumerate(TEST_QUERIES):
        query    = item["query"]
        expected = item["expected_source"]

        t0 = time.time()
        results = retrieve(query, top_k=top_k, use_rerank=True)
        lat = (time.time() - t0) * 1000
        latencies.append(lat)

        sources_ranked = [r.get("source", "") for r in results]

        # Recall@K
        hit = expected in sources_ranked
        recall_hits.append(int(hit))

        # MRR
        rr = 0.0
        for rank, src in enumerate(sources_ranked, 1):
            if src == expected:
                rr = 1.0 / rank
                break
        mrr_scores.append(rr)

        status = "✅" if hit else "❌"
        print(f"[{i+1:02d}] {status} {query[:55]:<55} | expect={expected} | rank={'%d'%sources_ranked.index(expected)+1 if expected in sources_ranked else '-'} | {lat:.0f}ms")

    recall = sum(recall_hits) / len(recall_hits)
    mrr    = sum(mrr_scores) / len(mrr_scores)
    lat_p50 = statistics.median(latencies)
    lat_p95 = sorted(latencies)[int(len(latencies) * 0.95)]

    print(f"\n{'='*60}")
    print(f"Recall@{top_k}  = {recall:.3f}  ({sum(recall_hits)}/{len(recall_hits)})")
    print(f"MRR       = {mrr:.3f}")
    print(f"Latency   P50={lat_p50:.0f}ms  P95={lat_p95:.0f}ms")
    print(f"{'='*60}\n")

    # 保存报告
    report = {
        "recall_at_k": recall,
        "mrr": mrr,
        "k": top_k,
        "latency_p50_ms": lat_p50,
        "latency_p95_ms": lat_p95,
        "per_query": [
            {
                "query": item["query"],
                "expected": item["expected_source"],
                "hit": bool(recall_hits[i]),
                "rr": mrr_scores[i],
                "latency_ms": latencies[i],
            }
            for i, item in enumerate(TEST_QUERIES)
        ],
    }
    report_path = Path(__file__).parent / "data" / "eval_report.json"
    report_path.parent.mkdir(exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"📄 评测报告已保存: {report_path}")
    return report


if __name__ == "__main__":
    evaluate_local(top_k=5)
