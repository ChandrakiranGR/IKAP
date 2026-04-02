import React, { useEffect, useState } from "react";
import { Navbar } from "@/components/Navbar";
import { AdminGuard } from "@/components/AdminGuard";
import { supabase } from "@/integrations/supabase/client";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Save, Loader2, Plus, Check, Pencil, X } from "lucide-react";
import { Textarea } from "@/components/ui/textarea";

interface Settings {
  embedding_model: string;
  chat_model: string;
  temperature: number;
  max_tokens: number;
  top_k: number;
  enable_mmr: boolean;
  mmr_lambda: number;
  similarity_threshold: number;
  hybrid_enabled: boolean;
  url_allowlist: string[];
  rate_limit_per_minute: number;
  active_prompt_version_id: string | null;
}

interface PromptVersion {
  id: string;
  name: string;
  system_prompt: string;
  created_at: string;
}

const defaultSettings: Settings = {
  embedding_model: "text-embedding-3-small",
  chat_model: "gpt-4o-mini",
  temperature: 0.1,
  max_tokens: 1500,
  top_k: 5,
  enable_mmr: false,
  mmr_lambda: 0.5,
  similarity_threshold: 0.3,
  hybrid_enabled: false,
  url_allowlist: [],
  rate_limit_per_minute: 30,
  active_prompt_version_id: null,
};

