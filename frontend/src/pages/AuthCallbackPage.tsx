import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { supabase } from "@/integrations/supabase/client";
import { Loader2 } from "lucide-react";

export default function AuthCallbackPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  const nextPath = useMemo(() => searchParams.get("next") || "/admin/ingest", [searchParams]);

  useEffect(() => {
    const completeAuth = async () => {
      try {
        const url = new URL(window.location.href);
        const hashParams = new URLSearchParams(url.hash.replace(/^#/, ""));

        const code = searchParams.get("code");
        const tokenHash = searchParams.get("token_hash") || hashParams.get("token_hash");
        const accessToken = hashParams.get("access_token");
        const refreshToken = hashParams.get("refresh_token");
        const type = (searchParams.get("type") || hashParams.get("type") || "magiclink") as
          | "signup"
          | "invite"
          | "magiclink"
          | "recovery"
          | "email_change"
          | "email";

        if (code) {
          const { error } = await supabase.auth.exchangeCodeForSession(code);
          if (error) throw error;
        } else if (tokenHash) {
          const { error } = await supabase.auth.verifyOtp({ type, token_hash: tokenHash });
          if (error) throw error;
        } else if (accessToken && refreshToken) {
          const { error } = await supabase.auth.setSession({
            access_token: accessToken,
            refresh_token: refreshToken,
          });
          if (error) throw error;
        } else {
          throw new Error("Missing auth token in callback URL.");
        }

        // allow auth state to settle before entering guarded routes
        await supabase.auth.getSession();
        navigate(nextPath, { replace: true });
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to complete sign in.");
      }
    };

    completeAuth();
  }, [navigate, nextPath, searchParams]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-md rounded-lg border bg-card p-6 text-center">
        <Loader2 className="mx-auto mb-3 h-6 w-6 animate-spin text-primary" />
        <h1 className="mb-1 text-lg font-semibold text-foreground">Completing sign in…</h1>
        <p className="text-sm text-muted-foreground">
          {error ?? "Please wait while we verify your magic link."}
        </p>
      </div>
    </div>
  );
}
