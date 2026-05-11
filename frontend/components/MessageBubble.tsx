"use client";

import { motion } from "framer-motion";
import { AgentSteps } from "./AgentSteps";
import { AudioPlayer } from "./AudioPlayer";
import type { Message } from "@/lib/types";

export function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === "user";

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className={`flex gap-3 ${isUser ? "flex-row-reverse" : "flex-row"}`}
    >
      {/* avatar */}
      <div
        className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center text-sm font-bold mt-1"
        style={{
          background: isUser
            ? "linear-gradient(135deg,#7c6af7,#e066c8)"
            : "linear-gradient(135deg,#1e2030,#2a2d40)",
          border: "1px solid var(--border)",
        }}
      >
        {isUser ? "U" : "🎵"}
      </div>

      {/* bubble */}
      <div className={`flex flex-col max-w-[70%] ${isUser ? "items-end" : "items-start"}`}>
        <div
          className="rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap"
          style={{
            background: isUser
              ? "linear-gradient(135deg,#7c6af7cc,#e066c8aa)"
              : "var(--surface)",
            border: isUser ? "none" : "1px solid var(--border)",
            color: "var(--text)",
          }}
        >
          {msg.text}
          {msg.streaming && <span className="cursor" />}
        </div>

        {/* agent thought chain */}
        {!isUser && msg.steps && msg.steps.length > 0 && (
          <div className="w-full max-w-lg">
            <AgentSteps steps={msg.steps} />
          </div>
        )}

        {/* audio player */}
        {msg.audioUrl && <AudioPlayer src={msg.audioUrl} />}

        {/* midi download */}
        {msg.midiUrl && (
          <a
            href={`${process.env.NEXT_PUBLIC_API_BASE}${msg.midiUrl}`}
            download
            className="mt-2 text-xs px-3 py-1 rounded-lg hover:opacity-80 transition-opacity"
            style={{ background: "#7c6af722", color: "var(--accent)" }}
          >
            ↓ 下载 MIDI
          </a>
        )}
      </div>
    </motion.div>
  );
}
