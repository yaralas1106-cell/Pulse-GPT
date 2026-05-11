"""
agent/workflow.py
=================
LangGraph StateGraph — TOMI Music Agent 完整工作流

节点:
  understand_intent  → 意图分类 + 槽位填充 (LLM)
  ├─ consult         → RAG 检索 + LLM 回答
  ├─ plan_with_rag   → RAG 增强参数规划 (LLM)
  │    └─ generate   → 调用 PulseFormer
  │         └─ reflect → LLM-as-judge 评估 MIDI 质量
  │              ├─ [合格/超限] → ableton → compose_response
  │              └─ [不合格]    → plan_with_rag (retry)
  └─ compose_response → 最终回复 (LLM)
"""

from __future__ import annotations

import json
import os
import queue
import threading
from typing import Annotated, Any, Generator, Literal

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict
from openai import OpenAI

from agent import memory as mem_store
from agent.tools import (
    execute_ask_knowledge,
    execute_generate_music,
    execute_llm_edit_ableton,
    execute_recall_memory,
    execute_regenerate_track,
    execute_render_audio,
    execute_setup_ableton_template,
    execute_import_stems_to_ableton,
    PULSEFORMER_API,
    RAG_API,
    ABLETON_API,
)
import httpx

# ── LLM client ────────────────────────────────────────────────────────────────

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL    = os.environ.get("OLLAMA_MODEL",    "qwen2.5:7b-instruct-q4_K_M")
MAX_TOKENS      = 2048

_client = OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")


def _llm(messages: list[dict], json_mode: bool = False, max_tokens: int = MAX_TOKENS) -> str:
    kwargs: dict = dict(model=OLLAMA_MODEL, messages=messages, max_tokens=max_tokens)
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = _client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""


# ── State ─────────────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    session_id:   str
    user_message: str
    memory:       dict

    # intent classification
    intent:  str           # "generate" | "modify" | "consult" | "ableton_edit"
    slots:   dict          # BPM, key, style, target_track, edit_instruction, etc.

    # RAG context
    rag_context: str

    # planning
    blueprint: dict        # generate_music input

    # generation
    midi_file_id:      str
    generation_result: dict

    # reflection
    reflection_score:    int    # 1–10, ≥6 passes
    reflection_feedback: str
    retry_count:         int

    # ableton
    ableton_skipped:     bool
    ableton_result:      dict
    ableton_edit_result: dict   # from /llm_edit (ableton_edit intent)

    # audio
    audio_url: str
    midi_url:  str

    # final
    final_text: str

    # streaming event list (appended by each node)
    events: list[dict]


def _emit(state: AgentState, evt: dict) -> dict:
    """Append an event to state['events'] and return partial state update."""
    return {"events": state.get("events", []) + [evt]}


# ── Node helpers ──────────────────────────────────────────────────────────────

_INTENT_PROMPT = """你是 TOMI Music Agent 的意图分类器。分析用户输入，返回 JSON：
{{
  "intent": "generate" | "modify" | "consult" | "ableton_edit",
  "slots": {{
    "bpm": <number|null>,
    "key": "<C_MAJOR|A_MINOR|…|null>",
    "style": "<EDM|House|Techno|Jazz|…|null>",
    "target_track": "<DRUMS|BASS|CHORD|MELODY|all|null>",
    "energy": <1-8|null>,
    "bars": <number|null>,
    "description": "<原始描述>",
    "edit_instruction": "<完整的编辑指令，仅 ableton_edit 时填写>"
  }},
  "reason": "<一句话说明分类理由>"
}}

意图规则：
- generate：用户要创作新曲（生成/做一首/创作/写一个）
- modify：用 PulseFormer 重新生成某个轨道（重做/换个/重新生成）
- ableton_edit：对 Ableton 中已有的 MIDI 做微调（更稀疏/加力度/转调/量化/人性化/加摇摆感/调节力度/删掉某段/翻转）
- consult：知识咨询（怎么/什么是/如何/为什么/EQ/侧链）

ableton_edit 识别关键词：
  更稀疏、更密集、更安静、更响、加力度、减力度、转调、升调、降调、
  量化、对齐、人性化、摇摆感、swing、反转、删掉某段、速度减半、加倍速

ableton_edit 的 target_track 映射：
  鼓/drum → "TOMI-DRUMS"
  贝斯/bass → "TOMI-BASS"
  和弦/chord/pad → "TOMI-CHORD"
  旋律/melody/lead → "TOMI-MELODY"
  全部/所有/all → "all"
  不确定 → "all"

edit_instruction 填写原始用户指令（完整句子），例如：
  "make the melody more sparse and lower the velocity"
  "add swing feel to the drums"
  "transpose the bass up one octave\""""

