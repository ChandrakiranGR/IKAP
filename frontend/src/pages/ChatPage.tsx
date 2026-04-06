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
import { postChatMessage, type Source } from "@/lib/api";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  confidence?: "low" | "medium" | "high";
}

const SAMPLE_PROMPTS = [
  "How do I reset my Northeastern password?",
  "How do I update Duo when I get a new phone?",
  "How do I connect to VPN on my Mac?",
  "Give me the link for Turnitin quick submit.",
  "How do I connect to eduroam on Android?",
  "How do I send messages with Qwickly before I publish my Canvas course?",
];

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

function confidenceClasses(confidence?: ChatMessage["confidence"]): string {
  if (confidence === "high") {
    return "border-emerald-200 bg-emerald-50 text-emerald-700";
  }
  if (confidence === "low") {
    return "border-amber-200 bg-amber-50 text-amber-700";
  }
  return "border-sky-200 bg-sky-50 text-sky-700";
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

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    const q = searchParams.get("q");
    if (!q || messages.length > 0 || input.trim()) return;
    setInput(q.trim());
  }, [input, messages.length, searchParams]);

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
      const data = await postChatMessage(text, controller.signal);
      if (controller.signal.aborted) return;

      const assistantMsg: ChatMessage = {
        id: (typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : Math.random().toString(36).substring(2, 15)),
        role: "assistant",
        content:
          stripLegacySourceTags(data.answer) ||
          "I couldn't find relevant information in the knowledge base.",
        sources: data.sources || [],
        confidence: data.confidence || "medium",
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
      <div className="mt-4 border-t border-border/70 pt-4">
        <div className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          Sources
        </div>
        <div className="space-y-2">
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
                className="source-card block"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-1">
                    <div className="font-medium text-foreground">{source.article_title}</div>
                    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                      {source.article_id && <span>{source.article_id}</span>}
                      {source.section && (
                        <span className="rounded-full bg-secondary px-2 py-0.5 text-[11px]">
                          {source.section}
                        </span>
                      )}
                    </div>
                  </div>
                  {source.source_url && (
                    <ExternalLink className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                  )}
                </div>
                {source.snippet && (
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                    {source.snippet}
                  </p>
                )}
                {source.source_url && (
                  <div className="mt-3 text-xs font-medium text-primary">Open KB article</div>
                )}
              </CardTag>
            );
          })}
        </div>
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
          className={`max-w-[80%] rounded-lg px-4 py-3 ${
            isUser ? "bg-chat-user text-foreground" : "border bg-chat-assistant text-foreground"
          }`}
        >
          {!isUser && (
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <Badge
                variant="outline"
                className={confidenceClasses(msg.confidence)}
              >
                {confidenceLabel(msg.confidence)}
              </Badge>
              {msg.sources?.length ? (
                <span className="text-xs text-muted-foreground">
                  {msg.sources.length} source{msg.sources.length === 1 ? "" : "s"}
                </span>
              ) : (
                <span className="text-xs text-muted-foreground">No source cards returned</span>
              )}
            </div>
          )}

          <div className="prose prose-sm max-w-none text-sm leading-relaxed">
            <ReactMarkdown
              components={{
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
              {msg.content}
            </ReactMarkdown>
          </div>

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

          {!isUser && renderSources(msg.sources)}
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

            <div className="mx-auto max-w-3xl space-y-4">
              {messages.map((msg) => renderMessage(msg))}
              {loading && (
                <div className="flex justify-start">
                  <div className="rounded-xl border bg-chat-assistant px-4 py-3 shadow-sm">
                    <div className="flex items-center gap-2">
                      <Loader2 className="h-4 w-4 animate-spin text-primary" />
                      <span className="text-sm font-medium text-foreground">
                        IKAP is searching the KB
                      </span>
                    </div>
                    <p className="mt-2 text-sm text-muted-foreground">
                      Grounding this answer in Northeastern IT articles and links.
                    </p>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          </div>

          <div className="border-t bg-card/95 p-4 backdrop-blur">
            {lastError && (
              <div className="mx-auto mb-3 flex max-w-3xl items-start gap-3 rounded-xl border border-destructive/20 bg-destructive/5 px-4 py-3 text-sm text-destructive">
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
              className="mx-auto max-w-3xl"
            >
              <div className="rounded-2xl border bg-background p-3 shadow-sm">
                <Textarea
                  ref={textareaRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Ask about IT services, MFA, VPN, accounts, Canvas, software, or Student Hub..."
                  className="min-h-[88px] resize-none border-0 px-1 py-1 text-sm shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
                  disabled={loading}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      sendMessage();
                    }
                  }}
                />
                <div className="mt-3 flex flex-col gap-3 border-t pt-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="text-xs text-muted-foreground">
                    Press Enter to send. Use Shift+Enter for a new line.
                  </div>
                  <div className="flex items-center justify-end gap-2">
                    {loading ? (
                      <Button
                        type="button"
                        onClick={handleStop}
                        variant="destructive"
                        title="Stop generating"
                      >
                        <Square className="mr-2 h-4 w-4" />
                        Stop
                      </Button>
                    ) : (
                      <>
                        <Button
                          type="button"
                          variant="ghost"
                          onClick={() => setInput("")}
                          disabled={!input.trim()}
                        >
                          Clear
                        </Button>
                        <Button type="submit" disabled={!input.trim()}>
                          <Send className="mr-2 h-4 w-4" />
                          Send
                        </Button>
                      </>
                    )}
                  </div>
                </div>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
