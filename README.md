# PULSE-GPT — AI Music Agent

> 自然语言驱动的 EDM 音乐生成与 Ableton Live 智能编辑系统

**TOMI**（**T**rack-aware **O**rchestration via **M**ulti-modal **I**nference）是一个基于 PulseFormer 模型的 AI 音乐 Agent，支持通过对话生成多轨 MIDI、实时推送到 Ableton Live，并用自然语言指令编辑 DAW 中的 MIDI clip。

---

## 系统架构

```
用户输入
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│                   LangGraph Agent Workflow                   │
│                                                             │
│  understand_intent → plan_with_rag → generate → reflect     │
│       │                  ▲               │          │        │
│       │                  └── retry ───────┘ (score<6)│        │
│       │                                      ↓          │        │
│       └→ rag_retrieve → consult        render_audio    │        │
│                                              ↓          │        │
│                                          ableton        │        │
│                                              ↓          │        │
│                                       compose_response  │        │
└─────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
   RAG Server          PulseFormer API      Ableton Bridge
   (port 8001)         (port 8000)          (port 8002)
   Qdrant + LLM        GPU Inference        Socket → Ableton
                                            (port 9877)
```

---

## 核心功能

### 🎵 音乐生成
- 自然语言描述 → 完整多轨 MIDI（Drums / Bass / Chord / Melody）
- 支持能量渐进式结构控制（INTRO → BUILD → DROP → OUTRO）
- PulseFormer 模型（7B 参数，基于 CP-FiLM Transformer）GPU 推理
- LLM-as-Judge 质量评审，不合格自动重试（最多 2 次）

### 🎛️ Ableton Live 集成
- 生成结果自动推送到 Ableton Arrangement View
- 12 种原子 MIDI 编辑操作：`transpose` / `octave_shift` / `velocity_scale` / `quantize` / `humanize` / `thin` / `reverse` / `fill_drums_pattern` / `fill_chord_loop` 等
- Rule-based 指令检测（<1ms），绕过 LLM 直接执行高频操作
- 状态持久化（`data/bridge_state.json`），桥接重启不丢轨道数据

### 📚 RAG 知识库
- 向量检索（Qdrant）+ LLM 重写，支持音乐制作知识问答
- 检索结果注入规划节点，风格参考增强生成参数

### 🌐 Web 界面
- 纯静态 HTML（`agent/static/chat.html`）零框架依赖
- SSE 流式输出，实时显示每个节点执行状态
- 生成模式 + Ableton 编辑模式双模切换
- 音频播放器（WAV/MP3）+ MIDI 下载

---

## 服务一览

| 服务 | 端口 | 启动命令 |
|------|------|---------|
| PulseFormer 推理 API | 8000 | `uvicorn api.server:app --port 8000` |
| RAG 服务 | 8001 | `uvicorn rag.server:app --port 8001` |
| Ableton Bridge | 8002 | `python agent/ableton_bridge.py` |
| Web Server（主入口） | 7860 | `uvicorn agent.web_server:app --port 7860` |
| Ollama（LLM） | 11434 | `ollama serve` |
| Ableton Live RPC | 9877 | Ableton Remote Script 自动启动 |

---

## 快速开始

### 1. 环境要求

- Python 3.10+（Anaconda 推荐）
- NVIDIA GPU（PulseFormer 推理需要 CUDA，显存 ≥ 6GB）
- [Ollama](https://ollama.ai) + `qwen2.5:7b-instruct-q4_K_M` 模型
- Ableton Live 11/12（Ableton 编辑功能可选）

### 2. 安装依赖

```bash
pip install fastapi uvicorn langgraph langchain openai httpx pretty_midi scipy pydub qdrant-client
```

### 3. 配置 Ableton Remote Script（可选）

将 `ableton_remote_script/TOMI_MCP/` 复制到：

```
C:\Users\<用户名>\Documents\Ableton\User Library\Remote Scripts\
```

在 Ableton **Preferences → Link/Tempo/MIDI → Control Surface** 选择 **TOMI_MCP**。

### 4. 启动所有服务

```powershell
# 1. LLM
ollama serve

# 2. PulseFormer（新终端）
uvicorn api.server:app --host 0.0.0.0 --port 8000

# 3. 加载模型（启动后执行一次）
Invoke-WebRequest -Uri "http://localhost:8000/model/load" -Method POST -ContentType "application/json" `
  -Body '{"model_path":"checkpoints/pulsecp_v5_clean_best.pt"}'

# 4. RAG 服务（新终端）
uvicorn rag.server:app --host 0.0.0.0 --port 8001

# 5. Ableton Bridge（新终端）
python agent/ableton_bridge.py

# 6. Web Server（新终端）
uvicorn agent.web_server:app --host 0.0.0.0 --port 7860
```

### 5. 打开界面

```
http://localhost:7860/chat-ui     # Agent 对话界面
http://localhost:7860/showcase    # 项目展示页
```

---

## 目录结构

```
TOMI-GPT/
├── agent/                  # Agent 核心
│   ├── workflow.py         # LangGraph 6 节点工作流
│   ├── tools.py            # 10 个 Agent 工具实现
│   ├── web_server.py       # FastAPI 主服务
│   ├── ableton_bridge.py   # Ableton MCP 桥接层
│   ├── llm_ableton_editor.py  # MIDI 编辑器（12 ops + rule-based）
│   ├── memory.py           # 用户偏好记忆
│   └── static/
│       ├── chat.html       # 对话界面（纯静态）
│       └── showcase.html   # 项目展示页
├── api/
│   └── server.py           # PulseFormer 推理 API
├── core/                   # 模型定义（Tokenizer / Model）
├── rag/                    # RAG 检索服务
│   ├── server.py
│   ├── retriever.py
│   └── ingest.py
├── ableton_remote_script/
│   └── TOMI_MCP/           # Ableton Live Remote Script
├── frontend/               # Next.js 前端（可选）
└── scripts/                # 工具脚本
```

---

## 技术栈

| 层 | 技术 |
|----|------|
| 模型 | PulseFormer（CP-FiLM Transformer，自研） |
| Agent 框架 | LangGraph + LangChain |
| LLM 推理 | Ollama（qwen2.5:7b） |
| 向量检索 | Qdrant |
| 后端 | FastAPI + Uvicorn |
| DAW 集成 | Ableton Live Remote Script（Socket RPC） |
| 前端 | 原生 HTML/CSS/JS（无框架依赖） |

---

## 主要创新点

1. **RAG 增强生成规划** — 检索风格参考后注入 LLM 规划节点，生成参数更贴近目标风格
2. **Ableton MCP 双向集成** — 不仅生成推送，还支持自然语言反向编辑 DAW 中已有 MIDI
3. **Rule-based 指令预处理** — 对高频操作（鼓填充、和弦密度）用正则绕过 LLM，<1ms 响应
4. **LLM-as-Judge 质量闭环** — 生成后自动评分，低于阈值重规划重生成

---

## License

MIT