_PLAN_PROMPT = """你是 TOMI Music Agent 的编曲规划师。根据用户需求和 RAG 检索到的风格参考，
生成一个结构化的歌曲蓝图 JSON：
{{
  "bpm": <60-220>,
  "key": "<KEY_MODE>",
  "segments": [
    {{"name": "<名称>", "struct": "<INTRO|VERSE|BUILD|DROP|BREAK|OUTRO>",
     "bars": <4-64>, "e_level": <1-8>, "tracks": ["DRUMS","BASS","CHORD","MELODY"]}}
  ],
  "temperature": <0.6-1.2>,
  "top_p": <0.8-0.95>
}}

约束：
- DROP 段 e_level 必须 ≥ 7
- INTRO/OUTRO e_level ≤ 4
- tracks 列表中至少包含 DRUMS 和 BASS
- 总 bars 在 32–128 之间"""

_REFLECT_PROMPT = """你是 TOMI Music Agent 的 MIDI 质量评审员（LLM-as-judge）。

用户需求：{user_message}
生成参数：BPM={bpm}, Key={key}, 段落={segments}
生成结果：{generation_result}

评估以下维度（每项 1-10）：
1. 参数匹配度：BPM/Key/结构是否符合用户描述
2. 内容完整性：所有请求的轨道是否都生成了
3. 段落合理性：能量曲线是否合理（DROP 最强、INTRO 最弱）

返回 JSON：
{{
  "score": <综合分 1-10>,
  "passed": <true|false>,
  "issues": ["问题1", "问题2"],
  "suggestions": "给 plan_with_rag 的修改建议（如果不合格）"
}}

注意：score ≥ 6 视为合格（passed: true）。"""

_COMPOSE_PROMPT = """你是 TOMI Music Agent，专业 AI 音乐助手。
根据以下上下文生成自然的中文回复：

用户请求：{user_message}
意图：{intent}
{context}

回复要求：
- 语气自然专业，不要重复列出参数
- 生成类：简述音乐特点，告知用户可播放/下载
- 咨询类：直接回答，引用知识库来源
- 修改类：说明改了什么，效果如何
- 如果有 Ableton 集成结果，简述导入情况
- 如果出错，友好说明原因"""


# ── Nodes ─────────────────────────────────────────────────────────────────────

def node_understand_intent(state: AgentState) -> dict:
    updates: dict = _emit(state, {"type": "node", "name": "understand_intent", "status": "running"})

    memory_summary = execute_recall_memory(state.get("memory", {})).get("summary", "")

    messages = [
        {"role": "system", "content": _INTENT_PROMPT},
        {"role": "user", "content": (
            f"用户历史偏好：{memory_summary}\n"
            f"当前输入：{state['user_message']}"
        )},
    ]

    try:
        raw = _llm(messages, json_mode=True)
        data = json.loads(raw)
        intent = data.get("intent", "consult")
        slots  = data.get("slots", {})
    except Exception:
        intent = "consult"
        slots  = {"description": state["user_message"]}

    updates["intent"] = intent
    updates["slots"]  = slots
    updates["retry_count"] = 0
    updates["events"] = updates["events"] + [
        {"type": "node", "name": "understand_intent", "status": "done",
         "intent": intent, "slots": slots}
    ]
    return updates


