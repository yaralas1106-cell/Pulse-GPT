"use client";

import { useRef, useState, useCallback, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import { MessageBubble } from "@/components/MessageBubble";
import { chatStream, abletonEdit, abletonState } from "@/lib/api";
import type { Message, ToolStep } from "@/lib/types";

type Mode = "generate" | "ableton";

const GEN_SUGGESTIONS = [
  "生成一首 128BPM 的 House 音乐，带强劲的底鼓和合成弦",
  "用能量渐进的方式生成一首 Techno，开头轻柔结尾爆炸",
  "侧链压缩怎么用？",
  "把刚才生成的贝斯轨重新生成，更暗一些",
];

const ABLETON_SUGGESTIONS = [
  "让旋律更稀疏，去掉大概一半的音符",
  "鼓加点人性化的随机感，不要太机械",
  "整体音量调小，bass 下移一个八度",
  "melody 反转，鼓的力度统一设成 90",
  "把所有轨道量化到 16 分音符网格上",
  "给 melody 加两个半音，chord 的力度调柔和",
];

export default function Home() {
  const [messages, setMessages]   = useState<Message[]>([]);
  const [input, setInput]         = useState("");
  const [busy, setBusy]           = useState(false);
  const [sessionId, setSessionId] = useState("");
  const [mode, setMode]           = useState<Mode>("generate");
  const [abletonTracks, setAbletonTracks] = useState<Record<string, { notes: number; track_index: number }> | null>(null);

  const bottomRef   = useRef<HTMLDivElement>(null);
  const abortRef    = useRef<AbortController | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  // Poll Ableton state when switching to ableton mode
  useEffect(() => {
    if (mode === "ableton") {
      abletonState()
        .then((s) => setAbletonTracks(s.tracks ?? null))
        .catch(() => setAbletonTracks(null));
    }
  }, [mode]);

  const addMessage = (msg: Message) =>
    setMessages((prev) => [...prev, msg]);

  const updateLast = (updater: (m: Message) => Message) =>
    setMessages((prev) =>
      prev.map((m, i) => (i === prev.length - 1 ? updater(m) : m))
    );

  // ── Generate mode send ────────────────────────────────────────────────────
  const sendGenerate = useCallback(
    async (text: string) => {
      if (!text.trim() || busy) return;
      setInput(""); setBusy(true);

      const userMsg: Message = { id: crypto.randomUUID(), role: "user", text };
      const assistantMsg: Message = { id: crypto.randomUUID(), role: "assistant", text: "", steps: [], streaming: true };
      setMessages((prev) => [...prev, userMsg, assistantMsg]);

      const ctrl = new AbortController();
      abortRef.current = ctrl;

      const updateAssistant = (updater: (m: Message) => Message) =>
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantMsg.id ? updater(m) : m))
        );

      try {
        await chatStream(text, sessionId, (evt) => {
          if (evt.type === "session") {
            setSessionId(evt.session_id);
          } else if (evt.type === "tool_call") {
            updateAssistant((m) => ({
              ...m,
              steps: [...(m.steps ?? []), { name: evt.name, status: "running", input: evt.input } as ToolStep],
            }));
          } else if (evt.type === "tool_result") {
            updateAssistant((m) => ({
              ...m,
              steps: (m.steps ?? []).map((s) =>
                s.name === evt.name && s.status === "running"
                  ? { ...s, status: "done", result: evt.result }
                  : s
              ) as ToolStep[],
            }));
          } else if (evt.type === "done") {
            updateAssistant((m) => ({
              ...m,
              text:      evt.text,
              audioUrl:  evt.audio_url ?? undefined,
              midiUrl:   evt.midi_url  ?? undefined,
              streaming: false,
            }));
            // Refresh ableton state after generation
            abletonState().then((s) => setAbletonTracks(s.tracks ?? null)).catch(() => {});
          } else if (evt.type === "error") {
            updateAssistant((m) => ({ ...m, text: `错误: ${evt.message}`, streaming: false }));
          }
        }, ctrl.signal);
      } catch (e: unknown) {
        const isAbort = e instanceof Error && e.name === "AbortError";
        if (!isAbort) {
          updateAssistant((m) => ({
            ...m,
            text: "连接失败，请确认后端服务已启动 (localhost:7860)",
            streaming: false,
          }));
        }
      } finally {
        setBusy(false);
        abortRef.current = null;
      }
    },
    [busy, sessionId],
  );

  // ── Ableton edit mode send ────────────────────────────────────────────────
  const sendAbletonEdit = useCallback(
    async (text: string) => {
      if (!text.trim() || busy) return;
      setInput(""); setBusy(true);

      const userMsg: Message = { id: crypto.randomUUID(), role: "user", text };
      const assistantMsg: Message = { id: crypto.randomUUID(), role: "assistant", text: "正在分析指令并修改 Ableton…", steps: [], streaming: true };
      setMessages((prev) => [...prev, userMsg, assistantMsg]);

      try {
        const result = await abletonEdit(text);

        let replyText = "";
        if (result.status === "no_edits") {
          replyText = "LLM 判断这条指令不需要修改任何轨道。";
        } else {
          const lines: string[] = [];
          for (const r of result.results ?? []) {
            if (r.status === "ok") {
              const ops = (r.ops_applied ?? []).map((o) => o.op).join(", ");
              lines.push(`✓ **${r.track}**  [${ops}]  ${r.notes_before} → ${r.notes_after} 音符`);
            } else {
              lines.push(`✗ ${r.track}: ${r.status}`);
            }
          }
          replyText = lines.join("\n");
        }

        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsg.id
              ? { ...m, text: replyText, streaming: false }
              : m
          )
        );

        // Refresh state
        abletonState().then((s) => setAbletonTracks(s.tracks ?? null)).catch(() => {});
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsg.id
              ? { ...m, text: `错误: ${msg}`, streaming: false }
              : m
          )
        );
      } finally {
        setBusy(false);
      }
    },
    [busy],
  );

  const send = mode === "ableton" ? sendAbletonEdit : sendGenerate;

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); }
  };

  const handleReset = () => {
    if (sessionId) fetch(`${process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:7860"}/session/${sessionId}`, { method: "DELETE" });
    setMessages([]); setSessionId("");
  };

  const suggestions = mode === "ableton" ? ABLETON_SUGGESTIONS : GEN_SUGGESTIONS;

  return (
    <div className="flex flex-col h-screen" style={{ background: "var(--bg)" }}>

      {/* ── Header ── */}
      <header className="shrink-0 flex items-center justify-between px-6 py-3 z-10"
        style={{ borderBottom: "1px solid var(--border)", background: "var(--surface)" }}>
        <div className="flex items-center gap-2.5">
          <span className="text-xl">🎵</span>
          <span className="font-bold tracking-tight text-lg" style={{ color: "var(--text)" }}>
            TOMI Music Agent
          </span>
          <span className="text-xs px-2 py-0.5 rounded-full"
            style={{ background: "#7c6af722", color: "var(--accent)" }}>
            PulseFormer
          </span>
        </div>

        <div className="flex items-center gap-3">
          {/* Mode toggle */}
          <div className="flex rounded-lg overflow-hidden text-xs"
            style={{ border: "1px solid var(--border)" }}>
            <button
              onClick={() => setMode("generate")}
              className="px-3 py-1.5 transition-colors"
              style={{
                background: mode === "generate" ? "linear-gradient(135deg,#7c6af7,#e066c8)" : "transparent",
                color: mode === "generate" ? "white" : "var(--muted)",
              }}
            >
              生成模式
            </button>
            <button
              onClick={() => setMode("ableton")}
              className="px-3 py-1.5 transition-colors"
              style={{
                background: mode === "ableton" ? "#22c55e" : "transparent",
                color: mode === "ableton" ? "white" : "var(--muted)",
              }}
            >
              Ableton 编辑
            </button>
          </div>

          <Link href="/showcase"
            className="text-xs px-3 py-1.5 rounded-lg hover:opacity-80 transition-opacity"
            style={{ background: "#7c6af722", color: "#a78bfa", border: "1px solid #7c6af733" }}>
            项目介绍
          </Link>

          {sessionId && (
            <span className="text-xs" style={{ color: "var(--muted)" }}>
              session: {sessionId}
            </span>
          )}
          <button onClick={handleReset}
            className="text-xs px-3 py-1.5 rounded-lg hover:opacity-80 transition-opacity"
            style={{ background: "#ffffff11", color: "var(--muted)" }}>
            新对话
          </button>
        </div>
      </header>

      {/* ── Ableton track status bar ── */}
      <AnimatePresence>
        {mode === "ableton" && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="shrink-0 overflow-hidden"
            style={{ background: "#0d1a0d", borderBottom: "1px solid #22c55e33" }}
          >
            <div className="px-6 py-2 flex items-center gap-4 text-xs">
              <span style={{ color: "#22c55e" }}>Ableton 轨道</span>
              {abletonTracks
                ? Object.entries(abletonTracks).map(([name, info]) => (
                    <span key={name} className="px-2 py-0.5 rounded"
                      style={{ background: "#22c55e22", color: "#86efac" }}>
                      {name.replace("TOMI-", "")} · {info.notes}音符
                    </span>
                  ))
                : <span style={{ color: "#6b7280" }}>未检测到轨道，请先生成音乐或调用 /import_stems</span>
              }
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Messages ── */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-3xl mx-auto space-y-6">
          <AnimatePresence initial={false}>
            {messages.length === 0 && (
              <motion.div key="welcome"
                initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                className="flex flex-col items-center justify-center py-20 gap-8">
                <div className="text-center">
                  <div className="text-6xl mb-4">{mode === "ableton" ? "🎛️" : "🎹"}</div>
                  <h2 className="text-2xl font-bold mb-2" style={{ color: "var(--text)" }}>
                    {mode === "ableton" ? "Ableton 编辑模式" : "你好，我是 TOMI"}
                  </h2>
                  <p className="text-sm" style={{ color: "var(--muted)" }}>
                    {mode === "ableton"
                      ? "用自然语言修改 Ableton 中的 MIDI 轨道"
                      : "AI 音乐创作助手 · 由 PulseFormer 驱动"}
                  </p>
                </div>

                <div className="grid grid-cols-2 gap-2 max-w-lg w-full">
                  {suggestions.map((s) => (
                    <button key={s} onClick={() => send(s)}
                      className="text-left text-xs px-3 py-2.5 rounded-xl hover:opacity-80 transition-opacity leading-relaxed"
                      style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)" }}>
                      {s}
                    </button>
                  ))}
                </div>
              </motion.div>
            )}

            {messages.map((msg) => (
              <MessageBubble key={msg.id} msg={msg} />
            ))}
          </AnimatePresence>
          <div ref={bottomRef} />
        </div>
      </div>

      {/* ── Input ── */}
      <div className="shrink-0 px-4 py-4"
        style={{ borderTop: "1px solid var(--border)", background: "var(--surface)" }}>
        <div className="max-w-3xl mx-auto flex gap-2 items-end">
          <div className="flex-1 flex items-end rounded-2xl px-4 py-2.5 gap-2"
            style={{ background: "var(--bg)", border: `1px solid ${mode === "ableton" ? "#22c55e55" : "var(--border)"}` }}>
            <textarea ref={textareaRef} value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKey}
              placeholder={mode === "ableton"
                ? "输入 Ableton 编辑指令，例如：让旋律更稀疏，bass 下移八度…"
                : "描述你想要的音乐，或问一个问题…"}
              rows={1}
              className="flex-1 bg-transparent text-sm resize-none outline-none leading-relaxed"
              style={{ color: "var(--text)", maxHeight: "120px", overflowY: "auto" }}
              onInput={(e) => {
                const t = e.currentTarget;
                t.style.height = "auto";
                t.style.height = `${t.scrollHeight}px`;
              }}
            />
          </div>

          {busy ? (
            <button onClick={() => abortRef.current?.abort()}
              className="w-10 h-10 rounded-xl flex items-center justify-center text-sm hover:opacity-80 transition-opacity"
              style={{ background: "#ef444433", color: "#ef4444" }}>
              ⏹
            </button>
          ) : (
            <button onClick={() => send(input)} disabled={!input.trim()}
              className="w-10 h-10 rounded-xl flex items-center justify-center text-sm transition-opacity disabled:opacity-30 hover:opacity-80"
              style={{
                background: mode === "ableton"
                  ? "linear-gradient(135deg,#16a34a,#22c55e)"
                  : "linear-gradient(135deg,#7c6af7,#e066c8)",
                color: "white",
              }}>
              ↑
            </button>
          )}
        </div>
        <p className="text-center text-xs mt-2" style={{ color: "var(--muted)" }}>
          {mode === "ableton"
            ? "Enter 发送 · LLM 自动决定修改哪些轨道"
            : "Enter 发送 · Shift+Enter 换行 · 生成约需 10–30 秒"}
        </p>
      </div>
    </div>
  );
}
