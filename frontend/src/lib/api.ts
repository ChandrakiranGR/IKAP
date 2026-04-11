export interface Source {
  chunk_id: string;
  article_title: string;
  article_id?: string | null;
  section?: string | null;
  source_url?: string | null;
  snippet: string;
}

export interface HistoryItem {
  role: "user" | "assistant";
  content: string;
}

export interface StructuredReference {
  label: string;
  url: string;
}

export interface StructuredAnswer {
  category?: string | null;
  clarifying_question?: string | null;
  steps: string[];
  references: StructuredReference[];
  support_message?: string | null;
}

export interface ChatResponse {
  answer: string;
  sources: Source[];
  confidence: "low" | "medium" | "high";
  mode: "grounded" | "clarify" | "unsupported" | "unsafe";
  structured: StructuredAnswer;
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}

export async function postChatMessage(
  question: string,
  history: HistoryItem[] = [],
  signal?: AbortSignal,
): Promise<ChatResponse> {
  const response = await fetch(apiUrl("/api/chat"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ question, history }),
    signal,
  });

  if (!response.ok) {
    let detail = "Request failed.";
    try {
      const payload = await response.json();
      detail = payload.detail || payload.error || detail;
    } catch {
      // Keep default detail when the response is not JSON.
    }
    throw new Error(detail);
  }

  return (await response.json()) as ChatResponse;
}