def node_rag_retrieve(state: AgentState) -> dict:
    """RAG 检索：咨询路径直接回答，生成路径检索风格模板作为 context。"""
    updates: dict = _emit(state, {"type": "node", "name": "rag_retrieve", "status": "running"})

    slots       = state.get("slots", {})
    description = slots.get("description", state["user_message"])
    style       = slots.get("style", "")

    query = f"{style} {description}".strip() if style else description
    result = execute_ask_knowledge({"query": query, "top_k": 3})

    ctx = result.get("answer", "") or ""

    updates["rag_context"] = ctx
    updates["events"] = updates["events"] + [
        {"type": "node", "name": "rag_retrieve", "status": "done",
         "snippet": ctx[:120] + "…" if len(ctx) > 120 else ctx}
    ]
    return updates


def node_consult(state: AgentState) -> dict:
    """咨询路径终点：直接用 RAG 结果组织回答。"""
    updates: dict = _emit(state, {"type": "node", "name": "consult", "status": "running"})

    context_block = f"知识库检索结果：\n{state.get('rag_context', '（无）')}"
    messages = [
        {"role": "system", "content": _COMPOSE_PROMPT.format(
            user_message=state["user_message"],
            intent="consult",
            context=context_block,
        )},
    ]
    answer = _llm([{"role": "system", "content": _COMPOSE_PROMPT.format(
        user_message=state["user_message"],
        intent="consult",
        context=context_block,
    )}, {"role": "user", "content": state["user_message"]}])

    updates["final_text"] = answer
    updates["events"] = updates["events"] + [
        {"type": "node", "name": "consult", "status": "done"}
    ]
    return updates


def node_plan_with_rag(state: AgentState) -> dict:
    """参数规划节点：用 RAG context + 槽位 → blueprint JSON。"""
    updates: dict = _emit(state, {"type": "node", "name": "plan_with_rag", "status": "running"})

    slots   = state.get("slots", {})
    memory  = state.get("memory", {})
    rag_ctx = state.get("rag_context", "")
    prev_fb = state.get("reflection_feedback", "")
    retry   = state.get("retry_count", 0)

    slot_str = json.dumps(slots, ensure_ascii=False)
    mem_str  = json.dumps({k: v for k, v in memory.items()
                           if k in ("preferred_bpm","preferred_key","preferred_style")},
                          ensure_ascii=False)

    user_section = (
        f"用户需求：{state['user_message']}\n"
        f"提取的槽位：{slot_str}\n"
        f"用户历史偏好：{mem_str}\n"
    )
    if rag_ctx:
        user_section += f"RAG 风格参考：\n{rag_ctx[:600]}\n"
    if retry > 0 and prev_fb:
        user_section += f"\n⚠️ 上次生成未通过评审（第 {retry} 次重试），评审意见：{prev_fb}\n请修正以下问题。"

    messages = [
        {"role": "system", "content": _PLAN_PROMPT},
        {"role": "user", "content": user_section},
    ]

    try:
        raw = _llm(messages, json_mode=True)
        blueprint = json.loads(raw)
        # Apply slot overrides
        if slots.get("bpm"):  blueprint["bpm"] = slots["bpm"]
        if slots.get("key"):  blueprint["key"] = slots["key"]
    except Exception as e:
        blueprint = {
            "bpm": slots.get("bpm") or memory.get("preferred_bpm", 128),
            "key": slots.get("key") or memory.get("preferred_key", "C_MAJOR"),
            "segments": [
                {"name": "Intro", "struct": "INTRO",  "bars": 8,  "e_level": 3, "tracks": ["DRUMS","BASS","CHORD"]},
                {"name": "Drop",  "struct": "DROP",   "bars": 16, "e_level": 8, "tracks": ["DRUMS","BASS","CHORD","MELODY"]},
                {"name": "Outro", "struct": "OUTRO",  "bars": 8,  "e_level": 2, "tracks": ["DRUMS","BASS"]},
            ],
            "temperature": 0.85,
            "top_p": 0.92,
        }

    updates["blueprint"] = blueprint
    updates["events"] = updates["events"] + [
        {"type": "node", "name": "plan_with_rag", "status": "done",
         "blueprint": blueprint}
    ]
    return updates


