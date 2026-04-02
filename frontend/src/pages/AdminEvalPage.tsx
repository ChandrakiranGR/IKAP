import React from "react";
import { Navbar } from "@/components/Navbar";
import { AdminGuard } from "@/components/AdminGuard";
import { BarChart3, FlaskConical } from "lucide-react";

export default function AdminEvalPage() {
  return (
    <AdminGuard>
      <div className="min-h-screen bg-background">
        <Navbar />
        <div className="container py-8">
          <h1 className="mb-2 text-2xl font-bold text-foreground">Evaluation & Tuning</h1>
          <p className="mb-8 text-sm text-muted-foreground">Test and compare retrieval + prompt configurations</p>

          <div className="grid gap-6 md:grid-cols-2">
            <div className="rounded-lg border bg-card p-8 text-center">
              <FlaskConical className="mx-auto mb-4 h-12 w-12 text-muted-foreground/30" />
              <h3 className="mb-2 font-semibold text-foreground">Evaluation Questions</h3>
              <p className="text-sm text-muted-foreground">
                Create 30–50 test questions with expected key points to measure RAG quality.
              </p>
              <p className="mt-4 text-xs text-muted-foreground">Coming in next iteration</p>
            </div>
            <div className="rounded-lg border bg-card p-8 text-center">
              <BarChart3 className="mx-auto mb-4 h-12 w-12 text-muted-foreground/30" />
              <h3 className="mb-2 font-semibold text-foreground">A/B Comparison Dashboard</h3>
              <p className="text-sm text-muted-foreground">
                Compare prompt versions and retrieval configs side-by-side with scored results.
              </p>
              <p className="mt-4 text-xs text-muted-foreground">Coming in next iteration</p>
            </div>
          </div>
        </div>
      </div>
    </AdminGuard>
  );
}
