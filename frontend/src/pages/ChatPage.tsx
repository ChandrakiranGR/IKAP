import React, { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { BookOpen, ExternalLink, Loader2, Pencil, Send, Square } from "lucide-react";
import { toast } from "sonner";

import { Navbar } from "@/components/Navbar";
import { Button } from "@/components/ui/button";
import { postChatMessage, type Source } from "@/lib/api";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  confidence?: "low" | "medium" | "high";
}

function stripLegacySourceTags(answer: string): string {
  return answer
    .replace(/\s*\[Source\s*\d+\]/gi, "")
    .replace(/\s*\[Sources?\s*\d+(?:\s*,\s*\d+)*\]/gi, "")
    .trim();
}

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [editingMsgId, setEditingMsgId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const abortControllerRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const sendMessage = async (messageText?: string) => {
    const text = (messageText || input).trim();
    if (!text || loading) return;

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
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
        id: crypto.randomUUID(),
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
      toast.error(message);
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
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
      <div className="mt-3 border-t pt-3">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Sources
        </div>
        <div className="space-y-2">
          {sources.map((source) => (
            <a
              key={source.chunk_id}
              href={source.source_url || "#"}
              target={source.source_url ? "_blank" : undefined}
              rel={source.source_url ? "noopener noreferrer" : undefined}
              className="source-card block"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-medium text-foreground">{source.article_title}</div>
                  {source.article_id && (
                    <div className="text-xs text-muted-foreground">{source.article_id}</div>
                  )}
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
            </a>
          ))}
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
          <div className="flex-1 overflow-y-auto p-4">
            {messages.length === 0 && (
              <div className="flex h-full items-center justify-center">
                <div className="text-center">
                  <BookOpen className="mx-auto mb-4 h-12 w-12 text-muted-foreground/30" />
                  <h2 className="mb-2 text-lg font-semibold text-foreground">Ask IKAP</h2>
                  <p className="text-sm text-muted-foreground">
                    Ask about accounts, MFA, VPN, Wi-Fi, Canvas, software, or Student Hub.
                  </p>
                </div>
              </div>
            )}

            <div className="mx-auto max-w-3xl space-y-4">
              {messages.map((msg) => renderMessage(msg))}
              {loading && (
                <div className="flex justify-start">
                  <div className="flex items-center gap-2 rounded-lg border bg-chat-assistant px-4 py-3">
                    <Loader2 className="h-4 w-4 animate-spin text-primary" />
                    <span className="text-sm text-muted-foreground">IKAP is searching the KB...</span>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          </div>

          <div className="border-t bg-card p-4">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                sendMessage();
              }}
              className="mx-auto flex max-w-3xl gap-2"
            >
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask about IT services, MFA, VPN, accounts..."
                className="flex-1 rounded-lg border bg-background px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                disabled={loading}
              />
              {loading ? (
                <Button type="button" onClick={handleStop} size="icon" variant="destructive" title="Stop generating">
                  <Square className="h-4 w-4" />
                </Button>
              ) : (
                <Button type="submit" disabled={!input.trim()} size="icon">
                  <Send className="h-4 w-4" />
                </Button>
              )}
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
