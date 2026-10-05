export interface Document {
  doc_id: string;
  filename: string;
  file_type: string;
  uploaded_at: string;
  file_size: number;
  total_chunks: number;
}

export interface Source {
  filename: string;
  chunk_index: number;
  score: number;
  page?: number;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  trace_id?: string;
  feedback?: 1 | -1;
}

export interface Conversation {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ModelOption {
  provider: string;
  model: string;
  label: string;
  free: boolean;
  group: string;
}

export const MODEL_OPTIONS: ModelOption[] = [
  // 무료 모델
  { provider: "gemini", model: "gemini-2.5-flash",         label: "Gemini 2.5 Flash",      free: true,  group: "Google Gemini" },
  { provider: "gemini", model: "gemini-2.5-flash-lite",    label: "Gemini 2.5 Flash-Lite", free: true,  group: "Google Gemini" },
  { provider: "gemini", model: "gemini-3.5-flash",         label: "Gemini 3.5 Flash",      free: true,  group: "Google Gemini" },
  { provider: "gemini", model: "gemini-3.8-flash",         label: "Gemini 3.8 Flash",      free: true,  group: "Google Gemini" },
  { provider: "groq",   model: "openai/gpt-oss-120b",      label: "GPT-OSS 120B",          free: true,  group: "Groq" },
  { provider: "groq",   model: "openai/gpt-oss-20b",       label: "GPT-OSS 20B (빠름)",    free: true,  group: "Groq" },
  { provider: "groq",   model: "qwen/qwen3.8-27b",         label: "Qwen3.8 27B",           free: true,  group: "Groq" },
];

// 유료 모델 — 백엔드는 지원하지만 UI에서는 숨김 (노출하려면 MODEL_OPTIONS에 합칠 것)
export const PAID_MODEL_OPTIONS: ModelOption[] = [
  { provider: "openai", model: "gpt-4o-mini",              label: "GPT-4o Mini",         free: false, group: "OpenAI" },
  { provider: "openai", model: "gpt-4o",                   label: "GPT-4o",              free: false, group: "OpenAI" },
  { provider: "claude", model: "claude-sonnet-4-6",        label: "Claude Sonnet 4.6",   free: false, group: "Claude" },
  { provider: "claude", model: "claude-haiku-4-5-20251001",label: "Claude Haiku 4.5",    free: false, group: "Claude" },
];
