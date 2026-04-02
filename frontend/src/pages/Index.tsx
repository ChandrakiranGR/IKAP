import { Link } from "react-router-dom";
import { AlertTriangle, BookOpen, MessageSquare, Shield } from "lucide-react";

import { Navbar } from "@/components/Navbar";
import { Button } from "@/components/ui/button";

const Index = () => {
  return (
    <div className="min-h-screen bg-background">
      <Navbar />

      <section className="relative overflow-hidden">
        <div className="neu-gradient absolute inset-0 opacity-5" />
        <div className="container relative py-24 md:py-32">
          <div className="mx-auto max-w-3xl text-center">
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border bg-card px-4 py-1.5 text-sm text-muted-foreground">
              <Shield className="h-4 w-4 text-primary" />
              KB-grounded Northeastern IT assistant
            </div>
            <h1 className="mb-6 text-4xl font-extrabold tracking-tight text-foreground md:text-6xl">
              Intelligent Knowledge
              <span className="block text-primary">Assistant Platform</span>
            </h1>
            <p className="mb-8 text-lg text-muted-foreground md:text-xl">
              Ask Northeastern IT questions in plain language and get step-by-step,
              source-backed answers from the cleaned KB corpus.
            </p>
            <div className="flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
              <Link to="/chat">
                <Button size="lg" className="gap-2 text-base">
                  <MessageSquare className="h-5 w-5" />
                  Open IKAP Chat
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </section>

      <section className="border-t bg-card py-20">
        <div className="container">
          <div className="mx-auto grid max-w-4xl gap-8 md:grid-cols-3">
            <div className="text-center">
              <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10">
                <BookOpen className="h-6 w-6 text-primary" />
              </div>
              <h3 className="mb-2 font-semibold text-foreground">Citation-Backed Answers</h3>
              <p className="text-sm text-muted-foreground">
                Every response is grounded in Northeastern KB content with article links and source snippets.
              </p>
            </div>
            <div className="text-center">
              <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10">
                <MessageSquare className="h-6 w-6 text-primary" />
              </div>
              <h3 className="mb-2 font-semibold text-foreground">Step-by-Step Help</h3>
              <p className="text-sm text-muted-foreground">
                Ask about MFA, VPN, Canvas, software, Student Hub, or account access in natural language.
              </p>
            </div>
            <div className="text-center">
              <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10">
                <Shield className="h-6 w-6 text-primary" />
              </div>
              <h3 className="mb-2 font-semibold text-foreground">Safer Responses</h3>
              <p className="text-sm text-muted-foreground">
                The assistant refuses unsafe requests and keeps answers aligned to approved KB guidance.
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="border-t py-8">
        <div className="container">
          <div className="mx-auto flex max-w-2xl items-start gap-3 rounded-lg border bg-card p-4">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-accent" />
            <p className="text-sm text-muted-foreground">
              <strong>Disclaimer:</strong> IKAP answers are grounded in the available KB articles.
              For urgent or account-specific issues, contact Northeastern IT Support directly.
            </p>
          </div>
        </div>
      </section>

      <footer className="border-t py-6">
        <div className="container text-center text-sm text-muted-foreground">
          © {new Date().getFullYear()} IKAP — Northeastern University IT
        </div>
      </footer>
    </div>
  );
};

export default Index;
