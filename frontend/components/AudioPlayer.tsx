"use client";

import { useEffect, useRef, useState } from "react";
import { audioUrl } from "@/lib/api";

export function AudioPlayer({ src }: { src: string }) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [duration, setDuration] = useState(0);
  const full = audioUrl(src);

  const toggle = () => {
    const a = audioRef.current;
    if (!a) return;
    if (playing) { a.pause(); } else { a.play(); }
  };

  useEffect(() => {
    const a = audioRef.current;
    if (!a) return;
    const onPlay  = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    const onTime  = () => setProgress(a.currentTime);
    const onMeta  = () => setDuration(a.duration);
    a.addEventListener("play",  onPlay);
    a.addEventListener("pause", onPause);
    a.addEventListener("timeupdate", onTime);
    a.addEventListener("loadedmetadata", onMeta);
    return () => {
      a.removeEventListener("play",  onPlay);
      a.removeEventListener("pause", onPause);
      a.removeEventListener("timeupdate", onTime);
      a.removeEventListener("loadedmetadata", onMeta);
    };
  }, []);

  const fmt = (s: number) =>
    `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

  return (
    <div
      className="mt-3 flex items-center gap-3 rounded-xl px-4 py-2.5 w-full max-w-sm"
      style={{ background: "var(--surface)", border: "1px solid var(--border)" }}
    >
      <audio ref={audioRef} src={full} preload="metadata" />

      {/* play/pause */}
      <button
        onClick={toggle}
        className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 transition-opacity hover:opacity-80"
        style={{ background: "var(--accent)" }}
      >
        {playing
          ? <span className="text-white text-xs font-bold">⏸</span>
          : <span className="text-white text-xs font-bold pl-0.5">▶</span>
        }
      </button>

      {/* progress bar */}
      <div className="flex-1 flex flex-col gap-1">
        <input
          type="range"
          min={0}
          max={duration || 1}
          value={progress}
          onChange={(e) => {
            const a = audioRef.current;
            if (a) a.currentTime = +e.target.value;
          }}
          className="w-full h-1 accent-purple-500 cursor-pointer"
        />
        <div className="flex justify-between text-xs" style={{ color: "var(--muted)" }}>
          <span>{fmt(progress)}</span>
          <span>{fmt(duration)}</span>
        </div>
      </div>

      {/* download */}
      <a
        href={full}
        download
        className="text-xs px-2 py-1 rounded-lg hover:opacity-80 transition-opacity"
        style={{ background: "#ffffff11", color: "var(--muted)" }}
      >
        ↓
      </a>
    </div>
  );
}
