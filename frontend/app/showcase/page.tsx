"use client";

import { useEffect, useRef, useState } from "react";
import { motion, useInView, AnimatePresence } from "framer-motion";
import Link from "next/link";

// ── helpers ────────────────────────────────────────────────────────────────────
const fadeUp = (delay = 0) => ({
  initial: { opacity: 0, y: 32 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true },
  transition: { duration: 0.6, delay, ease: [0.22, 1, 0.36, 1] },
});

// ── Pipeline node data ─────────────────────────────────────────────────────────
const NODES = [
  {
    id: "intent",
    label: "Intent",
    sub: "意图分类",
    desc: "LLM 解析用户输入，识别 generate / modify / consult / ableton_edit 四种意图，提取 BPM、调性、风格等槽位",
    color: "#7c6af7",
    icon: "🧠",
  },
  {
    id: "rag",
    label: "RAG",
    sub: "知识检索",
    desc: "向量检索音乐制作知识库（混音/EQ/侧链/理论），为规划节点提供专业上下文",
    color: "#06b6d4",
    icon: "📚",
  },
  {
    id: "plan",
    label: "Plan",
    sub: "RAG 增强规划",
    desc: "LLM + RAG context + 用户记忆三路融合，生成多段式歌曲蓝图（BPM / 调性 / e_level / 段落结构）",
    color: "#f59e0b",
    icon: "📐",
  },
  {
    id: "generate",
    label: "Generate",
    sub: "PulseFormer 生成",
    desc: "调用自研音乐大模型，基于 CP Token + FiLM 能量条件化生成四轨 MIDI（DRUMS / BASS / CHORD / MELODY）",
    color: "#e066c8",
    icon: "🎹",
  },
  {
    id: "reflect",
    label: "Reflect",
    sub: "LLM-as-Judge",
    desc: "自动评审生成质量（参数匹配 / 内容完整 / 能量合理），score < 6 则将 issues 反馈给 Plan 节点重试",
    color: "#ef4444",
    icon: "⚖️",
  },
  {
    id: "ableton",
    label: "Ableton",
    sub: "MCP 写入",
    desc: "通过 Socket RPC 将多轨 MIDI 实时注入 Ableton Arrange View，保留音轨索引 / clip 位置 / BPM 元数据",
    color: "#22c55e",
    icon: "🎛️",
  },
];

const FEATURES = [
  {
    icon: "📚",
    title: "RAG 音乐知识库",
    color: "#06b6d4",
    points: [
      "向量检索音乐制作知识（混音/侧链/EQ/EDM理论）",
      "双路径：咨询直答 + 生成规划增强",
      "LLM 组织回答并标注来源",
    ],
  },
  {
    icon: "🎛️",
    title: "Ableton MCP 集成",
    color: "#22c55e",
    points: [
      "Socket RPC 实时写入 DAW Arrange View",
      "一键创建 EDM 4轨模板 + 音色",
      "自动配置侧链压缩（Kick → Bass）",
    ],
  },
  {
    icon: "⚙️",
    title: "12 种原子操作",
    color: "#7c6af7",
    points: [
      "transpose / humanize / quantize / reverse",
      "fill_drums_pattern 鼓组空段填充",
      "多轨并行操作，LLM 自动路由",
    ],
  },
  {
    icon: "🧠",
    title: "用户偏好记忆",
    color: "#f59e0b",
    points: [
      "Session 级持久化：BPM / 调性 / 风格偏好",
      "规划时自动融合历史偏好",
      "跨对话记忆保留",
    ],
  },
  {
    icon: "⚖️",
    title: "LLM-as-Judge 评审",
    color: "#ef4444",
    points: [
      "三维度打分：匹配度 / 完整性 / 能量合理性",
      "score < 6 自动重规划，最多重试 2 次",
      "反馈 issues 定向修正下一轮",
    ],
  },
  {
    icon: "🔌",
    title: "10 工具 Agent",
    color: "#e066c8",
    points: [
      "plan_song / generate_music / render_audio",
      "regenerate_track 单轨锁定重生成",
      "ask_knowledge / recall_memory / update_memory",
    ],
  },
];

