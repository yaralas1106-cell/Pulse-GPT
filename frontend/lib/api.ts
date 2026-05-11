// 本地开发用 localhost 直连；生产/隧道模式用 Next.js 反向代理路径
const API = process.env.NEXT_PUBLIC_API_BASE ?? "/api/tomi";

export type SSEEvent =
  | { type: "session";     session_id: string }
  | { type: "tool_call";   name: string; input: Record<string, unknown> }
  | { type: "tool_result"; name: string; result: Record<string, unknown> }
  | { type: "done";        text: string; audio_url: string | null; midi_url: string | null }
  | { type: "error";       message: string };

export function chatStream(
  message: string,
  sessionId: string,
  onEvent: (e: SSEEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return fetch(`${API}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
    signal,
  }).then((res) => {
    const reader = res.body!.getReader();
    const dec = new TextDecoder();
    let buf = "";

    function pump(): Promise<void> {
      return reader.read().then(({ done, value }) => {
        if (done) return;
        buf += dec.decode(value, { stream: true });
        const lines = buf.split("\n\n");
        buf = lines.pop() ?? "";
        for (const line of lines) {
          const data = line.replace(/^data: /, "").trim();
          if (data) {
            try { onEvent(JSON.parse(data)); } catch {}
          }
        }
        return pump();
      });
    }
    return pump();
  });
}

export function audioUrl(path: string) {
  return path.startsWith("http") ? path : `${API}${path}`;
}

export function resetSession(sessionId: string) {
  return fetch(`${API}/session/${sessionId}`, { method: "DELETE" });
}

// ── Ableton direct edit ───────────────────────────────────────────────────────

export type AbletonEditResult = {
  status: string;
  instruction: string;
  results?: Array<{
    track: string;
    status: string;
    ops_applied?: Array<{ op: string; [k: string]: unknown }>;
    notes_before?: number;
    notes_after?: number;
  }>;
  llm_response?: string;
};

export async function abletonEdit(
  instruction: string,
  seed = 0,
): Promise<AbletonEditResult> {
  const res = await fetch(`${API}/ableton/edit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ instruction, seed }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function abletonState() {
  const res = await fetch(`${API}/ableton/state`);
  return res.json();
}
