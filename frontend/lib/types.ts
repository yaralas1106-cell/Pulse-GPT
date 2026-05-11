export type ToolStep = {
  name: string;
  status: "running" | "done" | "error";
  input?: Record<string, unknown>;
  result?: Record<string, unknown>;
};

export type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
  audioUrl?: string;
  midiUrl?: string;
  steps?: ToolStep[];       // agent thought chain
  streaming?: boolean;
};
