import React, { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  AlertCircle,
  BookOpen,
  ExternalLink,
  Loader2,
  Pencil,
  Send,
  Sparkles,
  Square,
} from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { Navbar } from "@/components/Navbar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  postChatMessage,
  type HistoryItem,
  type Source,
  type StructuredAnswer,
} from "@/lib/api";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  confidence?: "low" | "medium" | "high";
  mode?: "grounded" | "clarify" | "unsupported" | "unsafe";
  structured?: StructuredAnswer;
}

const SAMPLE_PROMPTS = [
  "How do I reset my Northeastern password?",
  "How do I update Duo when I get a new phone?",
  "How do I connect to VPN on my Mac?",
  "Give me the link for Turnitin quick submit.",
  "How do I connect to eduroam on Android?",
  "How do I send messages with Qwickly before I publish my Canvas course?",
];
const IT_TOPIC_SUGGESTIONS = [
  { label: "Password reset", prompt: "How do I reset my Northeastern password?" },
  { label: "Duo MFA", prompt: "How do I update Duo when I get a new phone?" },
  { label: "VPN", prompt: "How do I connect to VPN on Windows?" },
  { label: "Wi-Fi", prompt: "How do I connect to eduroam on Android?" },
  { label: "Canvas", prompt: "How do I publish courses and modules in Canvas?" },
  { label: "Software", prompt: "How do I get access to software at Northeastern?" },
];
const API_HISTORY_CONTENT_LIMIT = 4000;

function stripLegacySourceTags(answer: string): string {
  return answer
    .replace(/\s*\[Source\s*\d+\]/gi, "")
    .replace(/\s*\[Sources?\s*\d+(?:\s*,\s*\d+)*\]/gi, "")
    .trim();
}

function confidenceLabel(confidence?: ChatMessage["confidence"]): string {
  if (confidence === "high") return "High confidence";
  if (confidence === "low") return "Low confidence";
  return "Medium confidence";
}

function statusLabel(message: ChatMessage): string {
  if (message.mode === "clarify") return "Needs clarification";
  if (message.mode === "unsupported") return "Out of scope";
  if (message.mode === "unsafe") return "Cannot help with that";
  return confidenceLabel(message.confidence);
}

function statusClasses(message: ChatMessage): string {
  if (message.mode === "unsafe") {
    return "border-rose-200 bg-rose-50 text-rose-700";
  }
  if (message.mode === "clarify" || message.mode === "unsupported") {
    return "border-slate-200 bg-slate-50 text-slate-700";
  }
  if (message.confidence === "high") {
    return "border-emerald-200 bg-emerald-50 text-emerald-700";
  }
  if (message.confidence === "low") {
    return "border-amber-200 bg-amber-50 text-amber-700";
  }
  return "border-sky-200 bg-sky-50 text-sky-700";
}

function buildHistory(messages: ChatMessage[]): HistoryItem[] {
  return messages.slice(-6).map((message) => ({
    role: message.role,
    content: message.content.slice(0, API_HISTORY_CONTENT_LIMIT),
  }));
}

function hasStructuredContent(structured?: StructuredAnswer): boolean {
  if (!structured) return false;
  return Boolean(
    structured.category ||
      structured.clarifying_question ||
      structured.steps?.length ||
      structured.references?.length ||
      structured.support_message,
  );
}