const BADCASES = [
  {
    tag: "LLM 不遵循指令",
    problem: "7B 本地模型忽略 system prompt，对"39-49小节空白加鼓"自行发明格式",
    solution: "引入规则优先引擎，正则命中直接构造操作绕过 LLM，延迟从 5-8s → <1ms",
    color: "#ef4444",
  },
  {
    tag: "BPM 2× 误差",
    problem: "estimate_tempo() 对 EDM 四四拍 Kick 估算结果始终是真实 BPM 的 2 倍",
    solution: "改用 get_tempo_changes()[1][0] 直接读 MIDI 文件头 tempo 事件",
    color: "#f59e0b",
  },
  {
    tag: "Ableton API 边界",
    problem: "代码调用 get_tempo，但社区版 Remote Script 仅支持有限命令集",
    solution: "逐一测试可用命令，建立能力降级机制，不支持的命令 best-effort 跳过",
    color: "#06b6d4",
  },
  {
    tag: "Prompt 花括号冲突",
    problem: "LangGraph prompt 内嵌 JSON schema，Python .format() 将 {} 解析为占位符",
    solution: "统一改为 {{}} 双花括号转义，三个核心节点全部修复",
    color: "#7c6af7",
  },
  {
    tag: "进程重启丢状态",
    problem: "Bridge 重启后内存 track_state 清零，1306 条 DRUMS 音符信息全部丢失",
    solution: "设计 JSON 磁盘持久化 + 启动自动加载，实现无感热重启",
    color: "#22c55e",
  },
  {
    tag: "Clip 截断远端音符",
    problem: "bars 39-49 对应 beats 152-196，超出 32 beat clip 边界被静默丢弃",
    solution: "注入前计算 required_len，先调 set_clip_length 扩容再注入",
    color: "#e066c8",
  },
];

const METRICS = [
  { value: "10", label: "Agent 工具", sub: "覆盖生成/编辑/知识/记忆/DAW" },
  { value: "8", label: "LangGraph 节点", sub: "含条件路由与自动重试" },
  { value: "12", label: "MIDI 原子操作", sub: "多轨并行精细编辑" },
  { value: "6", label: "Bad Case 解决", sub: "工程复杂度的核心体现" },
  { value: "<1ms", label: "规则路由延迟", sub: "规则引擎绕过 LLM" },
  { value: "4", label: "音乐风格", sub: "House/Techno/Trance/Dubstep" },
];

const STACK = [
  { name: "PulseFormer", desc: "自研音乐生成大模型", color: "#e066c8" },
  { name: "LangGraph", desc: "有状态 Agent 工作流", color: "#7c6af7" },
  { name: "Ollama", desc: "本地 7B LLM 推理", color: "#f59e0b" },
  { name: "RAG Service", desc: "音乐知识向量检索", color: "#06b6d4" },
  { name: "Ableton MCP", desc: "DAW Socket RPC 集成", color: "#22c55e" },
  { name: "FastAPI", desc: "SSE 流式 API 后端", color: "#6366f1" },
  { name: "Next.js 14", desc: "双模式交互前端", color: "#e2e8f0" },
  { name: "pretty_midi", desc: "Python MIDI 渲染", color: "#f97316" },
];

