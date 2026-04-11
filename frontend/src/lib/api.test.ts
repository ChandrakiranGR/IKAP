import { afterEach, describe, expect, it, vi } from "vitest";

import { postChatMessage } from "@/lib/api";

const originalFetch = global.fetch;

describe("postChatMessage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    global.fetch = originalFetch;
  });

  it("posts the question to the chat API and returns the parsed payload", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        answer: "Test answer",
        sources: [],
        confidence: "high",
        mode: "grounded",
        structured: {
          category: "VPN access",
          clarifying_question: null,
          steps: ["Install GlobalProtect."],
          references: [],
          support_message: "Contact support.",
        },
      }),
    });

    global.fetch = fetchMock as typeof fetch;

    const result = await postChatMessage("How do I connect to VPN on my Mac?", [
      { role: "user", content: "I need help with VPN" },
    ]);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/chat",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: "How do I connect to VPN on my Mac?",
          history: [{ role: "user", content: "I need help with VPN" }],
        }),
      }),
    );
    expect(result).toEqual({
      answer: "Test answer",
      sources: [],
      confidence: "high",
      mode: "grounded",
      structured: {
        category: "VPN access",
        clarifying_question: null,
        steps: ["Install GlobalProtect."],
        references: [],
        support_message: "Contact support.",
      },
    });
  });

  it("surfaces API error details when the request fails", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({
        detail: "Question cannot be empty.",
      }),
    });

    global.fetch = fetchMock as typeof fetch;

    await expect(postChatMessage("")).rejects.toThrow("Question cannot be empty.");
  });
});