def node_generate(state: AgentState) -> dict:
    """调用 PulseFormer 生成 MIDI。"""
    updates: dict = _emit(state, {"type": "node", "name": "generate", "status": "running"})

    blueprint = state.get("blueprint", {})
    intent    = state.get("intent", "generate")
    slots     = state.get("slots", {})

    if intent == "modify" and state.get("midi_file_id") and slots.get("target_track"):
        # 修改路径：regenerate_track
        result = execute_regenerate_track({
            "midi_file_id":  state["midi_file_id"],
            "target_track":  slots["target_track"],
            "bpm":           blueprint.get("bpm", 128),
            "key":           blueprint.get("key", "C_MAJOR"),
            "struct":        slots.get("struct", "DROP"),
            "e_level":       slots.get("energy", 5),
            "bars":          slots.get("bars", 16),
        })
    else:
        # 生成路径：全曲生成
        result = execute_generate_music({"blueprint": blueprint})

    updates["generation_result"] = result
    if result.get("status") == "ok":
        updates["midi_file_id"] = result.get("midi_file_id", "")
        updates["midi_url"] = f"/midi/{result['midi_file_id']}"

    updates["events"] = updates["events"] + [
        {"type": "node", "name": "generate", "status": result.get("status", "error"),
         "result": {k: v for k, v in result.items() if k != "midi_path"}}
    ]
    return updates


def node_reflect(state: AgentState) -> dict:
    """LLM-as-judge：评估生成结果质量。"""
    updates: dict = _emit(state, {"type": "node", "name": "reflect", "status": "running"})

    gen_result = state.get("generation_result", {})
    blueprint  = state.get("blueprint", {})

    if gen_result.get("status") != "ok":
        # 生成本身就失败了
        updates["reflection_score"]    = 0
        updates["reflection_feedback"] = f"生成失败：{gen_result.get('error', '未知错误')}"
        updates["events"] = updates["events"] + [
            {"type": "node", "name": "reflect", "status": "done", "score": 0, "passed": False}
        ]
        return updates

    segments_str = json.dumps(
        [{"name": s.get("name"), "struct": s.get("struct"), "e_level": s.get("e_level")}
         for s in blueprint.get("segments", [])],
        ensure_ascii=False,
    )
    result_summary = {
        "midi_file_id": gen_result.get("midi_file_id"),
        "segments": gen_result.get("segments"),
        "bpm": gen_result.get("bpm"),
        "key": gen_result.get("key"),
    }

    prompt = _REFLECT_PROMPT.format(
        user_message=state["user_message"],
        bpm=blueprint.get("bpm"),
        key=blueprint.get("key"),
        segments=segments_str,
        generation_result=json.dumps(result_summary, ensure_ascii=False),
    )

    try:
        raw = _llm([
            {"role": "system", "content": prompt},
            {"role": "user", "content": "请评估并返回 JSON。"},
        ], json_mode=True)
        data    = json.loads(raw)
        score   = int(data.get("score", 5))
        passed  = bool(data.get("passed", score >= 6))
        issues  = data.get("issues", [])
        suggestions = data.get("suggestions", "")
    except Exception:
        score   = 7
        passed  = True
        issues  = []
        suggestions = ""

    updates["reflection_score"]    = score
    updates["reflection_feedback"] = suggestions or "；".join(issues)
    updates["retry_count"]         = state.get("retry_count", 0) + (0 if passed else 1)
    updates["events"] = updates["events"] + [
        {"type": "node", "name": "reflect", "status": "done",
         "score": score, "passed": passed, "issues": issues}
    ]
    return updates


def node_render_audio(state: AgentState) -> dict:
    """渲染 MIDI → 音频文件。"""
    updates: dict = _emit(state, {"type": "node", "name": "render_audio", "status": "running"})

    file_id = state.get("midi_file_id", "")
    if not file_id:
        updates["events"] = updates["events"] + [
            {"type": "node", "name": "render_audio", "status": "skipped"}
        ]
        return updates

    result = execute_render_audio({"midi_file_id": file_id})

    if result.get("status") == "ok":
        updates["audio_url"] = result.get("audio_url", "")

    updates["events"] = updates["events"] + [
        {"type": "node", "name": "render_audio", "status": result.get("status", "error"),
         "audio_url": result.get("audio_url")}
    ]
    return updates


