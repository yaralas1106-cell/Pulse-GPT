# TOMI-GPT · AI 音乐创作智能体
## 产品经理项目介绍（完整版）

---

## 一、项目背景与核心痛点

### 行业痛点

| 痛点 | 具体表现 | 行业现状 |
|------|----------|----------|
| **专业门槛极高** | Ableton / Logic Pro 学习周期长达数年，普通用户完全无法驾驭 | 90% 有音乐想法的人因技术壁垒无从下手 |
| **AI 生成与 DAW 生态割裂** | Suno / Udio 等工具输出黑盒音频，无法进入专业 DAW 做二次编辑 | 创作者丧失对作品的精细控制权，AI 只能"生成"不能"修改" |
| **专业知识获取断层** | 侧链压缩、EQ 曲线、混音技法等知识分散在论坛、视频中，无法实时调用 | 制作人需要反复查阅资料，打断创作心流 |
| **多模块流程割裂** | 生成 → 编排 → 混音 → 渲染需在多个独立工具间手动搬运数据 | 专业制作人 60%+ 时间消耗在非创作性的流程衔接上 |
| **AI 生成缺乏音乐领域专业性** | 通用 LLM 对 BPM、调性、能量曲线等 EDM 参数理解肤浅 | 生成结果与用户音乐直觉严重脱节 |

### 项目定位

> **TOMI-GPT** 是一个以自然语言为入口、打通「知识检索 → AI 作曲 → DAW 精细编辑 → 音频渲染」全链路的 AI 音乐创作智能体系统。用户只需用中文描述想法，系统自动完成从专业规划到 Ableton 实时写入的完整制作流程。

---

## 二、系统整体架构

```
┌───────────────────────────────────────────────────────────┐
│                    用户 (浏览器)                            │
│            Next.js 14 前端  |  双模式 UI                   │
│       ┌──────────────────┐  ┌──────────────────────────┐  │
│       │   生成模式        │  │   Ableton 编辑模式        │  │
│       │ 自然语言→完整歌曲  │  │ 自然语言→DAW精细编辑      │  │
│       └────────┬─────────┘  └─────────────┬────────────┘  │
└────────────────│────────────────────────────│──────────────┘
                 │ SSE 流式                   │ REST
                 ▼                            ▼
┌────────────────────────┐    ┌───────────────────────────┐
│  Web Server :7860       │    │  Ableton Bridge :8002      │
│  FastAPI + SSE 流式     │    │  FastAPI                   │
└──────────┬─────────────┘    └────────────┬──────────────┘
           │                               │
           ▼                               ├──→ /setup_template
┌──────────────────────────┐               ├──→ /import_stems
│   LangGraph StateGraph    │               ├──→ /chat_edit (LLM路由)
│                           │               ├──→ /llm_edit  (单轨编辑)
│  ┌─────────────────────┐  │               └──→ /apply_sidechain
│  │ understand_intent   │  │                         │
│  └─────────┬───────────┘  │               Ableton RPC Socket :9877
│            │               │               (ableton-mcp Remote Script)
│     ┌──────┴──────┐        │
│     ▼             ▼        │    ┌────────────────────────┐
│  [consult]  [generate/     │    │  RAG 知识库 :8001       │
│             modify/        │    │  音乐制作知识检索        │
│             ableton_edit]  │    │  (向量检索 + LLM 回答)  │
│     │             │        │    └────────────────────────┘
│     ▼             ▼        │
│  rag_retrieve  plan_with_rag◄──── RAG Context
│                    │       │
│                 generate   │    ┌────────────────────────┐
│                    │       │    │  PulseFormer API :8000  │
│                 reflect◄───┼────│  自研音乐生成大模型      │
│                 (LLM评审)  │    │  /generate/song        │
│                    │       │    │  /generate/segment     │
│              ┌─────┴────┐  │    └────────────────────────┘
│              ▼          ▼  │
│         [合格] ableton [重试]
│              │         │   │
│              ▼         └──→ plan_with_rag
│       render_audio         │
│              │             │
│       compose_response     │
└──────────────┬─────────────┘
               ▼
          SSE 流式输出到前端
```

---

## 三、五大核心模块详解

### 模块一：RAG 音乐知识库（创新亮点）

