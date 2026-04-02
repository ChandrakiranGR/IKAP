import React, { useState, useRef } from "react";
import { Navbar } from "@/components/Navbar";
import { AdminGuard } from "@/components/AdminGuard";
import { Button } from "@/components/ui/button";
import { supabase } from "@/integrations/supabase/client";
import { toast } from "sonner";
import { Upload, FileText, Loader2, CheckCircle, FileUp, FileJson, FileCode, Table } from "lucide-react";

interface ParsedArticle {
  title: string;
  article_id: string;
  category: string;
  tags: string;
  source_url: string;
  content: string;
  content_type: string;
}

function parseHTML(html: string): ParsedArticle {
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, "text/html");

  // Extract ServiceNow-specific metadata before stripping
  const snArticleId =
    doc.querySelector(".kb-number-info .ng-binding")?.textContent?.trim() ||
    doc.querySelector('meta[name="article-id"], meta[name="sys_id"], meta[name="number"]')?.getAttribute("content") || "";

  // Extract source URL from ServiceNow saved page comment
  let sourceUrl = "";
  const firstComment = html.match(/saved from url=\(\d+\)(https?:\/\/[^\s)]+)/);
  if (firstComment) sourceUrl = firstComment[1];

  // Extract category from breadcrumbs
  const breadcrumbLinks = doc.querySelectorAll(".breadcrumbs a, .ais-breadCrumbs a");
  const category = breadcrumbLinks.length > 0
    ? Array.from(breadcrumbLinks).map(a => a.textContent?.trim()).filter(Boolean).slice(-1)[0] || ""
    : "";

  // Remove all noise: scripts, styles, nav, footer, header, sidebars, ServiceNow chrome
  doc.querySelectorAll([
    "script", "style", "nav", "footer", "header", "aside", "noscript",
    ".nav", ".footer", ".header", ".sidebar",
    // ServiceNow-specific noise
    ".kb-end-buttons", ".kb-panel-heading", ".kb-number-info",
    ".kb-favorites-container", ".kb-comment-wrapper", ".kb-help-wrapper",
    ".title-secondary-data", ".breadcrumb-container", ".breadcrumbs",
    ".kb-permalink", ".str-rating", ".sp-stars", ".kb-rate-article",
    ".category-widget", ".dropdown-menu", ".global-footer",
    ".navbar", "[sn-atf-area='Article Favorites']",
    "[sn-atf-area='Knowledge Article Comments']",
    "[sn-atf-area='NU Knowledge Breadcrumbs']",
    "[sn-atf-area='Tech footer - top and global']",
    "img" // Remove image tags (they won't render in text anyway)
  ].join(", ")).forEach((el) => el.remove());

  // Try to extract title — prefer ServiceNow KB title
  const title =
    doc.querySelector(".kb-title-header")?.textContent?.trim() ||
    doc.querySelector("h1")?.textContent?.trim() ||
    doc.querySelector("title")?.textContent?.trim() ||
    "Untitled Article";

  // Target the actual article content — ServiceNow uses .kb-article-content or article tag
  const mainEl =
    doc.querySelector(".kb-article-content, article.kb-article-content, .kb-wrapper .kb-article-content") ||
    doc.querySelector("article, main, [role='main'], .article-body, .content-body, #content") ||
    doc.body;

  // Convert to readable text preserving structure
  const textContent = extractStructuredText(mainEl);

  return {
    title,
    article_id: snArticleId,
    category,
    tags: "",
    source_url: sourceUrl,
    content: textContent,
    content_type: "html",
  };
}