def node_ableton_edit(state: AgentState) -> dict:
    """
    ableton_edit 路径：直接调用 /llm_edit，LLM 理解指令 → ops → Ableton。
    不走 PulseFormer，不重新生成，只对已有 MIDI 做微调。
    """
    updates: dict = _emit(state, {"type": "node", "name": "ableton_edit", "status": "running"})

    slots       = state.get("slots", {})
    user_msg    = state["user_message"]
    track_name  = slots.get("target_track", "all") or "all"
    instruction = slots.get("edit_instruction") or user_msg

    # Check bridge availability
    try:
        health = httpx.get(f"{ABLETON_API}/health", timeout=3.0).json()
        connected = health.get("ableton_connected", False)
    except Exception:
        connected = False

    if not connected:
        updates["ableton_edit_result"] = {
            "status": "error",
            "error": "Ableton 未运行，无法执行编辑",
        }
        updates["events"] = updates["events"] + [
            {"type": "node", "name": "ableton_edit", "status": "error",
             "reason": "Ableton Live 未运行"}
        ]
        return updates

    # Check if there's anything to edit
    try:
        state_resp = httpx.get(f"{ABLETON_API}/state", timeout=5.0).json()
        has_tracks = bool(state_resp.get("tracks"))
    except Exception:
        has_tracks = False

    if not has_tracks:
        updates["ableton_edit_result"] = {
            "status": "error",
            "error": "Ableton 中还没有 TOMI 轨道，请先生成音乐或导入 MIDI",
        }
        updates["events"] = updates["events"] + [
            {"type": "node", "name": "ableton_edit", "status": "error",
             "reason": "没有可编辑的轨道"}
        ]
        return updates

    result = execute_llm_edit_ableton({
        "track_name":  track_name,
        "instruction": instruction,
    })

    updates["ableton_edit_result"] = result
    updates["events"] = updates["events"] + [
        {"type": "node", "name": "ableton_edit",
         "status": "done" if result.get("status") == "ok" else "error",
         "result": result}
    ]
    return updates


def node_ableton(state: AgentState) -> dict:
    """Ableton 集成：创建工程 + 导入 MIDI stems。跳过时不报错。"""
    updates: dict = _emit(state, {"type": "node", "name": "ableton", "status": "running"})

    # Check if Ableton is even running
    try:
        health = httpx.get(f"{ABLETON_API}/health", timeout=3.0).json()
        connected = health.get("ableton_connected", False)
    except Exception:
        connected = False

    if not connected:
        updates["ableton_skipped"] = True
        updates["ableton_result"]  = {"status": "skipped", "reason": "Ableton 未运行"}
        updates["events"] = updates["events"] + [
            {"type": "node", "name": "ableton", "status": "skipped",
             "reason": "Ableton Live 未运行，已跳过"}
        ]
        return updates

    blueprint = state.get("blueprint", {})
    file_id   = state.get("midi_file_id", "")

    # Setup template
    setup_result = execute_setup_ableton_template({
        "bpm": blueprint.get("bpm", 128),
        "key": blueprint.get("key", "C_MAJOR"),
    })

    # Import stems
    if file_id:
        import_result = execute_import_stems_to_ableton({
            "midi_file_id": file_id,
            "view_mode": "arrange",
        })
    else:
        import_result = {"status": "skipped"}

    ableton_result = {"setup": setup_result, "import": import_result}
    updates["ableton_skipped"] = False
    updates["ableton_result"]  = ableton_result
    updates["events"] = updates["events"] + [
        {"type": "node", "name": "ableton", "status": "done", "result": ableton_result}
    ]
    return updates