function MarkdownInline({ content }: { content: string }) {
  return (
    <ReactMarkdown
      components={{
        p: ({ children }) => <>{children}</>,
        a: ({ href, children }) => (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary underline hover:text-primary/80"
          >
            {children}
          </a>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

export default function ChatPage() {
  const [searchParams] = useSearchParams();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [editingMsgId, setEditingMsgId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [lastError, setLastError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const resizeComposer = () => {
    const element = textareaRef.current;
    if (!element) return;
    element.style.height = "0px";
    element.style.height = `${Math.min(element.scrollHeight, 168)}px`;
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    const q = searchParams.get("q");
    if (!q || messages.length > 0 || input.trim()) return;
    setInput(q.trim());
  }, [input, messages.length, searchParams]);

  useEffect(() => {
    resizeComposer();
  }, [input]);

  const primePrompt = (prompt: string) => {
    setInput(prompt);
    setLastError(null);
    setEditingMsgId(null);
    setEditText("");
    textareaRef.current?.focus();
  };

  const sendMessage = async (messageText?: string) => {
    const text = (messageText || input).trim();
    if (!text || loading) return;

    setLastError(null);

    const userMsg: ChatMessage = {
      id: (typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : Math.random().toString(36).substring(2, 15)),
      role: "user",
      content: text,
    };

    setMessages((prev) => [...prev, userMsg]);
    if (!messageText) setInput("");
    setLoading(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const data = await postChatMessage(text, buildHistory(messages), controller.signal);
      if (controller.signal.aborted) return;

      const assistantMsg: ChatMessage = {
        id: (typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : Math.random().toString(36).substring(2, 15)),
        role: "assistant",
        content:
          stripLegacySourceTags(data.answer) ||
          "I couldn't find relevant information in the knowledge base.",
        sources: data.sources || [],
        confidence: data.confidence || "medium",
        mode: data.mode,
        structured: data.structured,
      };

      setMessages((prev) => [...prev, assistantMsg]);
    } catch (error) {
      if (controller.signal.aborted) return;
      const message =
        error instanceof Error
          ? error.message
          : "Sorry, I encountered an error processing your request. Please try again.";
      setLastError(message);
      toast.error(message);
      setMessages((prev) => [
        ...prev,
        {
          id: (typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : Math.random().toString(36).substring(2, 15)),
          role: "assistant",
          content:
            "Sorry, I encountered an error processing your request. Please try again.",
        },
      ]);
    } finally {
      abortControllerRef.current = null;
      setLoading(false);
    }
  };

  const handleStop = () => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    setLoading(false);
  };

  const handleEditStart = (msg: ChatMessage) => {
    setEditingMsgId(msg.id);
    setEditText(msg.content);
  };

  const handleEditSubmit = (msgId: string) => {
    const text = editText.trim();
    if (!text) return;
    setMessages((prev) => {
      const idx = prev.findIndex((m) => m.id === msgId);
      return idx >= 0 ? prev.slice(0, idx) : prev;
    });
    setEditingMsgId(null);
    setEditText("");
    sendMessage(text);
  };

  const handleEditCancel = () => {
    setEditingMsgId(null);
    setEditText("");
  };

  const renderSources = (sources?: Source[]) => {
    if (!sources?.length) return null;

    return (
      <aside className="rounded-2xl border border-border/80 bg-background/80 p-4">
        <div className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          Sources
        </div>
        <div className="space-y-2.5">
          {sources.map((source) => {
            const CardTag = source.source_url ? "a" : "div";

            return (
              <CardTag
                key={source.chunk_id}
                {...(source.source_url
                  ? {
                      href: source.source_url,
                      target: "_blank",
                      rel: "noopener noreferrer",
                    }
                  : {})}
                className="source-card block rounded-xl border border-border/80 bg-card/80 p-3 shadow-sm hover:border-primary/30"
              >
                <div className="flex items-start gap-3">
                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="line-clamp-3 text-sm font-medium leading-5 text-foreground">
                      {source.article_title}
                    </div>
                    <div className="flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                      {source.article_id && <span>{source.article_id}</span>}
                      {source.section && <span>{source.section}</span>}
                    </div>
                  </div>
                  {source.source_url ? (
                    <ExternalLink className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                  ) : null}
                </div>
              </CardTag>
            );
          })}
        </div>
      </aside>
    );
  };

  const renderStructuredContent = (message: ChatMessage) => {
    const structured = message.structured;
    if (!hasStructuredContent(structured)) {
      return (
        <div className="prose prose-sm max-w-none text-sm leading-relaxed">
          <MarkdownInline content={message.content} />
        </div>
      );
    }

    const shouldRenderAsProcedure = message.mode === "grounded";
    const guidanceTitle =
      message.mode === "unsafe"
        ? "Safe guidance"
        : message.mode === "unsupported"
          ? "How IKAP can help"
          : "Guidance";
    const shouldShowSupport = message.mode === "grounded" || message.mode === "unsafe";
    const shouldShowClarifyingQuestion = Boolean(
      structured?.clarifying_question && message.mode !== "unsupported",
    );
    const supportLines = (structured?.support_message || "")
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);

    return (
      <div className="space-y-4 text-sm leading-relaxed">
        {structured?.category && (
          <div className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            {structured.category}
          </div>
        )}

        {shouldShowClarifyingQuestion && (
          <div className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-sky-900">
            <div className="mb-1 text-xs font-semibold uppercase tracking-[0.12em] text-sky-700">
              Clarifying question
            </div>
            <div>{structured.clarifying_question}</div>
          </div>
        )}

        {!!structured?.steps?.length && (
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              {shouldRenderAsProcedure ? "Steps" : guidanceTitle}
            </div>
            {shouldRenderAsProcedure ? (
              <ol className="space-y-2 pl-5">
                {structured.steps.map((step, idx) => (
                  <li key={`${message.id}-step-${idx}`} className="list-decimal">
                    <MarkdownInline content={step} />
                  </li>
                ))}
              </ol>
            ) : (
              <div className="rounded-xl border border-slate-200 bg-slate-50/80 px-4 py-3 text-slate-800">
                <div className="space-y-2">
                  {structured.steps.map((step, idx) => (
                    <p
                      key={`${message.id}-guidance-${idx}`}
                      className={idx === 0 ? "font-medium leading-6" : "leading-6 text-slate-600"}
                    >
                      <MarkdownInline content={step} />
                    </p>
                  ))}
                </div>
              </div>
            )}

            {message.mode === "unsupported" && (
              <div className="mt-3">
                <div className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
                  Try an IT topic
                </div>
                <div className="flex flex-wrap gap-2">
                  {IT_TOPIC_SUGGESTIONS.map((suggestion) => (
                    <button
                      key={suggestion.label}
                      type="button"
                      onClick={() => primePrompt(suggestion.prompt)}
                      className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:border-primary/40 hover:bg-primary/5 hover:text-primary"
                    >
                      {suggestion.label}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {!!structured?.references?.length && (
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              References
            </div>
            <div className="space-y-2">
              {structured.references.map((reference, idx) => (
                <a
                  key={`${message.id}-reference-${idx}`}
                  href={reference.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center justify-between rounded-xl border px-3 py-2 transition hover:border-primary/40 hover:bg-primary/5"
                >
                  <span className="pr-3">{reference.label}</span>
                  <ExternalLink className="h-4 w-4 shrink-0 text-muted-foreground" />
                </a>
              ))}
            </div>
          </div>
        )}

        {shouldShowSupport && !!supportLines.length && (
          <div className="rounded-xl border border-border/70 bg-secondary/30 px-4 py-3">
            <div className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              Need more help?
            </div>
            <div className="space-y-1 text-sm text-muted-foreground">
              {supportLines.map((line, idx) => (
                <div key={`${message.id}-support-${idx}`} className="leading-6">
                  {line.startsWith("- ") ? (
                    <div className="flex gap-2">
                      <span className="pt-[2px] text-muted-foreground">•</span>
                      <div className="min-w-0">
                        <MarkdownInline content={line.slice(2)} />
                      </div>
                    </div>
                  ) : (
                    <MarkdownInline content={line} />
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderMessage = (msg: ChatMessage) => {
    const isUser = msg.role === "user";
    const isEditing = editingMsgId === msg.id;

    if (isUser && isEditing) {
      return (
        <div key={msg.id} className="flex justify-end">
          <div className="w-full max-w-[80%] rounded-lg bg-chat-user px-4 py-3">
            <textarea
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              className="w-full resize-none rounded border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              rows={3}
              autoFocus
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleEditSubmit(msg.id);
                }
                if (e.key === "Escape") handleEditCancel();
              }}
            />
            <div className="mt-2 flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={handleEditCancel}>
                Cancel
              </Button>
              <Button size="sm" onClick={() => handleEditSubmit(msg.id)} disabled={!editText.trim()}>
                Send
              </Button>
            </div>
          </div>
        </div>
      );
    }

    return (
      <div key={msg.id} className={`group flex ${isUser ? "justify-end" : "justify-start"}`}>
        <div
          className={`w-full ${
            isUser
              ? "max-w-[42rem] rounded-2xl bg-chat-user px-4 py-3 text-foreground shadow-sm"
              : "max-w-6xl text-foreground"
          }`}
        >
          {!isUser && (
            <div className="mb-3 flex flex-wrap items-center gap-2 px-1">
              <Badge
                variant="outline"
                className={statusClasses(msg)}
              >
                {statusLabel(msg)}
              </Badge>
              {msg.mode === "grounded" && msg.sources?.length ? (
                <span className="text-xs text-muted-foreground">
                  {msg.sources.length} source{msg.sources.length === 1 ? "" : "s"}
                </span>
              ) : msg.mode === "grounded" ? (
                <span className="text-xs text-muted-foreground">No source cards returned</span>
              ) : null}
            </div>
          )}

          {isUser ? (
            renderStructuredContent(msg)
          ) : (
            <div
              className={`grid gap-4 ${
                msg.mode === "grounded" && msg.sources?.length ? "lg:grid-cols-[minmax(0,1fr)_260px]" : ""
              }`}
            >
              <div className="rounded-2xl border bg-chat-assistant px-4 py-4 shadow-sm sm:px-5">
                {renderStructuredContent(msg)}
              </div>
              {msg.mode === "grounded" && msg.sources?.length ? (
                <div className="lg:pt-0">
                  {renderSources(msg.sources)}
                </div>
              ) : null}
            </div>
          )}

          {isUser && !loading && (
            <div className="mt-1 flex justify-end opacity-0 transition-opacity group-hover:opacity-100">
              <button
                onClick={() => handleEditStart(msg)}
                className="rounded p-1 text-muted-foreground transition-colors hover:text-foreground"
                title="Edit message"
              >
                <Pencil className="h-3 w-3" />
              </button>
            </div>
          )}

        </div>
      </div>
    );
  };

  return (
    <div className="flex h-screen flex-col bg-background">
      <Navbar />
      <div className="flex flex-1 overflow-hidden">
        <div className="flex flex-1 flex-col">
          <div className="flex-1 overflow-y-auto bg-[radial-gradient(circle_at_top,_hsl(var(--primary)/0.08),_transparent_38%),linear-gradient(to_bottom,_hsl(var(--background)),_hsl(var(--neu-gray-50)))] p-4">
            {messages.length === 0 && (
              <div className="flex h-full items-center justify-center">
                <div className="w-full max-w-3xl rounded-2xl border bg-card/90 p-8 shadow-sm backdrop-blur">
                  <div className="text-center">
                    <BookOpen className="mx-auto mb-4 h-12 w-12 text-primary/70" />
                    <h2 className="mb-2 text-2xl font-semibold text-foreground">Ask IKAP</h2>
                    <p className="mx-auto max-w-2xl text-sm leading-6 text-muted-foreground">
                      Ask about accounts, MFA, VPN, Wi-Fi, Canvas, software, or Student Hub and
                      get KB-grounded steps with article links.
                    </p>
                  </div>

                  <div className="mt-8 grid gap-3 md:grid-cols-2">
                    {SAMPLE_PROMPTS.map((prompt) => (
                      <button
                        key={prompt}
                        type="button"
                        onClick={() => primePrompt(prompt)}
                        className="rounded-xl border bg-background px-4 py-3 text-left text-sm transition hover:border-primary/40 hover:bg-primary/5"
                      >
                        <div className="mb-1 flex items-center gap-2 font-medium text-foreground">
                          <Sparkles className="h-4 w-4 text-primary" />
                          Try this
                        </div>
                        <div className="text-muted-foreground">{prompt}</div>
                      </button>
                    ))}
                  </div>

                  <div className="mt-6 rounded-xl border border-dashed bg-secondary/40 px-4 py-3 text-sm text-muted-foreground">
                    Tip: Ask in plain language like “How do I connect to VPN on my Mac?” or
                    “Give me the Turnitin quick submit link.”
                  </div>
                </div>
              </div>
            )}

            <div className="mx-auto max-w-6xl space-y-5">
              {messages.map((msg) => renderMessage(msg))}
              {loading && (
                <div className="flex justify-start">
                  <div className="rounded-2xl border bg-chat-assistant px-4 py-3 shadow-sm">
                    <div className="flex items-center gap-2">
                      <Loader2 className="h-4 w-4 animate-spin text-primary" />
                      <span className="text-sm font-medium text-foreground">
                        IKAP is checking your request
                      </span>
                    </div>
                    <p className="mt-2 text-sm text-muted-foreground">
                      If it is a Northeastern IT question, IKAP will ground the answer in KB articles and links.
                    </p>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          </div>

          <div className="border-t bg-card/90 px-3 py-2 backdrop-blur">
            {lastError && (
              <div className="mx-auto mb-3 flex max-w-6xl items-start gap-3 rounded-xl border border-destructive/20 bg-destructive/5 px-4 py-3 text-sm text-destructive">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <div>
                  <div className="font-medium">Request failed</div>
                  <div className="text-destructive/90">{lastError}</div>
                </div>
              </div>
            )}

            <form
              onSubmit={(e) => {
                e.preventDefault();
                sendMessage();
              }}
              className="mx-auto max-w-6xl"
            >
              <div className="rounded-[28px] border bg-background/95 px-4 py-2 shadow-lg backdrop-blur">
                <div className="flex items-end gap-3">
                  <Textarea
                    ref={textareaRef}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder="Ask about IT services, MFA, VPN, accounts, Canvas, software, or Student Hub..."
                    rows={1}
                    className="max-h-40 min-h-[24px] flex-1 resize-none border-0 bg-transparent px-0 py-2 text-sm leading-6 shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
                    disabled={loading}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        sendMessage();
                      }
                    }}
                  />
                  <div className="flex items-center gap-2 pb-1">
                    {!loading && input.trim() ? (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => setInput("")}
                        className="rounded-full px-3 text-xs"
                      >
                        Clear
                      </Button>
                    ) : null}
                    {loading ? (
                      <Button
                        type="button"
                        onClick={handleStop}
                        variant="destructive"
                        size="icon"
                        title="Stop generating"
                        className="h-10 w-10 rounded-full"
                      >
                        <Square className="h-4 w-4" />
                      </Button>
                    ) : (
                      <Button
                        type="submit"
                        size="icon"
                        disabled={!input.trim()}
                        className="h-10 w-10 rounded-full"
                        title="Send message"
                      >
                        <Send className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                </div>
              </div>
              <div className="px-2 pt-1 text-[11px] text-muted-foreground/80">
                Enter to send. Shift+Enter for a new line.
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
