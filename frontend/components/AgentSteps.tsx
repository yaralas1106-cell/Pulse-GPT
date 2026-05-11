"use client";

import { motion, AnimatePresence } from "framer-motion";
import type { ToolStep } from "@/lib/types";

const TOOL_LABELS: Record<string, string> = {
  // LangGraph nodes
  understand_intent:        "意图理解",
  rag_retrieve:             "RAG 检索",
  consult:                  "知识库问答",
  plan_with_rag:            "参数规划",
  generate:                 "PulseFormer 生成",
  reflect:                  "质量反思",
  render_audio:             "渲染音频",
  ableton:                  "Ableton 集成",
  compose_response:         "组织回复",
  // legacy tool names (agent.py fallback)
  recall_memory:            "记忆调取",
  plan_song:                "规划歌曲",
  generate_music:           "PulseFormer 生成",
  regenerate_track:         "重生成轨道",
  ask_knowledge:            "查询知识库",
  setup_ableton_template:   "创建 Ableton 模板",
  import_stems_to_ableton:  "导入 Ableton",
  apply_sidechain:          "配置侧链",
  save_memory:              "保存记忆",
};

const TOOL_ICONS: Record<string, string> = {
  // LangGraph nodes
  understand_intent:        "🧭",
  rag_retrieve:             "📚",
  consult:                  "💬",
  plan_with_rag:            "📐",
  generate:                 "🎹",
  reflect:                  "🔍",
  render_audio:             "🎧",
  ableton:                  "🎛️",
  compose_response:         "✍️",
  // legacy
  recall_memory:            "🧠",
  plan_song:                "📐",
  generate_music:           "🎹",
  regenerate_track:         "🔄",
  ask_knowledge:            "📚",
  setup_ableton_template:   "🎛️",
  import_stems_to_ableton:  "🎚️",
  apply_sidechain:          "🔗",
  save_memory:              "💾",
};

export function AgentSteps({ steps }: { steps: ToolStep[] }) {
  if (!steps.length) return null;

  return (
    <div className="mt-3 space-y-1.5">
      <AnimatePresence initial={false}>
        {steps.map((step, i) => (
          <motion.div
            key={`${step.name}-${i}`}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.2 }}
            className="flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg"
            style={{
              background: "var(--surface)",
              border: `1px solid ${step.status === "error" ? "#ef4444" : step.status === "done" ? "#22c55e22" : "#7c6af722"}`,
            }}
          >
            {/* icon */}
            <span className="text-base leading-none">
              {TOOL_ICONS[step.name] ?? "⚙️"}
            </span>

            {/* label */}
            <span style={{ color: "var(--text)" }} className="flex-1 font-medium">
              {TOOL_LABELS[step.name] ?? step.name}
            </span>

            {/* status indicator */}
            {step.status === "running" && (
              <span className="relative flex h-2 w-2">
                <span
                  className="pulse-ring absolute inline-flex h-full w-full rounded-full opacity-75"
                  style={{ background: "var(--accent)" }}
                />
                <span
                  className="relative inline-flex rounded-full h-2 w-2"
                  style={{ background: "var(--accent)" }}
                />
              </span>
            )}
            {step.status === "done" && (
              <span className="text-green-400 font-bold">✓</span>
            )}
            {step.status === "error" && (
              <span className="text-red-400 font-bold">✗</span>
            )}

            {/* show key result fields */}
            {step.status === "done" && step.result && (
              <span style={{ color: "var(--muted)" }} className="max-w-[180px] truncate">
                {summariseResult(step.result)}
              </span>
            )}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

function summariseResult(r: Record<string, unknown>): string {
  // LangGraph node results
  if (r.score !== undefined) {
    const score = Number(r.score);
    const passed = r.passed;
    const bar = "█".repeat(Math.round(score / 2)) + "░".repeat(5 - Math.round(score / 2));
    return `${bar} ${score}/10 ${passed ? "✓" : "→重试"}`;
  }
  if (r.intent)      return `意图: ${r.intent}`;
  if (r.blueprint)   return `BPM=${(r.blueprint as Record<string, unknown>).bpm} ${(r.blueprint as Record<string, unknown>).key}`;
  if (r.snippet)     return String(r.snippet).slice(0, 60);
  if (r.reason)      return String(r.reason).slice(0, 60);
  if (r.audio_url)   return "✦ audio ready";
  if (r.midi_file_id) return `midi: ${r.midi_file_id}`;
  // legacy
  if (r.status === "ok") {
    if (r.answer)  return String(r.answer).slice(0, 60);
    if (r.tracks)  return `${(r.tracks as unknown[]).length} tracks`;
  }
  if (r.status === "error") return String(r.message ?? "error").slice(0, 60);
  return "";
}