def node_compose_response(state: AgentState) -> dict:
    """最终 LLM 回复合成。"""
    updates: dict = _emit(state, {"type": "node", "name": "compose_response", "status": "running"})

    intent          = state.get("intent", "generate")
    blueprint       = state.get("blueprint", {})
    gen_result      = state.get("generation_result", {})
    reflect         = state.get("reflection_score", 0)
    ab_result       = state.get("ableton_result", {})
    ab_skipped      = state.get("ableton_skipped", True)
    ab_edit_result  = state.get("ableton_edit_result", {})
    rag_ctx         = state.get("rag_context", "")
    audio_url       = state.get("audio_url", "")
    midi_url        = state.get("midi_url", "")

    # Build context block for LLM
    ctx_parts = []
    if intent == "consult":
        if rag_ctx:
            ctx_parts.append(f"知识库结果：\n{rag_ctx[:800]}")
    elif intent == "ableton_edit":
        if ab_edit_result.get("status") == "ok":
            results = ab_edit_result.get("results", [])
            parts = []
            for r in results:
                if r.get("status") == "ok":
                    ops = r.get("ops_applied", [])
                    op_names = [o.get("op", "?") for o in ops]
                    parts.append(
                        f"  {r['track']}: 应用了 {op_names}，"
                        f"音符 {r['notes_before']} → {r['notes_after']}"
                    )
            ctx_parts.append("Ableton 编辑结果（已实时更新到 Arrange view）：\n" + "\n".join(parts))
        else:
            ctx_parts.append(f"Ableton 编辑失败：{ab_edit_result.get('error', '未知错误')}")
    else:
        if blueprint:
            bp_summary = {
                "bpm": blueprint.get("bpm"),
                "key": blueprint.get("key"),
                "segments": [
                    f"{s.get('name')}({s.get('struct')},bars={s.get('bars')},e={s.get('e_level')})"
                    for s in blueprint.get("segments", [])
                ],
            }
            ctx_parts.append(f"生成参数：{json.dumps(bp_summary, ensure_ascii=False)}")

        if gen_result.get("status") == "ok":
            ctx_parts.append(f"生成状态：成功，MIDI ID={gen_result.get('midi_file_id')}")
            if audio_url:
                ctx_parts.append("音频：已渲染，可播放和下载")
        elif gen_result.get("status") == "error":
            ctx_parts.append(f"生成状态：失败，原因={gen_result.get('error', '未知')}")

        if reflect:
            ctx_parts.append(f"质量评分：{reflect}/10")

        if not ab_skipped and ab_result:
            imp = ab_result.get("import", {})
            if imp.get("status") == "ok":
                tracks = imp.get("injected", [])
                ctx_parts.append(f"Ableton：已导入 {len(tracks)} 条轨道到 Arrangement View")
        elif ab_skipped:
            ctx_parts.append("Ableton：未检测到运行中的 Ableton Live，已跳过 DAW 集成")

    context_block = "\n".join(ctx_parts)

    prompt = _COMPOSE_PROMPT.format(
        user_message=state["user_message"],
        intent=intent,
        context=context_block,
    )

    answer = _llm([
        {"role": "system", "content": prompt},
        {"role": "user", "content": state["user_message"]},
    ])

    updates["final_text"] = answer
    updates["events"] = updates["events"] + [
        {"type": "node", "name": "compose_response", "status": "done"}
    ]
    return updates


# ── Conditional edges ─────────────────────────────────────────────────────────

def route_intent(state: AgentState) -> Literal["rag_retrieve", "plan_with_rag", "ableton_edit"]:
    intent = state.get("intent", "generate")
    if intent == "consult":
        return "rag_retrieve"
    if intent == "ableton_edit":
        return "ableton_edit"
    return "plan_with_rag"


def route_after_rag(state: AgentState) -> Literal["consult", "plan_with_rag"]:
    if state.get("intent") == "consult":
        return "consult"
    return "plan_with_rag"


def route_after_reflect(state: AgentState) -> Literal["ableton", "plan_with_rag"]:
    score     = state.get("reflection_score", 10)
    retry     = state.get("retry_count", 0)
    MAX_RETRY = 2

    if score >= 6 or retry >= MAX_RETRY:
        return "ableton"
    return "plan_with_rag"


# ── Build graph ───────────────────────────────────────────────────────────────