export default function AdminSettingsPage() {
  const [settings, setSettings] = useState<Settings>(defaultSettings);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Prompt management state
  const [prompts, setPrompts] = useState<PromptVersion[]>([]);
  const [newPromptName, setNewPromptName] = useState("");
  const [newPromptText, setNewPromptText] = useState("");
  const [showNewForm, setShowNewForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editPrompt, setEditPrompt] = useState("");
  const [savingPrompt, setSavingPrompt] = useState(false);

  const loadData = async () => {
    const [settingsRes, promptsRes] = await Promise.all([
      supabase.from("app_settings").select("*").limit(1).maybeSingle(),
      supabase.from("prompt_versions").select("*").order("created_at", { ascending: false }),
    ]);

    if (settingsRes.data) {
      const d = settingsRes.data;
      setSettings({
        embedding_model: d.embedding_model || defaultSettings.embedding_model,
        chat_model: d.chat_model || defaultSettings.chat_model,
        temperature: d.temperature ?? defaultSettings.temperature,
        max_tokens: d.max_tokens ?? defaultSettings.max_tokens,
        top_k: d.top_k ?? defaultSettings.top_k,
        enable_mmr: d.enable_mmr ?? defaultSettings.enable_mmr,
        mmr_lambda: d.mmr_lambda ?? defaultSettings.mmr_lambda,
        similarity_threshold: d.similarity_threshold ?? defaultSettings.similarity_threshold,
        hybrid_enabled: d.hybrid_enabled ?? defaultSettings.hybrid_enabled,
        url_allowlist: d.url_allowlist || defaultSettings.url_allowlist,
        rate_limit_per_minute: d.rate_limit_per_minute ?? defaultSettings.rate_limit_per_minute,
        active_prompt_version_id: d.active_prompt_version_id || null,
      });
    }
    if (promptsRes.data) setPrompts(promptsRes.data);
    setLoading(false);
  };

  useEffect(() => { loadData(); }, []);

  const handleSave = async () => {
    setSaving(true);
    const { error } = await supabase.from("app_settings").upsert({
      id: "singleton",
      ...settings,
    });
    if (error) toast.error("Failed to save settings");
    else toast.success("Settings saved");
    setSaving(false);
  };

  const handleCreatePrompt = async () => {
    if (!newPromptName.trim() || !newPromptText.trim()) return;
    setSavingPrompt(true);
    const { error } = await supabase.from("prompt_versions").insert({
      name: newPromptName.trim(),
      system_prompt: newPromptText.trim(),
    });
    if (error) toast.error("Failed to create prompt");
    else {
      toast.success("Prompt created");
      setNewPromptName("");
      setNewPromptText("");
      setShowNewForm(false);
      await loadData();
    }
    setSavingPrompt(false);
  };

  const handleUpdatePrompt = async (id: string) => {
    if (!editName.trim() || !editPrompt.trim()) return;
    setSavingPrompt(true);
    const { error } = await supabase.from("prompt_versions").update({
      name: editName.trim(),
      system_prompt: editPrompt.trim(),
    }).eq("id", id);
    if (error) toast.error("Failed to update prompt");
    else {
      toast.success("Prompt updated");
      setEditingId(null);
      await loadData();
    }
    setSavingPrompt(false);
  };

  const handleSetActive = async (id: string) => {
    const { error } = await supabase.from("app_settings").upsert({
      id: "singleton",
      active_prompt_version_id: id,
    });
    if (error) toast.error("Failed to set active prompt");
    else {
      toast.success("Active prompt updated");
      setSettings((s) => ({ ...s, active_prompt_version_id: id }));
    }
  };

  if (loading) return <div className="flex min-h-screen items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>;

  const Field = ({ label, children }: { label: string; children: React.ReactNode }) => (
    <div>
      <label className="mb-1 block text-sm font-medium text-foreground">{label}</label>
      {children}
    </div>
  );

  const inputClass = "w-full rounded-md border bg-background px-3 py-2 text-sm text-foreground";

  return (
    <AdminGuard>
      <div className="min-h-screen bg-background">
        <Navbar />
        <div className="container max-w-2xl py-8">
          <h1 className="mb-6 text-2xl font-bold text-foreground">Settings</h1>

          <div className="space-y-6">
            {/* OpenAI Configuration */}
            <section className="rounded-lg border bg-card p-6">
              <h2 className="mb-4 font-semibold text-foreground">OpenAI Configuration</h2>
              <div className="grid gap-4 md:grid-cols-2">
                <Field label="Embedding Model">
                  <input value={settings.embedding_model} onChange={(e) => setSettings({ ...settings, embedding_model: e.target.value })} className={inputClass} />
                </Field>
                <Field label="Chat Model">
                  <input value={settings.chat_model} onChange={(e) => setSettings({ ...settings, chat_model: e.target.value })} className={inputClass} />
                </Field>
                <Field label="Temperature">
                  <input type="number" step="0.05" min="0" max="2" value={settings.temperature} onChange={(e) => setSettings({ ...settings, temperature: parseFloat(e.target.value) })} className={inputClass} />
                </Field>
                <Field label="Max Tokens">
                  <input type="number" min="100" max="4000" value={settings.max_tokens} onChange={(e) => setSettings({ ...settings, max_tokens: parseInt(e.target.value) })} className={inputClass} />
                </Field>
              </div>
            </section>

            {/* Retrieval Configuration */}
            <section className="rounded-lg border bg-card p-6">
              <h2 className="mb-4 font-semibold text-foreground">Retrieval Configuration</h2>
              <div className="grid gap-4 md:grid-cols-2">
                <Field label="Top K">
                  <input type="number" min="1" max="20" value={settings.top_k} onChange={(e) => setSettings({ ...settings, top_k: parseInt(e.target.value) })} className={inputClass} />
                </Field>
                <Field label="Similarity Threshold">
                  <input type="number" step="0.05" min="0" max="1" value={settings.similarity_threshold} onChange={(e) => setSettings({ ...settings, similarity_threshold: parseFloat(e.target.value) })} className={inputClass} />
                </Field>
                <Field label="Enable MMR">
                  <select value={settings.enable_mmr ? "true" : "false"} onChange={(e) => setSettings({ ...settings, enable_mmr: e.target.value === "true" })} className={inputClass}>
                    <option value="false">Disabled</option>
                    <option value="true">Enabled</option>
                  </select>
                </Field>
                <Field label="MMR Lambda">
                  <input type="number" step="0.1" min="0" max="1" value={settings.mmr_lambda} onChange={(e) => setSettings({ ...settings, mmr_lambda: parseFloat(e.target.value) })} className={inputClass} />
                </Field>
                <Field label="Hybrid Search">
                  <select value={settings.hybrid_enabled ? "true" : "false"} onChange={(e) => setSettings({ ...settings, hybrid_enabled: e.target.value === "true" })} className={inputClass}>
                    <option value="false">Vector Only</option>
                    <option value="true">Hybrid (Vector + Keyword)</option>
                  </select>
                </Field>
                <Field label="Rate Limit (req/min)">
                  <input type="number" min="1" max="100" value={settings.rate_limit_per_minute} onChange={(e) => setSettings({ ...settings, rate_limit_per_minute: parseInt(e.target.value) })} className={inputClass} />
                </Field>
              </div>
            </section>

            <Button onClick={handleSave} disabled={saving} className="w-full">
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
              Save Settings
            </Button>

            {/* System Prompts */}
            <section className="rounded-lg border bg-card p-6">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="font-semibold text-foreground">System Prompts</h2>
                <Button size="sm" variant="outline" onClick={() => setShowNewForm(!showNewForm)}>
                  {showNewForm ? <X className="mr-1 h-4 w-4" /> : <Plus className="mr-1 h-4 w-4" />}
                  {showNewForm ? "Cancel" : "New"}
                </Button>
              </div>

              {showNewForm && (
                <div className="mb-4 space-y-3 rounded-md border border-dashed p-4">
                  <input
                    placeholder="Prompt name"
                    value={newPromptName}
                    onChange={(e) => setNewPromptName(e.target.value)}
                    className={inputClass}
                  />
                  <Textarea
                    placeholder="System prompt text…"
                    value={newPromptText}
                    onChange={(e) => setNewPromptText(e.target.value)}
                    rows={5}
                  />
                  <Button size="sm" onClick={handleCreatePrompt} disabled={savingPrompt || !newPromptName.trim() || !newPromptText.trim()}>
                    {savingPrompt ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Save className="mr-1 h-4 w-4" />}
                    Create
                  </Button>
                </div>
              )}

              {prompts.length === 0 && !showNewForm && (
                <p className="text-sm text-muted-foreground">No prompt versions yet. Click "New" to create one.</p>
              )}

              <div className="space-y-3">
                {prompts.map((p) => {
                  const isActive = settings.active_prompt_version_id === p.id;
                  const isEditing = editingId === p.id;

                  return (
                    <div key={p.id} className={`rounded-md border p-4 ${isActive ? "border-primary bg-primary/5" : ""}`}>
                      {isEditing ? (
                        <div className="space-y-3">
                          <input value={editName} onChange={(e) => setEditName(e.target.value)} className={inputClass} />
                          <Textarea value={editPrompt} onChange={(e) => setEditPrompt(e.target.value)} rows={5} />
                          <div className="flex gap-2">
                            <Button size="sm" onClick={() => handleUpdatePrompt(p.id)} disabled={savingPrompt}>
                              {savingPrompt ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Save className="mr-1 h-4 w-4" />}
                              Save
                            </Button>
                            <Button size="sm" variant="ghost" onClick={() => setEditingId(null)}>Cancel</Button>
                          </div>
                        </div>
                      ) : (
                        <>
                          <div className="mb-1 flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <span className="font-medium text-foreground">{p.name}</span>
                              {isActive && <span className="rounded-full bg-primary px-2 py-0.5 text-xs text-primary-foreground">Active</span>}
                            </div>
                            <div className="flex gap-1">
                              <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => { setEditingId(p.id); setEditName(p.name); setEditPrompt(p.system_prompt); }}>
                                <Pencil className="h-3.5 w-3.5" />
                              </Button>
                              {!isActive && (
                                <Button size="sm" variant="outline" className="h-7" onClick={() => handleSetActive(p.id)}>
                                  <Check className="mr-1 h-3.5 w-3.5" /> Set Active
                                </Button>
                              )}
                            </div>
                          </div>
                          <p className="line-clamp-2 text-sm text-muted-foreground">{p.system_prompt}</p>
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
            </section>
          </div>
        </div>
      </div>
    </AdminGuard>
  );
}