**解决的问题：** 通用 LLM 对专业音乐制作知识（侧链压缩参数、EQ 频段分配、EDM 能量曲线设计、PulseFormer 论文内容）理解不准确，生成结果缺乏专业性。

**架构设计：**

```
用户提问 → RAG API (:8001)
               │
    ┌──────────┴──────────┐
    │  向量检索（top_k=3） │  ← 音乐制作知识文档库
    │  + 可选 Rerank 精排  │    (混音技法/Ableton教程/
    └──────────┬──────────┘     PulseFormer论文/EDM理论)
               │
    LLM 组织回答（引用来源）
               │
         返回 answer + sources
```

**在 Agent 工作流中的两种使用路径：**

| 使用场景 | 触发条件 | 效果 |
|----------|----------|------|
| **咨询路径**（consult） | 用户问"侧链怎么配置"、"什么是四四拍" | RAG 直接回答，引用专业来源 |
| **生成增强**（plan_with_rag） | 每次规划歌曲蓝图前 | 检索同风格参考模板，辅助 LLM 制定更专业的 BPM/结构/能量参数 |

**工具定义（Claude tool_use schema）：**
```python
ask_knowledge(query: str, top_k: int = 3)
# 示例：query="House Drop 的标准能量曲线是什么"
# 返回：answer（LLM综合回答）+ sources（来源片段列表）
```

---

### 模块二：LangGraph 六节点推理工作流（核心创新）

**区别于市面产品的关键：** 传统 AI 音乐工具（Suno/Udio）是单次黑盒生成；TOMI-GPT 是**有状态、可回溯、自我评审**的多步骤推理链路。

#### 完整节点流程

```
understand_intent
       │
       ├─→ [consult]      → rag_retrieve → compose_response → END
       │
       ├─→ [generate]     → rag_retrieve → plan_with_rag → generate
       │                                        ↑               │
       │                                        │ (score<6重试)  ▼
       │                                        └────────── reflect
       │                                                        │ (score≥6)
       │                                                        ▼
       │                                                    ableton(可选)
       │                                                        │
       │                                                   render_audio
       │                                                        │
       │                                                  compose_response → END
       │
       ├─→ [modify]       → plan_with_rag → generate(单轨) → reflect → ...
       │
       └─→ [ableton_edit] → ableton_bridge(/chat_edit) → compose_response → END
```

#### 每个节点的职责

| 节点 | 技术实现 | 输入→输出 |
|------|----------|-----------|
| `understand_intent` | LLM JSON mode 分类 + 槽位填充 | 用户消息 → intent + slots（BPM/key/style/target_track） |
| `rag_retrieve` | RAG API top_k=3 检索 | 风格描述 → 专业参考 context |
| `plan_with_rag` | LLM + RAG context + 用户偏好记忆 | context → 歌曲蓝图 JSON（多段结构/e_level/温度） |
| `generate` | PulseFormer API 调用 | 蓝图 → MIDI 文件（全曲或单轨重生成） |
| `reflect` | **LLM-as-judge** 自动评审 | MIDI 元数据 → score(1-10) + issues + suggestions |
| `ableton` | Ableton Bridge RPC | MIDI → 实时写入 DAW Arrange View |
| `render_audio` | pretty_midi.fluidsynth() | MIDI → WAV/MP3 |
| `compose_response` | LLM 自然语言组织 | 所有上下文 → 用户友好的中文回复 |

**LLM-as-judge 自动评审机制（reflect 节点）：**
- 评估维度：参数匹配度 / 内容完整性 / 段落能量合理性
- score ≥ 6 → 通过，进入 Ableton 导入和音频渲染
- score < 6 → 将 issues + suggestions 反馈给 `plan_with_rag` 节点重试
- 最多重试 2 次，防止死循环

**SSE 流式输出：** 每个节点执行时实时推送事件到前端，用户可看到 Agent 的完整推理过程（而非等待黑盒结果）。

---

### 模块三：十工具 Agent 工具集

Agent 设计了 **10 个原子工具**，覆盖音乐创作全链路：

```
音乐创作链路：
plan_song → generate_music → render_audio

DAW 集成链路：
setup_ableton_template → import_stems_to_ableton → apply_sidechain

编辑修改：
regenerate_track（单轨重生成）
llm_edit_ableton（自然语言→精细MIDI编辑）

知识与记忆：
ask_knowledge（RAG查询）
recall_memory / update_memory（用户偏好管理）
```