// ── Pipeline animated component ───────────────────────────────────────────────
function Pipeline() {
  const [active, setActive] = useState(0);
  const [running, setRunning] = useState(true);

  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => {
      setActive((a) => (a + 1) % NODES.length);
    }, 1800);
    return () => clearInterval(t);
  }, [running]);

  return (
    <div className="w-full">
      {/* Node row */}
      <div className="flex items-start justify-between gap-1 md:gap-2 mb-6 relative">
        {/* connecting line */}
        <div className="absolute top-7 left-0 right-0 h-px" style={{ background: "linear-gradient(90deg, transparent, #7c6af733, #7c6af7, #7c6af733, transparent)" }} />

        {NODES.map((node, i) => {
          const isActive = active === i;
          const isPast   = (active > i) || (active === 0 && i === NODES.length - 1);
          return (
            <button
              key={node.id}
              onClick={() => { setActive(i); setRunning(false); }}
              className="flex flex-col items-center gap-2 z-10 flex-1"
            >
              <motion.div
                animate={{
                  scale: isActive ? 1.15 : 1,
                  boxShadow: isActive ? `0 0 24px ${node.color}88` : "none",
                }}
                transition={{ duration: 0.3 }}
                className="w-14 h-14 rounded-2xl flex items-center justify-center text-2xl relative"
                style={{
                  background: isActive ? node.color : isPast ? `${node.color}44` : "#1e2230",
                  border: `2px solid ${isActive ? node.color : "#2a2f42"}`,
                }}
              >
                {node.icon}
                {isActive && (
                  <motion.div
                    className="absolute inset-0 rounded-2xl"
                    style={{ border: `2px solid ${node.color}` }}
                    animate={{ scale: [1, 1.4], opacity: [0.8, 0] }}
                    transition={{ duration: 1, repeat: Infinity }}
                  />
                )}
              </motion.div>
              <span className="text-xs font-semibold" style={{ color: isActive ? node.color : "#6b7280" }}>
                {node.label}
              </span>
              <span className="text-xs hidden md:block" style={{ color: "#4b5563", fontSize: "0.65rem" }}>
                {node.sub}
              </span>
            </button>
          );
        })}
      </div>

      {/* Detail card */}
      <AnimatePresence mode="wait">
        <motion.div
          key={active}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          transition={{ duration: 0.25 }}
          className="rounded-2xl p-5"
          style={{ background: "#1e2230", border: `1px solid ${NODES[active].color}44` }}
        >
          <div className="flex items-center gap-3 mb-3">
            <span className="text-2xl">{NODES[active].icon}</span>
            <div>
              <div className="font-bold text-sm" style={{ color: NODES[active].color }}>
                {NODES[active].label} 节点
              </div>
              <div className="text-xs" style={{ color: "#6b7280" }}>{NODES[active].sub}</div>
            </div>
            <button
              className="ml-auto text-xs px-2.5 py-1 rounded-lg"
              style={{ background: running ? "#ef444422" : "#22c55e22", color: running ? "#ef4444" : "#22c55e" }}
              onClick={() => setRunning(!running)}
            >
              {running ? "⏸ 暂停" : "▶ 播放"}
            </button>
          </div>
          <p className="text-sm leading-relaxed" style={{ color: "#9ca3af" }}>
            {NODES[active].desc}
          </p>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function ShowcasePage() {
  return (
    <div className="min-h-screen" style={{ background: "var(--bg)", color: "var(--text)" }}>

      {/* ── floating bg orbs ── */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none" style={{ zIndex: 0 }}>
        <div className="absolute -top-40 -left-40 w-96 h-96 rounded-full opacity-20"
          style={{ background: "radial-gradient(circle, #7c6af7, transparent)", filter: "blur(60px)" }} />
        <div className="absolute top-1/2 -right-40 w-80 h-80 rounded-full opacity-15"
          style={{ background: "radial-gradient(circle, #e066c8, transparent)", filter: "blur(60px)" }} />
        <div className="absolute bottom-0 left-1/3 w-72 h-72 rounded-full opacity-10"
          style={{ background: "radial-gradient(circle, #06b6d4, transparent)", filter: "blur(60px)" }} />
      </div>

      <div className="relative" style={{ zIndex: 1 }}>

        {/* ── Hero ───────────────────────────────────────────────────────────── */}
        <section className="max-w-5xl mx-auto px-6 pt-24 pb-20 text-center">
          <motion.div {...fadeUp(0)} className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-xs mb-6"
            style={{ background: "#7c6af722", border: "1px solid #7c6af744", color: "#a78bfa" }}>
            🎵 AI Music Creation Agent &nbsp;·&nbsp; PulseFormer + LangGraph + Ableton MCP
          </motion.div>

          <motion.h1 {...fadeUp(0.1)} className="text-5xl md:text-7xl font-black tracking-tight mb-6 leading-none">
            <span style={{ background: "linear-gradient(135deg,#7c6af7,#e066c8,#06b6d4)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
              TOMI-GPT
            </span>
          </motion.h1>

          <motion.p {...fadeUp(0.2)} className="text-lg md:text-xl max-w-2xl mx-auto mb-4 leading-relaxed" style={{ color: "#9ca3af" }}>
            全链路 AI 音乐创作智能体
          </motion.p>
          <motion.p {...fadeUp(0.25)} className="text-sm max-w-xl mx-auto mb-10 leading-relaxed" style={{ color: "#6b7280" }}>
            自然语言 → RAG 知识检索 → LangGraph 多节点规划 → PulseFormer 生成 → LLM-as-Judge 评审 → Ableton MCP 实时写入
          </motion.p>

          <motion.div {...fadeUp(0.3)} className="flex items-center justify-center gap-4 flex-wrap">
            <Link href="/"
              className="px-6 py-3 rounded-xl font-semibold text-sm transition-opacity hover:opacity-80"
              style={{ background: "linear-gradient(135deg,#7c6af7,#e066c8)", color: "white" }}>
              🎹 打开 Agent 对话
            </Link>
            <a href="https://github.com" target="_blank"
              className="px-6 py-3 rounded-xl font-semibold text-sm transition-opacity hover:opacity-80"
              style={{ background: "#1e2230", border: "1px solid #2a2f42", color: "#e8eaf0" }}>
              GitHub →
            </a>
          </motion.div>
        </section>

        {/* ── Metrics strip ──────────────────────────────────────────────────── */}
        <motion.section {...fadeUp(0)} className="border-y py-10" style={{ borderColor: "#232630" }}>
          <div className="max-w-5xl mx-auto px-6 grid grid-cols-3 md:grid-cols-6 gap-6 text-center">
            {METRICS.map((m, i) => (
              <motion.div key={m.label} {...fadeUp(i * 0.05)}>
                <div className="text-2xl font-black mb-1"
                  style={{ background: "linear-gradient(135deg,#7c6af7,#e066c8)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
                  {m.value}
                </div>
                <div className="text-xs font-semibold mb-0.5" style={{ color: "#e8eaf0" }}>{m.label}</div>
                <div className="text-xs" style={{ color: "#4b5563", fontSize: "0.65rem" }}>{m.sub}</div>
              </motion.div>
            ))}
          </div>
        </motion.section>

        {/* ── Pipeline ───────────────────────────────────────────────────────── */}
        <section className="max-w-5xl mx-auto px-6 py-20">
          <motion.div {...fadeUp(0)} className="text-center mb-12">
            <div className="text-xs font-semibold tracking-widest uppercase mb-3" style={{ color: "#7c6af7" }}>
              LangGraph 工作流
            </div>
            <h2 className="text-3xl font-bold">六节点推理链路</h2>
            <p className="mt-3 text-sm" style={{ color: "#6b7280" }}>
              点击节点查看详情，每个节点独立流式输出 · LLM-as-Judge 自动评审 + 回溯重试
            </p>
          </motion.div>
          <motion.div {...fadeUp(0.1)}>
            <Pipeline />
          </motion.div>
        </section>

        {/* ── Feature cards ──────────────────────────────────────────────────── */}
        <section className="max-w-5xl mx-auto px-6 py-10 pb-20">
          <motion.div {...fadeUp(0)} className="text-center mb-12">
            <div className="text-xs font-semibold tracking-widest uppercase mb-3" style={{ color: "#06b6d4" }}>
              核心模块
            </div>
            <h2 className="text-3xl font-bold">六大技术创新</h2>
          </motion.div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
            {FEATURES.map((f, i) => (
              <motion.div key={f.title} {...fadeUp(i * 0.07)}
                className="rounded-2xl p-5 flex flex-col gap-3 group hover:scale-[1.02] transition-transform duration-300"
                style={{ background: "#161921", border: `1px solid ${f.color}22` }}>
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl flex items-center justify-center text-xl"
                    style={{ background: `${f.color}22` }}>
                    {f.icon}
                  </div>
                  <span className="font-bold text-sm" style={{ color: f.color }}>{f.title}</span>
                </div>
                <ul className="space-y-1.5">
                  {f.points.map((p) => (
                    <li key={p} className="text-xs flex items-start gap-2" style={{ color: "#9ca3af" }}>
                      <span style={{ color: f.color, marginTop: "0.1rem" }}>▸</span>
                      {p}
                    </li>
                  ))}
                </ul>
              </motion.div>
            ))}
          </div>
        </section>

        {/* ── Architecture diagram ───────────────────────────────────────────── */}
        <section className="max-w-5xl mx-auto px-6 py-10 pb-20">
          <motion.div {...fadeUp(0)} className="text-center mb-12">
            <div className="text-xs font-semibold tracking-widest uppercase mb-3" style={{ color: "#e066c8" }}>
              系统架构
            </div>
            <h2 className="text-3xl font-bold">服务拓扑</h2>
          </motion.div>

          <motion.div {...fadeUp(0.1)} className="rounded-2xl p-6 md:p-10 font-mono text-xs leading-relaxed overflow-x-auto"
            style={{ background: "#0d1117", border: "1px solid #232630", color: "#e8eaf0" }}>
            <div style={{ minWidth: "560px" }}>
              {/* User layer */}
              <div className="flex justify-center mb-4">
                <div className="px-6 py-2 rounded-xl text-center" style={{ background: "#7c6af722", border: "1px solid #7c6af755", color: "#a78bfa", minWidth: "280px" }}>
                  🌐 用户浏览器 (Next.js :3000)
                </div>
              </div>

              <div className="flex justify-center mb-1" style={{ color: "#4b5563" }}>│ SSE 流式 / REST</div>

              {/* Web + Bridge layer */}
              <div className="flex gap-4 justify-center mb-4">
                <div className="px-4 py-2 rounded-xl text-center" style={{ background: "#1e293b", border: "1px solid #7c6af755", color: "#a78bfa", flex: 1, maxWidth: "200px" }}>
                  ⚡ Web Server<br /><span style={{ color: "#4b5563" }}>FastAPI :7860</span>
                </div>
                <div className="px-4 py-2 rounded-xl text-center" style={{ background: "#0d1a0d", border: "1px solid #22c55e55", color: "#86efac", flex: 1, maxWidth: "200px" }}>
                  🎛️ Ableton Bridge<br /><span style={{ color: "#4b5563" }}>FastAPI :8002</span>
                </div>
              </div>

              <div className="flex gap-4 justify-center mb-1">
                <div className="flex-1 max-w-[200px] text-center" style={{ color: "#4b5563" }}>│ LangGraph</div>
                <div className="flex-1 max-w-[200px] text-center" style={{ color: "#4b5563" }}>│ Socket RPC</div>
              </div>

              {/* Backend services */}
              <div className="flex gap-3 justify-center mb-4 flex-wrap">
                {[
                  { label: "🤖 LangGraph\nAgent", color: "#7c6af7" },
                  { label: "📚 RAG Service\n:8001", color: "#06b6d4" },
                  { label: "🎹 PulseFormer\n:8000", color: "#e066c8" },
                  { label: "🎵 Ableton Live\nMCP :9877", color: "#22c55e" },
                ].map((s) => (
                  <div key={s.label} className="px-3 py-2 rounded-xl text-center whitespace-pre-line" style={{ background: `${s.color}11`, border: `1px solid ${s.color}44`, color: s.color, fontSize: "0.65rem", minWidth: "110px" }}>
                    {s.label}
                  </div>
                ))}
              </div>

              {/* Ollama */}
              <div className="flex justify-center">
                <div className="px-5 py-1.5 rounded-lg text-center" style={{ background: "#1c1a00", border: "1px solid #f59e0b44", color: "#f59e0b", fontSize: "0.65rem" }}>
                  🦙 Ollama :11434 — qwen2.5:7b 本地推理
                </div>
              </div>
            </div>
          </motion.div>
        </section>

        {/* ── Bad Cases ──────────────────────────────────────────────────────── */}
        <section className="max-w-5xl mx-auto px-6 py-10 pb-20">
          <motion.div {...fadeUp(0)} className="text-center mb-12">
            <div className="text-xs font-semibold tracking-widest uppercase mb-3" style={{ color: "#ef4444" }}>
              工程复杂度
            </div>
            <h2 className="text-3xl font-bold">Bad Case 处理</h2>
            <p className="mt-3 text-sm" style={{ color: "#6b7280" }}>
              每个 Bad Case 都是一次从现象到根因的工程判断，而不是绕过问题
            </p>
          </motion.div>

          <div className="grid md:grid-cols-2 gap-4">
            {BADCASES.map((bc, i) => (
              <motion.div key={bc.tag} {...fadeUp(i * 0.06)}
                className="rounded-2xl p-5"
                style={{ background: "#161921", border: `1px solid ${bc.color}33` }}>
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-xs px-2.5 py-0.5 rounded-full font-semibold"
                    style={{ background: `${bc.color}22`, color: bc.color }}>
                    {bc.tag}
                  </span>
                </div>
                <div className="mb-2">
                  <span className="text-xs font-semibold" style={{ color: "#ef4444" }}>问题：</span>
                  <span className="text-xs" style={{ color: "#9ca3af" }}> {bc.problem}</span>
                </div>
                <div>
                  <span className="text-xs font-semibold" style={{ color: "#22c55e" }}>解决：</span>
                  <span className="text-xs" style={{ color: "#9ca3af" }}> {bc.solution}</span>
                </div>
              </motion.div>
            ))}
          </div>
        </section>

        {/* ── Tech stack ─────────────────────────────────────────────────────── */}
        <section className="max-w-5xl mx-auto px-6 py-10 pb-20">
          <motion.div {...fadeUp(0)} className="text-center mb-10">
            <div className="text-xs font-semibold tracking-widest uppercase mb-3" style={{ color: "#f59e0b" }}>
              技术选型
            </div>
            <h2 className="text-3xl font-bold">Tech Stack</h2>
          </motion.div>

          <div className="flex flex-wrap gap-3 justify-center">
            {STACK.map((s, i) => (
              <motion.div key={s.name} {...fadeUp(i * 0.04)}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm"
                style={{ background: "#161921", border: `1px solid ${s.color}33` }}>
                <span className="w-2 h-2 rounded-full" style={{ background: s.color }} />
                <span className="font-semibold" style={{ color: s.color }}>{s.name}</span>
                <span className="text-xs" style={{ color: "#4b5563" }}>{s.desc}</span>
              </motion.div>
            ))}
          </div>
        </section>

        {/* ── CTA ────────────────────────────────────────────────────────────── */}
        <section className="max-w-5xl mx-auto px-6 py-10 pb-32 text-center">
          <motion.div {...fadeUp(0)} className="rounded-3xl p-12"
            style={{ background: "linear-gradient(135deg, #7c6af711, #e066c811)", border: "1px solid #7c6af733" }}>
            <div className="text-4xl mb-4">🎵</div>
            <h2 className="text-2xl font-bold mb-3">立即体验 TOMI-GPT</h2>
            <p className="text-sm mb-8" style={{ color: "#6b7280" }}>
              用自然语言描述你的音乐想法，AI 自动完成作曲、编排和 DAW 写入
            </p>
            <Link href="/"
              className="inline-flex px-8 py-3.5 rounded-xl font-bold text-sm transition-opacity hover:opacity-80"
              style={{ background: "linear-gradient(135deg,#7c6af7,#e066c8)", color: "white" }}>
              🎹 打开 Agent 对话 →
            </Link>
          </motion.div>
        </section>

        {/* ── Footer ─────────────────────────────────────────────────────────── */}
        <footer className="border-t py-6 text-center text-xs" style={{ borderColor: "#232630", color: "#374151" }}>
          TOMI-GPT · Built with PulseFormer + LangGraph + Ableton MCP
        </footer>
      </div>
    </div>
  );
}