function extractStructuredText(el: Element): string {
  const lines: string[] = [];

  // Inline walker: returns inline text (for use inside paragraphs, list items, etc.)
  function inlineWalk(node: Node): string {
    if (node.nodeType === Node.TEXT_NODE) {
      return node.textContent?.replace(/\s+/g, " ") || "";
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return "";
    const elem = node as Element;
    const tag = elem.tagName.toLowerCase();

    // Convert <a> to Markdown link
    if (tag === "a") {
      const href = elem.getAttribute("href")?.trim();
      const text = Array.from(elem.childNodes).map(inlineWalk).join("").trim();
      if (href && text && !href.startsWith("#") && !href.startsWith("javascript:")) {
        return `[${text}](${href})`;
      }
      return text;
    }

    // Bold/strong
    if (tag === "strong" || tag === "b") {
      const text = Array.from(elem.childNodes).map(inlineWalk).join("").trim();
      return text ? `**${text}**` : "";
    }

    // Italic/em
    if (tag === "em" || tag === "i") {
      const text = Array.from(elem.childNodes).map(inlineWalk).join("").trim();
      return text ? `*${text}*` : "";
    }

    // Line breaks
    if (tag === "br") return "\n";

    // Skip images
    if (tag === "img") return "";

    return Array.from(elem.childNodes).map(inlineWalk).join("");
  }

  function walk(node: Node, depth = 0) {
    if (node.nodeType === Node.TEXT_NODE) {
      const text = node.textContent?.trim();
      if (text) lines.push(text);
      return;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    const tag = (node as Element).tagName.toLowerCase();

    // Add heading markers
    if (/^h[1-6]$/.test(tag)) {
      const text = (node as Element).textContent?.trim();
      if (text) {
        lines.push("");
        lines.push(text);
        lines.push("");
      }
      return;
    }

    // List items — use inlineWalk to preserve links
    if (tag === "li") {
      const text = inlineWalk(node).trim();
      if (text) {
        const parent = (node as Element).parentElement;
        const isOrdered = parent?.tagName.toLowerCase() === "ol";
        const index = Array.from(parent?.children || []).indexOf(node as Element) + 1;
        lines.push(isOrdered ? `${index}. ${text}` : `- ${text}`);
      }
      return;
    }

    // Paragraphs and divs — use inlineWalk for the whole block
    if (tag === "p" || tag === "div") {
      const text = inlineWalk(node).trim();
      if (text) {
        lines.push(text);
        lines.push("");
      }
      return;
    }

    // Table rows
    if (tag === "tr") {
      const cells = Array.from((node as Element).querySelectorAll("td, th"))
        .map((c) => inlineWalk(c).trim())
        .filter(Boolean);
      if (cells.length) lines.push(cells.join(" | "));
      return;
    }

    // Skip table wrapper, process children
    if (tag === "table" || tag === "tbody" || tag === "thead") {
      node.childNodes.forEach((child) => walk(child, depth + 1));
      lines.push("");
      return;
    }

    // Default: recurse
    node.childNodes.forEach((child) => walk(child, depth + 1));
  }

  walk(el);

  // Clean up excessive blank lines and filter noise
  const noisePatterns = [
    /^(\(\*\)|\( \))+$/,  // Star rating markers
    /^\d+% found this useful$/,
    /^Helpful\??$/i,
    /^Yes$/,
    /^No$/,
    /^Rate this article$/i,
    /^Created with Sketch\.?$/i,
    /^Copy Permalink$/i,
    /^Back to top$/i,
    /^Subscribe$/i,
    /^Flag Article$/i,
    /^Edit Article$/i,
    /^Save Favorite$/i,
    /^You have no favorites\.$/i,
    /^Article metadata\.?$/i,
    /^Revised by .+$/i,
    /^This article (was updated|has \d+ views|has average rating)/i,
    /^\d+\s*Views?$/i,
    /^\d+mo? ago$/,
    /^\d+ months? ago$/,
    /^BMP$/,
    /^Favorite Articles$/i,
  ];

  return lines
    .filter(line => {
      const trimmed = line.trim();
      if (!trimmed) return true; // keep blank lines for spacing
      return !noisePatterns.some(p => p.test(trimmed));
    })
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function parseJSON(jsonStr: string): ParsedArticle[] {
  const data = JSON.parse(jsonStr);

  // Handle array of articles
  const articles = Array.isArray(data) ? data : [data];

  return articles.map((item: any) => {
    // Flexible field mapping — try common field names
    const title =
      item.title || item.name || item.short_description || item.subject || "Untitled";
    const articleId =
      item.article_id || item.number || item.sys_id || item.id || "";
    const category =
      item.category || item.kb_category || item.type || "";
    const tags =
      (Array.isArray(item.tags) ? item.tags.join(", ") : item.tags) ||
      item.keywords ||
      "";
    const sourceUrl =
      item.source_url || item.url || item.link || "";

    // Handle structured sections format (from pre-processed KB articles)
    if (item.sections && Array.isArray(item.sections)) {
      const contentParts: string[] = [];
      for (const section of item.sections) {
        if (section.heading) {
          contentParts.push(`## ${section.heading}`);
        }
        if (section.steps && Array.isArray(section.steps)) {
          // Deduplicate steps (the pre-processed JSON has duplicates)
          const seen = new Set<string>();
          section.steps.forEach((step: string, i: number) => {
            if (!seen.has(step)) {
              seen.add(step);
              contentParts.push(`${i + 1}. ${step}`);
            }
          });
        }
        if (section.content) {
          contentParts.push(section.content);
        }
        if (section.text) {
          contentParts.push(section.text);
        }
        contentParts.push("");
      }
      return {
        title,
        article_id: String(articleId),
        category: String(category),
        tags: String(tags),
        source_url: String(sourceUrl),
        content: contentParts.join("\n").trim(),
        content_type: "json",
      };
    }

    // Content: try multiple field names
    const content =
      item.content ||
      item.text ||
      item.body ||
      item.kb_content ||
      item.article_body ||
      item.description ||
      item.raw_text ||
      "";

    // If content is HTML, strip tags
    let cleanContent = content;
    if (/<[^>]+>/.test(content)) {
      const parsed = parseHTML(content);
      cleanContent = parsed.content;
    }

    return {
      title,
      article_id: String(articleId),
      category: String(category),
      tags: String(tags),
      source_url: String(sourceUrl),
      content: cleanContent,
      content_type: "json",
    };
  });
}

// CSV parsing for incident data
function parseCSVRow(row: string): string[] {
  const result: string[] = [];
  let current = "";
  let inQuotes = false;
  for (let i = 0; i < row.length; i++) {
    const ch = row[i];
    if (inQuotes) {
      if (ch === '"' && row[i + 1] === '"') { current += '"'; i++; }
      else if (ch === '"') { inQuotes = false; }
      else { current += ch; }
    } else {
      if (ch === '"') { inQuotes = true; }
      else if (ch === ',') { result.push(current); current = ""; }
      else { current += ch; }
    }
  }
  result.push(current);
  return result;
}

function parseCSV(text: string): Record<string, string>[] {
  const lines = text.split(/\r?\n/).filter(l => l.trim());
  if (lines.length < 2) return [];
  const headers = parseCSVRow(lines[0]).map(h => h.trim().toLowerCase());
  return lines.slice(1).map(line => {
    const values = parseCSVRow(line);
    const obj: Record<string, string> = {};
    headers.forEach((h, i) => { obj[h] = (values[i] || "").trim(); });
    return obj;
  });
}

function createIncidentArticle(row: Record<string, string>): ParsedArticle {
  const shortDesc = row["short_description"] || "Untitled Incident";
  const parts: string[] = [`# ${shortDesc}`];

  if (row["description"]) {
    parts.push("", "## Problem Description", row["description"]);
  }
  if (row["work_notes"]) {
    parts.push("", "## Work Notes", row["work_notes"]);
  }
  if (row["comments_and_work_notes"] && row["comments_and_work_notes"] !== row["work_notes"]) {
    parts.push("", "## Comments and Work Notes", row["comments_and_work_notes"]);
  }
  if (row["close_notes"]) {
    parts.push("", "## Resolution", row["close_notes"]);
  }
  if (row["comments"] && row["comments"] !== row["comments_and_work_notes"]) {
    parts.push("", "## Additional Comments", row["comments"]);
  }

  const tags: string[] = [];
  if (row["u_application_service"]) tags.push(row["u_application_service"]);
  if (row["state"]) tags.push(`state:${row["state"]}`);

  return {
    title: shortDesc,
    article_id: "",
    category: row["business_service"] || "",
    tags: tags.join(", "),
    source_url: "",
    content: parts.join("\n"),
    content_type: "csv_incident",
  };
}

export default function AdminIngestPage() {
  const [title, setTitle] = useState("");
  const [articleId, setArticleId] = useState("");
  const [category, setCategory] = useState("");
  const [tags, setTags] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ chunks: number; warnings: string[] } | null>(null);
  const [batchResults, setBatchResults] = useState<{ title: string; chunks: number; status: string }[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [activeTab, setActiveTab] = useState<"paste" | "upload">("paste");

  const handleIngest = async (article?: ParsedArticle) => {
    const t = article?.title || title.trim();
    const c = article?.content || content.trim();
    if (!t || !c) {
      toast.error("Title and content are required.");
      return null;
    }

    const { data, error } = await supabase.functions.invoke("ingest", {
      body: {
        title: t,
        article_id: (article?.article_id || articleId).trim() || undefined,
        category: (article?.category || category).trim() || undefined,
        tags: (article?.tags || tags).split(",").map((t) => t.trim()).filter(Boolean),
        source_url: (article?.source_url || sourceUrl).trim() || undefined,
        content: c,
        content_type: article?.content_type || "pasted_text",
      },
    });
    if (error) throw error;
    return data;
  };

  const handleSingleIngest = async () => {
    setLoading(true);
    setResult(null);
    try {
      const data = await handleIngest();
      if (data) {
        setResult({ chunks: data.chunks_created || 0, warnings: data.warnings || [] });
        toast.success(`Article ingested: ${data.chunks_created} chunks created`);
        setTitle("");
        setArticleId("");
        setCategory("");
        setTags("");
        setSourceUrl("");
        setContent("");
      }
    } catch (err) {
      console.error(err);
      toast.error("Ingestion failed.");
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files?.length) return;

    setLoading(true);
    setBatchResults([]);
    const results: { title: string; chunks: number; status: string }[] = [];

    for (const file of Array.from(files)) {
      try {
        const text = await file.text();
        const ext = file.name.toLowerCase().split(".").pop();

        let articles: ParsedArticle[] = [];

        if (ext === "csv") {
          const rows = parseCSV(text);
          articles = rows
            .filter(r => r["short_description"]?.trim())
            .map(createIncidentArticle);
        } else if (ext === "json") {
          articles = parseJSON(text);
        } else if (ext === "html" || ext === "htm") {
          articles = [parseHTML(text)];
        } else {
          articles = [{
            title: file.name.replace(/\.[^.]+$/, ""),
            article_id: "",
            category: "",
            tags: "",
            source_url: "",
            content: text,
            content_type: "pasted_text",
          }];
        }

        for (const article of articles) {
          if (!article.content.trim()) {
            results.push({ title: article.title, chunks: 0, status: "empty_content" });
            continue;
          }
          try {
            const data = await handleIngest(article);
            results.push({
              title: article.title,
              chunks: data?.chunks_created || 0,
              status: "ok",
            });
          } catch (err) {
            console.error("Ingest error for:", article.title, err);
            results.push({ title: article.title, chunks: 0, status: "error" });
          }
        }
      } catch (err) {
        console.error("File parse error:", file.name, err);
        results.push({ title: file.name, chunks: 0, status: "parse_error" });
      }
    }

    setBatchResults(results);
    const successCount = results.filter((r) => r.status === "ok").length;
    const totalChunks = results.reduce((sum, r) => sum + r.chunks, 0);
    toast.success(`Ingested ${successCount} article(s), ${totalChunks} total chunks`);
    setLoading(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleLoadSample = () => {
    setActiveTab("paste");
    setTitle("How to Enroll in Duo MFA");
    setArticleId("KB0012345");
    setCategory("Security");
    setTags("MFA, Duo, Enrollment, Security");
    setSourceUrl("https://service.northeastern.edu/tech?id=kb_article&sys_id=duo_mfa");
    setContent(`How to Enroll in Duo Multi-Factor Authentication (MFA)

Overview
Duo MFA adds an extra layer of security to your Northeastern account. All faculty, staff, and students must enroll in Duo to access university services.

Requirements
- A smartphone (iOS or Android) with the Duo Mobile app, OR
- A hardware token (available from the IT Help Desk)
- Your Northeastern username and password

Step-by-Step Enrollment

Step 1: Go to the Duo Enrollment Portal
Navigate to https://duo.northeastern.edu and sign in with your Northeastern credentials.

Step 2: Choose Your Device
Select "Mobile phone" or "Tablet" as your device type. Enter your phone number if prompted.

Step 3: Install Duo Mobile
Download and install the Duo Mobile app from the App Store (iOS) or Google Play Store (Android).

Step 4: Activate Duo Mobile
Open the Duo Mobile app and scan the QR code displayed on your screen. The app will automatically link to your Northeastern account.

Step 5: Verify Enrollment
Click "Send Me a Push" to verify your enrollment. Approve the push notification on your phone.

Troubleshooting
- If you don't receive a push notification, ensure your phone has an internet connection.
- If you lost your phone, contact the IT Help Desk at 617-373-4357 to get a temporary bypass code.
- Hardware tokens can be requested at the IT Help Desk in Snell Library.

Warning: Never share your Duo bypass codes with anyone. IT staff will never ask for your bypass codes.

For additional help, contact the IT Service Desk:
- Phone: 617-373-4357
- Email: help@northeastern.edu
- ServiceNow: https://service.northeastern.edu`);
  };

  const tabClass = (tab: string) =>
    `px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
      activeTab === tab
        ? "bg-card text-foreground border border-b-0"
        : "text-muted-foreground hover:text-foreground"
    }`;

  return (
    <AdminGuard>
      <div className="min-h-screen bg-background">
        <Navbar />
        <div className="container max-w-3xl py-8">
          <div className="mb-6 flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-foreground">Ingest KB Article</h1>
              <p className="text-sm text-muted-foreground">Add knowledge base content for IKAP retrieval</p>
            </div>
            <Button variant="outline" size="sm" onClick={handleLoadSample}>
              <FileText className="mr-2 h-4 w-4" />
              Load Sample KB
            </Button>
          </div>

          {/* Tabs */}
          <div className="flex gap-1 mb-0">
            <button className={tabClass("paste")} onClick={() => setActiveTab("paste")}>
              <span className="flex items-center gap-1.5">
                <FileText className="h-4 w-4" /> Paste Text
              </span>
            </button>
            <button className={tabClass("upload")} onClick={() => setActiveTab("upload")}>
              <span className="flex items-center gap-1.5">
                <FileUp className="h-4 w-4" /> Upload Files
              </span>
            </button>
          </div>

          {activeTab === "paste" && (
            <div className="space-y-4 rounded-lg rounded-tl-none border bg-card p-6">
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">Title *</label>
                  <input value={title} onChange={(e) => setTitle(e.target.value)} className="w-full rounded-md border bg-background px-3 py-2 text-sm text-foreground" placeholder="Article title" />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">Article ID</label>
                  <input value={articleId} onChange={(e) => setArticleId(e.target.value)} className="w-full rounded-md border bg-background px-3 py-2 text-sm text-foreground" placeholder="KB0012345" />
                </div>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">Category</label>
                  <input value={category} onChange={(e) => setCategory(e.target.value)} className="w-full rounded-md border bg-background px-3 py-2 text-sm text-foreground" placeholder="e.g. Security, Network" />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-foreground">Tags (comma-separated)</label>
                  <input value={tags} onChange={(e) => setTags(e.target.value)} className="w-full rounded-md border bg-background px-3 py-2 text-sm text-foreground" placeholder="MFA, Duo, Security" />
                </div>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">Source URL</label>
                <input value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} className="w-full rounded-md border bg-background px-3 py-2 text-sm text-foreground" placeholder="https://..." />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">KB Content *</label>
                <textarea value={content} onChange={(e) => setContent(e.target.value)} rows={12} className="w-full rounded-md border bg-background px-3 py-2 text-sm text-foreground font-mono" placeholder="Paste your KB article content here..." />
              </div>

              <div className="flex items-center gap-4">
                <Button onClick={handleSingleIngest} disabled={loading}>
                  {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Upload className="mr-2 h-4 w-4" />}
                  Ingest Article
                </Button>
                {result && (
                  <div className="flex items-center gap-2 text-sm">
                    <CheckCircle className="h-4 w-4 text-green-600" />
                    <span className="text-foreground">{result.chunks} chunks created</span>
                    {result.warnings.length > 0 && (
                      <span className="text-accent">({result.warnings.join(", ")})</span>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === "upload" && (
            <div className="space-y-4 rounded-lg rounded-tl-none border bg-card p-6">
              <div className="rounded-lg border-2 border-dashed border-border p-8 text-center">
                <FileUp className="mx-auto mb-3 h-10 w-10 text-muted-foreground/40" />
                <h3 className="mb-1 font-semibold text-foreground">Upload KB Files</h3>
                <p className="mb-4 text-sm text-muted-foreground">
                  Supports <strong>.html</strong>, <strong>.json</strong>, <strong>.csv</strong>, and <strong>.txt</strong> files. CSV files with incident data are auto-parsed.
                </p>

                <div className="mb-4 rounded-lg bg-muted p-3 text-left text-xs text-muted-foreground">
                  <p className="mb-2 font-medium text-foreground">Supported JSON formats:</p>
                  <div className="grid gap-2 md:grid-cols-2">
                    <div>
                      <p className="font-medium">Single article:</p>
                      <pre className="mt-1 overflow-x-auto rounded bg-background p-2">
{`{
  "title": "...",
  "content": "...",
  "article_id": "KB001",
  "category": "Security"
}`}
                      </pre>
                    </div>
                    <div>
                      <p className="font-medium">Array of articles:</p>
                      <pre className="mt-1 overflow-x-auto rounded bg-background p-2">
{`[
  { "title": "...", "body": "..." },
  { "name": "...", "text": "..." }
]`}
                      </pre>
                    </div>
                  </div>
                  <p className="mt-2">
                    <span className="flex flex-wrap gap-1">
                      <span className="inline-flex items-center gap-1"><FileJson className="h-3 w-3" /> Fields auto-detected:</span>
                      <code>title/name/short_description</code>,
                      <code>content/body/text/description</code>,
                      <code>article_id/number/sys_id</code>,
                      <code>category</code>, <code>tags/keywords</code>,
                      <code>source_url/url/link</code>
                    </span>
                  </p>
                </div>

                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".html,.htm,.json,.txt,.csv"
                  multiple
                  onChange={handleFileUpload}
                  className="hidden"
                  id="file-upload"
                />
                <Button onClick={() => fileInputRef.current?.click()} disabled={loading}>
                  {loading ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <FileUp className="mr-2 h-4 w-4" />
                  )}
                  {loading ? "Processing..." : "Select Files"}
                </Button>
              </div>

              {/* Batch results */}
              {batchResults.length > 0 && (
                <div className="rounded-lg border bg-background p-4">
                  <h3 className="mb-3 font-semibold text-foreground">
                    Ingestion Results ({batchResults.filter((r) => r.status === "ok").length}/{batchResults.length} succeeded)
                  </h3>
                  <div className="max-h-64 space-y-2 overflow-y-auto">
                    {batchResults.map((r, i) => (
                      <div key={i} className="flex items-center justify-between rounded border px-3 py-2 text-sm">
                        <span className="truncate text-foreground">{r.title}</span>
                        <span className="ml-2 shrink-0">
                          {r.status === "ok" ? (
                            <span className="flex items-center gap-1 text-green-600">
                              <CheckCircle className="h-3.5 w-3.5" />
                              {r.chunks} chunks
                            </span>
                          ) : (
                            <span className="text-destructive">{r.status}</span>
                          )}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </AdminGuard>
  );
}