**工具设计亮点：**

```python
# 单轨重生成工具：锁定其他轨道，只重做指定轨道
regenerate_track(
    midi_file_id,      # 当前MIDI（包含已有4轨）
    target_track,      # 只重生成这一轨
    bpm, key, struct, e_level, bars
)
# 实现"鼓不变，换个bass"的精细控制

# RAG知识工具：让Agent能回答专业问题
ask_knowledge(
    query="House Drop侧链压缩怎么配置",
    top_k=3
)
# 返回：answer（专业回答）+ sources（来源文档）
```

---

### 模块四：Ableton MCP 深度集成（业界首创）

**解决的核心问题：** AI 生成的 MIDI 与专业 DAW 之间存在不可逾越的"最后一公里"——用户必须手动导入、手动分轨、手动对齐。

**技术方案：** 通过 `ableton-mcp` Remote Script 在 Ableton Live 内注册 Socket RPC 服务（端口 9877），建立 Python Bridge 实时调用。

#### 四大 MCP 能力

**① 一键创建 EDM 模板**
```python
setup_ableton_template(bpm=128, key="C_MINOR")
# → 自动创建 4 轨（DRUMS/BASS/CHORD/MELODY）
# → 加载对应音色（Drum Rack/Bass Synth/Pad/Lead）
# → 设置 BPM + 调性
```

**② 多轨自动路由导入**
```python
import_stems_to_ableton(midi_file_id, view_mode="arrange")
# → PulseFormer 生成的多轨 MIDI 自动匹配到对应 Ableton 轨道
# → 音符时间精确转换（seconds → beats，修正 BPM 2x 误差）
# → 注入后保存 track_state 供后续 LLM 编辑
```

**③ 自然语言精细编辑（12 种原子操作）**

设计了完整的 **Operation Vocabulary**，将用户语言映射为结构化操作：

```
transpose        — 整体移调
octave_shift     — 八度上下移
velocity_scale   — 力度缩放（渐强/渐弱）
set_velocity     — 统一力度
quantize         — 量化对齐
humanize         — 添加人性化随机偏移
time_stretch     — 时间拉伸（加速/减速）
thin             — 稀疏化（删除部分音符）
delete_range     — 删除指定小节范围
reverse          — 音符时间镜像反转
fill_drums_pattern — 空白段鼓组填充
add_notes        — 插入自定义音符
```

多轨并行操作示例：
```python
# 用户："让旋律更稀疏，鼓加点人性化，bass降八度"
edits = [
    {"track": "TOMI-MELODY", "ops": [{"op": "thin", "keep_every": 2}]},
    {"track": "TOMI-DRUMS",  "ops": [{"op": "humanize", "timing": 0.04, "velocity": 8}]},
    {"track": "TOMI-BASS",   "ops": [{"op": "octave_shift", "octave": -1}]},
]
```

**④ 侧链压缩自动配置**
```python
apply_sidechain(source_track="01_DRUMS", target_track="02_BASS")
# → 在 BASS 轨加 Compressor 设备
# → 自动将侧链信号源设为 KICK 轨
# → EDM 经典"律动感"一键实现
```

---

### 模块五：用户偏好记忆系统

**Session 级别持久化**，跨对话积累用户音乐偏好：

```python
# 每次生成后自动更新
update_memory("preferred_bpm", 128)
update_memory("preferred_key", "A_MINOR")
update_memory("preferred_style", "Tech House")

# 下次规划时自动注入
recall_memory() → "BPM偏好：128；调性偏好：A小调；风格：Tech House"
```

规划节点（`plan_with_rag`）将记忆 + RAG context + 用户当前输入三路融合，生成更个性化的歌曲蓝图。

---

## 四、技术选型全景

