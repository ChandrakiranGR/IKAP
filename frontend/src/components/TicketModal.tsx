import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { supabase } from "@/integrations/supabase/client";
import { toast } from "sonner";
import { X, Ticket, Loader2 } from "lucide-react";

interface Source {
  chunk_id: string;
  article_title: string;
  source_url?: string;
  snippet: string;
}

interface TicketModalProps {
  open: boolean;
  onClose: () => void;
  question: string;
  answer: string;
  sources: Source[];
  sessionId: string;
}

export function TicketModal({ open, onClose, question, answer, sources, sessionId }: TicketModalProps) {
  const [urgency, setUrgency] = useState("medium");
  const [contactEmail, setContactEmail] = useState("");
  const [shortDesc, setShortDesc] = useState(question.slice(0, 160));
  const [loading, setLoading] = useState(false);

  const detailedDesc = `User Question: ${question}\n\nAssistant Answer: ${answer}\n\nSources:\n${sources.map((s, i) => `${i + 1}. ${s.article_title}${s.source_url ? ` - ${s.source_url}` : ""}`).join("\n")}\n\nTimestamp: ${new Date().toISOString()}`;

  const handleSubmit = async () => {
    setLoading(true);
    try {
      const { data, error } = await supabase.functions.invoke("ticket", {
        body: {
          session_id: sessionId,
          question,
          answer,
          sources: sources.map((s) => s.source_url).filter(Boolean),
          urgency,
          contact_email: contactEmail || undefined,
          short_description: shortDesc,
          description: detailedDesc,
        },
      });
      if (error) throw error;
      if (data.incident_number) {
        toast.success(`Ticket created: ${data.incident_number}`);
      } else {
        toast.success("Ticket captured (ServiceNow not configured yet).");
      }
      onClose();
    } catch (err) {
      console.error(err);
      toast.error("Failed to create ticket.");
    } finally {
      setLoading(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/50 backdrop-blur-sm">
      <div className="mx-4 w-full max-w-lg rounded-lg border bg-card p-6 shadow-lg">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="flex items-center gap-2 text-lg font-semibold text-foreground">
            <Ticket className="h-5 w-5 text-primary" />
            Create ServiceNow Ticket
          </h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">Short Description</label>
            <input
              value={shortDesc}
              onChange={(e) => setShortDesc(e.target.value)}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm text-foreground"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">Detailed Description</label>
            <textarea
              value={detailedDesc}
              readOnly
              rows={5}
              className="w-full rounded-md border bg-muted px-3 py-2 text-xs text-muted-foreground"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Urgency</label>
              <select
                value={urgency}
                onChange={(e) => setUrgency(e.target.value)}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm text-foreground"
              >
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Contact Email (optional)</label>
              <input
                type="email"
                value={contactEmail}
                onChange={(e) => setContactEmail(e.target.value)}
                placeholder="your@email.com"
                className="w-full rounded-md border bg-background px-3 py-2 text-sm text-foreground"
              />
            </div>
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={loading}>
            {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            Submit Ticket
          </Button>
        </div>
      </div>
    </div>
  );
}
