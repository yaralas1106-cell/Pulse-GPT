"""
agent/agent.py
==============
Music Agent — Claude API 对话循环 + tool_use 编排。

调用方式：
    from agent.agent import MusicAgent
    agent = MusicAgent()
    response = agent.chat(session_id, user_message)
"""

import os
import json
from openai import OpenAI

from agent.tools import ALL_SCHEMAS, dispatch_tool
from agent import memory as mem_store

SYSTEM_PROMPT = """你是 TOMI Music Agent，一个专业的 AI 音乐创作助手。

你的能力：
1. **音乐生成**：理解用户的音乐需求，规划歌曲蓝图，调用 PulseFormer 生成多轨 MIDI
2. **音乐修改**：锁定部分轨道，只重新生成用户指定的轨道（regenerate_track）
3. **知识咨询**：通过 ask_knowledge 查询音乐制作知识库（侧链压缩、EQ、Ableton 操作、PulseFormer 论文等）
4. **DAW 集成**：将生成的 MIDI 直接导入 Ableton Live（需要 Ableton 运行）
5. **用户记忆**：记住用户的音乐风格偏好，下次更好地服务

路径判断：
- 用户问"如何/怎么/什么是" → 先用 ask_knowledge 查知识库
- 用户要"生成/做一首/创作" → plan_song → generate_music → render_audio
- 用户要"改一下/换个/重做某轨" → regenerate_track
- 用户要"导入 Ableton/在 Ableton 里" → import_stems_to_ableton（先确认 Ableton 已运行）

工具调用规范：
- 生成流程：recall_memory → plan_song → generate_music → render_audio
- 咨询流程：ask_knowledge → 直接回答（引用来源）
- 修改流程：regenerate_track → render_audio
- Ableton 流程：setup_ableton_template → import_stems_to_ableton

重要约束：
- BPM 必须在 60–220 之间，e_level 在 1–8 之间
- key 格式为 C_MAJOR / A_MINOR 等
- Ableton 工具失败时，友好说明需要先启动 Ableton Live 并加载 Remote Script

回复用中文，语气自然专业。生成成功后告知用户可播放或下载，并简述生成的音乐特点。"""

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL    = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-instruct-q4_K_M")
MAX_TOKENS = 4096

# Convert Anthropic-style tool schemas to OpenAI function-calling format
def _to_openai_tools(schemas: list) -> list:
    return [
        {
            "type": "function",
            "function": {
                "name":        s["name"],
                "description": s["description"],
                "parameters":  s["input_schema"],
            },
        }
        for s in schemas
    ]

OPENAI_TOOLS = _to_openai_tools(ALL_SCHEMAS)


class MusicAgent:
    def __init__(self):
        self.client = OpenAI(
            base_url=OLLAMA_BASE_URL,
            api_key="ollama",  # Ollama doesn't need a real key
        )
        self._sessions: dict[str, list] = {}

    def _get_messages(self, session_id: str) -> list:
        if session_id not in self._sessions:
            self._sessions[session_id] = []
        return self._sessions[session_id]

    def chat(self, session_id: str, user_message: str) -> dict:
        messages = self._get_messages(session_id)
        memory_store = mem_store.load(session_id)

        if not messages:
            messages.append({"role": "system", "content": SYSTEM_PROMPT})

        messages.append({"role": "user", "content": user_message})

        result_text = ""
        audio_url   = None
        midi_url    = None

        # Agentic loop
        while True:
            response = self.client.chat.completions.create(
                model=OLLAMA_MODEL,
                max_tokens=MAX_TOKENS,
                tools=OPENAI_TOOLS,
                tool_choice="auto",
                messages=messages,
            )

            msg = response.choices[0].message
            messages.append(msg.model_dump(exclude_none=True))

            finish = response.choices[0].finish_reason

            if finish == "stop" or not msg.tool_calls:
                result_text = msg.content or ""
                break

            # Execute tool calls
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                tool_result = dispatch_tool(tc.function.name, args, memory_store)

                if tc.function.name == "render_audio" and tool_result.get("status") == "ok":
                    audio_url = tool_result.get("audio_url")
                if tc.function.name == "generate_music" and tool_result.get("status") == "ok":
                    midi_url = f"/midi/{tool_result['midi_file_id']}"

                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      json.dumps(tool_result, ensure_ascii=False),
                })

        mem_store.save(session_id, memory_store)

        return {
            "text":      result_text,
            "audio_url": audio_url,
            "midi_url":  midi_url,
        }

    def chat_stream(self, session_id: str, user_message: str):
        """
        Generator that yields SSE-compatible dicts for each agent step.
        Yields:
          {"type": "tool_call",   "name": str, "input": dict}
          {"type": "tool_result", "name": str, "result": dict}
          {"type": "done",        "text": str, "audio_url": str|None, "midi_url": str|None}
          {"type": "error",       "message": str}
        """
        messages = self._get_messages(session_id)
        memory_store = mem_store.load(session_id)

        if not messages:
            messages.append({"role": "system", "content": SYSTEM_PROMPT})

        messages.append({"role": "user", "content": user_message})

        audio_url = None
        midi_url  = None

        try:
            while True:
                response = self.client.chat.completions.create(
                    model=OLLAMA_MODEL,
                    max_tokens=MAX_TOKENS,
                    tools=OPENAI_TOOLS,
                    tool_choice="auto",
                    messages=messages,
                )

                msg    = response.choices[0].message
                finish = response.choices[0].finish_reason
                messages.append(msg.model_dump(exclude_none=True))

                if finish == "stop" or not msg.tool_calls:
                    mem_store.save(session_id, memory_store)
                    yield {
                        "type":      "done",
                        "text":      msg.content or "",
                        "audio_url": audio_url,
                        "midi_url":  midi_url,
                    }
                    return

                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}

                    yield {"type": "tool_call", "name": tc.function.name, "input": args}

                    tool_result = dispatch_tool(tc.function.name, args, memory_store)

                    if tc.function.name == "render_audio" and tool_result.get("status") == "ok":
                        audio_url = tool_result.get("audio_url")
                    if tc.function.name == "generate_music" and tool_result.get("status") == "ok":
                        midi_url = f"/midi/{tool_result['midi_file_id']}"

                    yield {"type": "tool_result", "name": tc.function.name, "result": tool_result}

                    messages.append({
                        "role":         "tool",
                        "tool_call_id": tc.id,
                        "content":      json.dumps(tool_result, ensure_ascii=False),
                    })
        except Exception as exc:
            yield {"type": "error", "message": str(exc)}

    def reset_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