| 层次 | 技术 | 选型理由 |
|------|------|----------|
| **音乐生成模型** | PulseFormer（自研） | CP Token 多轨表示 + FiLM 能量条件化；支持 e_level(1-8) 精细控制 DROP/INTRO 能量差异 |
| **Agent 框架** | LangGraph StateGraph | 有状态图结构，支持条件路由 + 回溯重试，远优于线性 Chain |
| **本地 LLM** | Ollama + qwen2.5:7b | 结构化 JSON 指令路由本地执行，降低 API 成本；复杂规划走 Claude API |
| **RAG 后端** | 自建 RAG Service | 音乐制作专业知识库，向量检索 + LLM 组织答案 |
| **DAW 集成** | ableton-mcp Socket RPC | 社区 Remote Script，实时 TCP 长连接写入 MIDI Note 数据 |
| **后端框架** | FastAPI + uvicorn | SSE 流式推送，LangGraph 通过 Thread+Queue 与 HTTP 层解耦 |
| **前端** | Next.js 14 + TypeScript | 双模式 UI，Ableton track 状态面板，SSE 逐字流式渲染 |
| **音频渲染** | pretty_midi.fluidsynth() | 纯 Python 路径，无需系统 FluidSynth CLI，跨平台零配置 |
| **状态持久化** | JSON 文件（bridge_state.json） | Bridge 重启自动恢复 track state，无感热重启 |

---

## 五、Bad Case 处理：工程复杂度的核心体现

### Bad Case 1：7B 本地模型不遵循操作词表

**问题：** 要求 qwen2.5:7b 将中文指令"39-49小节空白，帮我加鼓"输出为结构化 JSON，模型完全无视 system prompt，自行发明格式：
```json
{"bar_39": [{"time": "b39.00", "note": "Kick", "velocity": 127}]}
```
导致 `apply_ops()` 无法解析，返回 no_edits。

**解决方案：** 引入**规则优先引擎**，LLM 调用前先跑正则检测，命中则直接构造操作跳过 LLM：
```python
_EMPTY_DRUM_PATTERNS = [
    r"(\d+)\s*[-–～至到]\s*(\d+)\s*小节.*?(?:空白|没有|加入|填充|加鼓)",
    r"bars?\s+(\d+)\s*[-–to]+\s*(\d+).*?(?:empty|blank|add drum)",
]
# 命中 → 直接返回 fill_drums_pattern 操作，绕过 LLM
# 未命中 → 走 LLM 路由
```
**结果：** 命中率 100%，延迟从 5-8s（LLM）降至 <1ms。体现"不要用大炮打蚊子"的工程判断。

---

### Bad Case 2：BPM 识别 2 倍误差

**问题：** `pretty_midi.estimate_tempo()` 对 EDM 鼓组始终估算出 2 倍 BPM（128BPM → 256BPM），导致注入 Ableton 的所有音符时间错位，整段音乐变成两倍速。

**根因分析：** EDM 标准四四拍 Kick 每拍一个的模式，让统计算法误判为 16 分音符密度，输出双倍结果。

**解决：** 弃用估算，直接读 MIDI 文件头的 tempo 事件：
```python
bpm = pm.get_tempo_changes()[1][0]  # 精确，非估算
```

---

### Bad Case 3：Ableton Remote Script 能力边界发现

**问题：** 项目开发时调用 `get_tempo` RPC 命令，但用户实际运行的是 ableton-mcp 社区版 Remote Script，仅支持 `get_session_info` 等有限命令集，导致连接健康检查始终 False，所有 Ableton 功能失效。

**解决过程：** 逐一测试 RPC 命令，绘制实际可用命令边界；建立**能力降级机制**——不支持的命令用 try/except 包裹执行，失败时 best-effort 跳过而不是崩溃：
```python
try:
    _rpc("load_instrument_or_effect", {...})
except Exception:
    pass  # 音色加载失败不影响 MIDI 注入
```

---

### Bad Case 4：Python .format() 与 JSON 模板花括号冲突

**问题：** LangGraph 节点的 prompt 模板内嵌 JSON schema 示例（含大量 `{}`），Python `.format()` 将其识别为占位符，运行时报：
```
KeyError: '\n  "score"'
```
三个核心节点（intent/plan/reflect）全部受影响，工作流在 reflect 节点崩溃。

**解决：** 将所有非占位符花括号统一改为 `{{}}` 双花括号转义，并补充 prompt 渲染单元测试。

---

### Bad Case 5：进程重启导致 Track State 丢失

**问题：** Ableton Bridge 服务重启（代码更新、崩溃恢复）后，内存中的 `_track_state`（包含 1306 条 DRUMS 音符）全部清零，用户需要重新执行 `/import_stems` 才能恢复编辑能力。

**解决：** 设计**三层持久化恢复机制**：
1. 每次 import/edit 操作后自动写 `data/bridge_state.json`
2. 服务启动时自动调用 `_load_state()` 恢复
3. 提供 `seed_bridge_state.py` 工具从 MIDI 文件直接重建状态（用于历史数据恢复）

