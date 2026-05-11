"""
rag/rewriter.py — Query Rewriting via Claude

把用户口语化 query（尤其中文音乐描述）改写成检索友好的专业术语 query。
同时输出 source routing hint。
"""
import json
import os
import re

import anthropic

_CLIENT: anthropic.Anthropic | None = None

REWRITE_SYSTEM = """你是一个音乐制作 RAG 系统的 Query 改写器。

你会收到用户的自然语言问题（可能是中文口语、情绪描述或技术问题），你的任务是：
1. 改写成适合向量检索的专业术语 query（中英混合，关键词密度高）
2. 判断最可能相关的知识来源

知识来源有三个：
- ableton_manual：Ableton Live 软件操作、界面、插件、MIDI/Audio 工作流
- pulseformer_paper：PulseFormer 模型、E_level、FiLM、Time-Major Token、生成参数
- music_tutorial：音乐理论、和弦、混音技巧、编曲方法、中文音乐制作教程

输出格式（严格 JSON，不要 markdown 代码块）：
{
  "rewritten_query": "改写后的检索 query",
  "original_intent": "一句话总结用户真实意图",
  "suggested_sources": ["source_key1", "source_key2"]
}"""

REWRITE_EXAMPLES = [
    {
        "user": "我想要那种夜店里炸场的感觉",
        "assistant": '{"rewritten_query": "Big Room House EDM drop sidechain pumping supersaw lead high energy density arrangement", "original_intent": "生成高能量EDM Drop段落", "suggested_sources": ["pulseformer_paper", "music_tutorial"]}',
    },
    {
        "user": "Ableton 里怎么把一个 clip 移到 arrange view？",
        "assistant": '{"rewritten_query": "Ableton Live arrange view drag clip session arrangement duplicate", "original_intent": "Ableton Session→Arrange clip操作", "suggested_sources": ["ableton_manual"]}',
    },
    {
        "user": "E_level 设多少才能有那种 buildup 感觉",
        "assistant": '{"rewritten_query": "PulseFormer E_level energy level buildup section density FiLM conditioning structural scheduler", "original_intent": "PulseFormer Buildup段落参数设置", "suggested_sources": ["pulseformer_paper"]}',
    },
]


def _get_client() -> anthropic.Anthropic:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    return _CLIENT


def rewrite_query(raw_query: str) -> dict:
    """
    改写 query，返回:
    {
      "rewritten_query": str,
      "original_intent": str,
      "suggested_sources": list[str],
    }
    失败时返回原始 query。
    """
    messages = []
    for ex in REWRITE_EXAMPLES:
        messages.append({"role": "user",      "content": ex["user"]})
        messages.append({"role": "assistant", "content": ex["assistant"]})
    messages.append({"role": "user", "content": raw_query})

    try:
        resp = _get_client().messages.create(
            model="claude-haiku-4-5",
            max_tokens=256,
            system=REWRITE_SYSTEM,
            messages=messages,
        )
        text = resp.content[0].text.strip()
        # 提取 JSON（防止模型输出多余文字）
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception as e:
        print(f"[rewriter] 改写失败: {e}")

    return {
        "rewritten_query": raw_query,
        "original_intent": raw_query,
        "suggested_sources": [],
    }
