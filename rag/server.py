"""
rag/server.py — FastAPI RAG 检索服务

启动:
    python -m rag.server          # 端口 8001
    uvicorn rag.server:app --port 8001 --reload
"""
import sys
import time
import requests
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.retriever import retrieve, format_context, route_sources
from rag.rewriter  import rewrite_query
from rag.config    import RERANK_TOP_K

app = FastAPI(title="TOMI RAG Service", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Schemas ───────────────────────────────────────────────────────────────────

class RetrieveRequest(BaseModel):
    query:        str
    top_k:        int         = Field(RERANK_TOP_K, ge=1, le=20)
    sources:      list[str] | None = None    # None = 自动路由
    rewrite:      bool        = True          # 是否先改写 query
    use_routing:  bool        = True
    use_rerank:   bool        = True
    return_context: bool      = True          # 是否返回拼接好的 context 字符串


class ChunkResult(BaseModel):
    text:          str
    source:        str
    doc_type:      str
    page:          int | None
    section:       str | None
    rerank_score:  float | None = None
    rrf_score:     float | None = None


class RetrieveResponse(BaseModel):
    query:            str
    rewritten_query:  str | None
    original_intent:  str | None
    routed_sources:   list[str]
    chunks:           list[ChunkResult]
    context:          str | None
    latency_ms:       float


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/retrieve", response_model=RetrieveResponse)
def retrieve_endpoint(req: RetrieveRequest):
    t0 = time.time()

    # 1. Query rewriting
    rewritten   = None
    intent      = None
    hint_sources = req.sources or []

    if req.rewrite:
        result = rewrite_query(req.query)
        rewritten    = result.get("rewritten_query", req.query)
        intent       = result.get("original_intent")
        hint_sources = req.sources or result.get("suggested_sources", [])
    else:
        rewritten = req.query

    # 2. Source routing（覆盖 rewriter 的建议，用统一逻辑）
    if req.use_routing and not req.sources:
        routed = route_sources(rewritten or req.query)
        # 合并 rewriter hint
        all_sources = list(set(routed + hint_sources)) or None
    else:
        all_sources = req.sources or None

    routed_sources = all_sources or []

    # 3. Retrieve
    try:
        results = retrieve(
            query        = rewritten or req.query,
            top_k        = req.top_k,
            sources      = all_sources,
            use_routing  = False,   # routing 已在上面做了
            use_rerank   = req.use_rerank,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"检索失败: {str(e)}")

    # 4. 组装 response
    chunks = [
        ChunkResult(
            text          = r.get("text", ""),
            source        = r.get("source", "unknown"),
            doc_type      = r.get("doc_type", ""),
            page          = r.get("page"),
            section       = r.get("section"),
            rerank_score  = r.get("_rerank_score"),
            rrf_score     = r.get("_rrf_score"),
        )
        for r in results
    ]

    context = format_context(results) if req.return_context else None
    latency = (time.time() - t0) * 1000

    return RetrieveResponse(
        query           = req.query,
        rewritten_query = rewritten,
        original_intent = intent,
        routed_sources  = routed_sources,
        chunks          = chunks,
        context         = context,
        latency_ms      = round(latency, 1),
    )


OLLAMA_URL   = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen2.5:7b-instruct-q4_K_M"

SYSTEM_PROMPT = """你是 TOMI，一个专业的音乐制作助手。
你的知识来自三个来源：
1. PulseFormer 学术论文（作者的原创研究）
2. 音乐制作课堂笔记（中文，HEMe 课程）
3. Ableton Live 11 官方手册（英文）

回答时：
- 优先引用知识库内容，说明来源
- 如果知识库没有相关内容，直接说"我的知识库中没有相关信息"
- 回答简洁、专业，中文为主
"""


class ChatRequest(BaseModel):
    query:      str
    top_k:      int  = 5
    use_rerank: bool = False
    stream:     bool = False


class ChatResponse(BaseModel):
    query:     str
    sources:   list[str]
    answer:    str
    latency_ms: float


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest):
    t0 = time.time()

    # 1. 检索
    try:
        results = retrieve(query=req.query, top_k=req.top_k, use_rerank=req.use_rerank)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"检索失败: {str(e)}")

    context = format_context(results)
    sources = list({r.get("source", "") for r in results})

    # 2. 调用 Ollama
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": f"参考资料：\n{context}\n\n问题：{req.query}"},
    ]
    try:
        resp = requests.post(OLLAMA_URL, json={
            "model":    OLLAMA_MODEL,
            "messages": messages,
            "stream":   False,
        }, timeout=120)
        resp.raise_for_status()
        answer = resp.json()["message"]["content"]
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM 调用失败: {str(e)}")

    return ChatResponse(
        query      = req.query,
        sources    = sources,
        answer     = answer,
        latency_ms = round((time.time() - t0) * 1000, 1),
    )


@app.get("/sources")
def list_sources():
    from rag.config import DOCS
    return {k: v["desc"] for k, v in DOCS.items()}


@app.post("/route")
def route_only(body: dict):
    query = body.get("query", "")
    return {"sources": route_sources(query)}


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("rag.server:app", host="0.0.0.0", port=8001, reload=False)