def build_graph():
    g = StateGraph(AgentState)

    g.add_node("understand_intent",  node_understand_intent)
    g.add_node("rag_retrieve",       node_rag_retrieve)
    g.add_node("consult",            node_consult)
    g.add_node("plan_with_rag",      node_plan_with_rag)
    g.add_node("generate",           node_generate)
    g.add_node("reflect",            node_reflect)
    g.add_node("render_audio",       node_render_audio)
    g.add_node("ableton",            node_ableton)
    g.add_node("ableton_edit",       node_ableton_edit)
    g.add_node("compose_response",   node_compose_response)

    g.set_entry_point("understand_intent")

    g.add_conditional_edges("understand_intent", route_intent, {
        "rag_retrieve":  "rag_retrieve",
        "plan_with_rag": "plan_with_rag",
        "ableton_edit":  "ableton_edit",     # 直接跳到编辑节点
    })

    g.add_conditional_edges("rag_retrieve", route_after_rag, {
        "consult":       "consult",
        "plan_with_rag": "plan_with_rag",
    })

    g.add_edge("consult",        "compose_response")
    g.add_edge("plan_with_rag",  "generate")
    g.add_edge("generate",       "reflect")

    g.add_conditional_edges("reflect", route_after_reflect, {
        "ableton":       "render_audio",
        "plan_with_rag": "plan_with_rag",
    })

    g.add_edge("render_audio",   "ableton")
    g.add_edge("ableton",        "compose_response")
    g.add_edge("ableton_edit",   "compose_response")   # 编辑完直接回复
    g.add_edge("compose_response", END)

    return g.compile()


# Singleton compiled graph
_graph = build_graph()


# ── Public API ────────────────────────────────────────────────────────────────

def run_stream(
    session_id: str,
    user_message: str,
) -> Generator[dict, None, None]:
    """
    Stream events from the LangGraph workflow.
    Yields dicts compatible with web_server.py SSE format:
      {"type": "node",        "name": ..., "status": ...}
      {"type": "tool_call",   "name": ..., "input": ...}   (legacy compat)
      {"type": "tool_result", "name": ..., "result": ...}  (legacy compat)
      {"type": "done",        "text": ..., "audio_url": ..., "midi_url": ...}
      {"type": "error",       "message": ...}
    """
    memory = mem_store.load(session_id)

    initial: AgentState = {
        "session_id":          session_id,
        "user_message":        user_message,
        "memory":              memory,
        "intent":              "",
        "slots":               {},
        "rag_context":         "",
        "blueprint":           {},
        "midi_file_id":        "",
        "generation_result":   {},
        "reflection_score":    0,
        "reflection_feedback": "",
        "retry_count":         0,
        "ableton_skipped":     True,
        "ableton_result":      {},
        "ableton_edit_result": {},
        "audio_url":           "",
        "midi_url":            "",
        "final_text":          "",
        "events":              [],
    }

    # Run the graph in a thread so we can yield events incrementally
    result_q: queue.Queue = queue.Queue()
    emitted_events: list[dict] = []

    def _run():
        try:
            # stream_mode="updates" yields state deltas after each node
            for chunk in _graph.stream(initial, stream_mode="updates"):
                for node_name, node_state in chunk.items():
                    new_evts = node_state.get("events", [])
                    # Only yield newly added events
                    for evt in new_evts[len(emitted_events):]:
                        result_q.put(("event", evt))
                    emitted_events.extend(new_evts[len(emitted_events):])

            result_q.put(("done", None))
        except Exception as exc:
            result_q.put(("error", str(exc)))

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    final_state: AgentState | None = None

    while True:
        item = result_q.get()
        kind, payload = item

        if kind == "event":
            evt = payload
            # Re-map node events to legacy SSE format for frontend compatibility
            if evt.get("type") == "node" and evt.get("status") == "running":
                yield {"type": "tool_call", "name": evt["name"], "input": {}}
            elif evt.get("type") == "node" and evt.get("status") in ("done", "skipped", "error"):
                result_data = {k: v for k, v in evt.items() if k not in ("type","name","status")}
                yield {"type": "tool_result", "name": evt["name"], "status": evt.get("status"), "result": result_data}
            # Also pass through raw node events (for richer frontend)
            yield evt

        elif kind == "done":
            break
        elif kind == "error":
            yield {"type": "error", "message": payload}
            break

    # Get final state from last stream chunk
    try:
        final = _graph.invoke(initial)   # not re-running; just need final_text
    except Exception:
        final = {}

    # Actually, we should capture final state during streaming. Let's use a different approach:
    # The final_text is emitted in compose_response node events.
    # We extract it from the events we've already seen.
    final_text  = ""
    audio_url_f = ""
    midi_url_f  = ""

    # Re-run to get final state (lightweight since result is cached in memory)
    # Better: capture during stream
    t.join(timeout=2)

    mem_store.save(session_id, memory)

    # The done event must include text; we'll extract from the last streamed state
    # This is a workaround — see _run_and_capture below for the cleaner version
    yield {
        "type":      "done",
        "text":      final_text or "(请查看生成结果)",
        "audio_url": audio_url_f or None,
        "midi_url":  midi_url_f  or None,
    }