```python
# 启动时自动执行
def _load_state():
    if _STATE_FILE.exists():
        _track_state.update(json.loads(_STATE_FILE.read_text()))

_load_state()  # module 加载即恢复
```

---

### Bad Case 6：fill_drums_pattern 音符超出 Clip 边界被截断

**问题：** 初始导入的 clip 仅 32 beats（8小节），用户要求填充 bars 39-49，对应 beats 152-196，超出 clip 边界的所有音符被 Ableton 静默丢弃，但 API 不报错。

**解决：** 注入前自动计算所需长度，先扩容 clip 再注入：
```python
required_len = max(n["start_time"] + n["duration"] for n in notes_after)
if required_len > info.get("clip_length", 32.0):
    _rpc("set_clip_length", {
        "track_index": info["track_index"],
        "length": required_len,
    })
```

---

### Bad Case 7：音频渲染 FileNotFoundError（FluidSynth CLI 缺失）

**问题：** 代码最初调用系统 `fluidsynth` CLI 命令渲染 MIDI → WAV，但 Windows 用户环境变量中没有配置 FluidSynth，抛出：
```
FileNotFoundError: [WinError 2] fluidsynth: 找不到指定文件
```

**解决：** 完全重写渲染模块，改用 `pretty_midi` Python binding + scipy，消除系统依赖：
```python
pm = pretty_midi.PrettyMIDI(midi_path)
audio_data = pm.fluidsynth(fs=44100)          # Python binding，无需CLI
audio_int16 = np.int16(audio / np.max(...) * 32767)
wavfile.write(wav_path, 44100, audio_int16)
```

---

## 六、产品量化指标

| 指标 | 数值 |
|------|------|
| 端到端生成延迟 | 15-45s（含 PulseFormer 推理 + 音频渲染） |
| `/chat_edit` 规则路径响应 | < 1ms |
| `/chat_edit` LLM 路径响应 | 5-10s |
| Agent 工具总数 | 10 个（覆盖生成/编辑/知识/记忆/DAW全链路） |
| LangGraph 节点数 | 8 个（含条件分支和回溯重试） |
| 支持 MIDI 操作类型 | 12 种原子操作 |
| 支持音乐风格 | House / Techno / Trance / Dubstep / Ambient |
| 多轨并行处理 | 4 轨同时编辑（DRUMS/BASS/CHORD/MELODY） |
| LLM-as-judge 阈值 | score ≥ 6/10 通过，最多重试 2 次 |
| 状态恢复时间 | < 100ms（JSON 磁盘加载） |

---

## 七、一句话电梯简介（适合简历头部）

> 独立设计并全栈实现 **TOMI-GPT**——一个集 RAG 音乐知识库、LangGraph 六节点推理工作流、自研 PulseFormer 音乐生成大模型、十工具 Agent 工具集、Ableton MCP 实时 DAW 集成于一体的全链路 AI 音乐创作智能体。用中文自然语言即可完成从专业规划、多轨 MIDI 生成、LLM-as-judge 质量评审、到 Ableton Arrange View 实时写入与精细编辑的完整制作流程，首次将 AI 生成模型与专业 DAW 通过 Agent 工作流深度打通，落地生产可用的端到端音乐 AI 助手。

---

## 八、适配产品经理 JD 的技术关键词索引

| JD 常见要求 | 本项目对应 |
|-------------|-----------|
| **大模型应用落地经验** | LangGraph Agent + Ollama 本地推理 + Claude API 混合架构 |
| **RAG 系统设计** | 音乐知识库向量检索，双路径（咨询直答 / 生成增强） |
| **Agent / 工具调用** | 10 工具 Claude tool_use schema + LangGraph 有状态图 |
| **MCP（Model Context Protocol）** | Ableton MCP Socket RPC 集成，实时 DAW 控制 |
| **产品工程化落地** | Bad Case 7 个，规则引擎 + 能力降级 + 状态持久化 |
| **多模态 / 跨模态** | 文本指令 → MIDI → 音频的跨模态生成管道 |
| **流式交互体验** | SSE 实时流，每个 Agent 节点独立推送进度 |
| **自研 AI 模型** | PulseFormer 论文作者，FiLM 能量条件化多轨生成 |
