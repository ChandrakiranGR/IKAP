import React, { useEffect, useState } from "react";
import { Navbar } from "@/components/Navbar";
import { AdminGuard } from "@/components/AdminGuard";
import { supabase } from "@/integrations/supabase/client";
import { FileText, Trash2, RefreshCw, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

interface Article {
  id: string;
  title: string;
  article_id: string | null;
  category: string | null;
  tags: string[] | null;
  content_type: string;
  ingestion_status: string;
  created_at: string;
}

export default function AdminArticlesPage() {
  const [articles, setArticles] = useState<Article[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchArticles = async () => {
    setLoading(true);
    const { data, error } = await supabase
      .from("kb_articles")
      .select("id, title, article_id, category, tags, content_type, ingestion_status, created_at")
      .order("created_at", { ascending: false });
    if (error) {
      console.error(error);
      toast.error("Failed to load articles");
    } else {
      setArticles((data as Article[]) || []);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchArticles();
  }, []);

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this article and all its chunks?")) return;
    const { error } = await supabase.from("kb_articles").delete().eq("id", id);
    if (error) {
      toast.error("Failed to delete");
    } else {
      toast.success("Article deleted");
      fetchArticles();
    }
  };

  const handleDeleteAll = async () => {
    if (!confirm(`Delete ALL ${articles.length} articles and their chunks? This cannot be undone.`)) return;
    if (!confirm("Are you absolutely sure? This will remove all KB data.")) return;
    
    const { data, error } = await supabase.functions.invoke("admin-delete-articles", {
      body: { article_ids: null },
    });
    if (error) {
      toast.error("Failed to delete articles: " + (error.message || "Unknown error"));
    } else {
      toast.success("All articles deleted. You can now re-upload with the improved parser.");
      fetchArticles();
    }
  };

  return (
    <AdminGuard>
      <div className="min-h-screen bg-background">
        <Navbar />
        <div className="container py-8">
          <div className="mb-6 flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-foreground">KB Articles</h1>
              <p className="text-sm text-muted-foreground">{articles.length} articles ingested</p>
            </div>
            <div className="flex items-center gap-2">
              {articles.length > 0 && (
                <Button variant="destructive" size="sm" onClick={handleDeleteAll}>
                  <AlertTriangle className="mr-2 h-4 w-4" />
                  Delete All
                </Button>
              )}
              <Button variant="outline" size="sm" onClick={fetchArticles}>
                <RefreshCw className="mr-2 h-4 w-4" />
                Refresh
              </Button>
            </div>
          </div>

          <div className="rounded-lg border bg-card">
            {loading ? (
              <div className="p-8 text-center text-muted-foreground">Loading...</div>
            ) : articles.length === 0 ? (
              <div className="p-8 text-center">
                <FileText className="mx-auto mb-3 h-10 w-10 text-muted-foreground/30" />
                <p className="text-muted-foreground">No articles yet. Go to Ingest to add KB content.</p>
              </div>
            ) : (
              <table className="w-full">
                <thead>
                  <tr className="border-b text-left text-sm text-muted-foreground">
                    <th className="px-4 py-3 font-medium">Title</th>
                    <th className="px-4 py-3 font-medium">Article ID</th>
                    <th className="px-4 py-3 font-medium">Category</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                    <th className="px-4 py-3 font-medium">Type</th>
                    <th className="px-4 py-3 font-medium">Date</th>
                    <th className="px-4 py-3 font-medium" />
                  </tr>
                </thead>
                <tbody>
                  {articles.map((a) => (
                    <tr key={a.id} className="border-b last:border-0 hover:bg-muted/50">
                      <td className="px-4 py-3 text-sm font-medium text-foreground">{a.title}</td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">{a.article_id || "—"}</td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">{a.category || "—"}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${a.ingestion_status === "ok" ? "bg-green-100 text-green-700" : "bg-accent/20 text-accent"}`}>
                          {a.ingestion_status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">{a.content_type}</td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">
                        {new Date(a.created_at).toLocaleDateString()}
                      </td>
                      <td className="px-4 py-3">
                        <button onClick={() => handleDelete(a.id)} className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive">
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </AdminGuard>
  );
}