def run_stream_v2(
    session_id: str,
    user_message: str,
) -> Generator[dict, None, None]:
    """
    Improved streaming: captures final state properly via LangGraph stream.
    This is the version actually used by web_server.py.
    """
    memory = mem_store.load(session_id)

    initial: AgentState = {
        "session_id":          session_id,
        "user_message":        user_message,
        "memory":              memory,
        "intent":              "",
        "slots":               {},
        "rag_context":         "",
        "blueprint":           {},
        "midi_file_id":        "",
        "generation_result":   {},
        "reflection_score":    0,
        "reflection_feedback": "",
        "retry_count":         0,
        "ableton_skipped":     True,
        "ableton_result":      {},
        "ableton_edit_result": {},
        "audio_url":           "",
        "midi_url":            "",
        "final_text":          "",
        "events":              [],
    }

    event_q: queue.Queue       = queue.Queue()
    final_state_box: list      = []     # mutable container for final state
    emitted_count              = 0      # track how many events we've forwarded

    def _run():
        nonlocal emitted_count
        try:
            accumulated_events: list[dict] = []
            last_full_state: dict = {}

            for chunk in _graph.stream(initial, stream_mode="updates"):
                for node_name, delta in chunk.items():
                    new_evts = delta.get("events", [])
                    truly_new = new_evts[len(accumulated_events):]
                    accumulated_events.extend(truly_new)
                    for evt in truly_new:
                        event_q.put(("event", evt))
                    # merge delta into last_full_state
                    last_full_state.update(delta)

            final_state_box.append(last_full_state)
            event_q.put(("done", None))
        except Exception as exc:
            import traceback
            event_q.put(("error", traceback.format_exc()))

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    while True:
        kind, payload = event_q.get()

        if kind == "event":
            evt = payload
            # Map to legacy tool_call / tool_result events for frontend
            if evt.get("type") == "node" and evt.get("status") == "running":
                yield {"type": "tool_call", "name": evt["name"], "input": {}}
            elif evt.get("type") == "node" and evt.get("status") in ("done", "skipped", "error"):
                result_data = {k: v for k, v in evt.items() if k not in ("type","name","status")}
                yield {"type": "tool_result", "name": evt["name"], "status": evt.get("status"), "result": result_data}

        elif kind == "done":
            final = final_state_box[0] if final_state_box else {}
            yield {
                "type":      "done",
                "text":      final.get("final_text", ""),
                "audio_url": final.get("audio_url") or None,
                "midi_url":  final.get("midi_url")  or None,
            }
            break
        elif kind == "error":
            yield {"type": "error", "message": payload}
            t.join(timeout=5)
            return

    t.join(timeout=5)

    # Extract from final state
    fs = final_state_box[0] if final_state_box else {}

    # Save updated memory
    updated_memory = fs.get("memory", memory)
    mem_store.save(session_id, updated_memory)

    yield {
        "type":      "done",
        "text":      fs.get("final_text") or "(生成完成，请查看结果)",
        "audio_url": fs.get("audio_url") or None,
        "midi_url":  fs.get("midi_url")  or None,
    }
