import React from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";

export function AdminGuard({ children }: { children: React.ReactNode }) {
  const { user, loading, isAdmin } = useAuth();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="flex items-center gap-2 text-muted-foreground">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          Loading...
        </div>
      </div>
    );
  }

  if (!user) return <Navigate to="/admin/login" replace />;
  
  if (!isAdmin) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="max-w-md rounded-lg border bg-card p-8 text-center">
          <div className="mb-4 text-4xl">🚫</div>
          <h2 className="mb-2 text-xl font-bold text-foreground">Access Denied</h2>
          <p className="mb-4 text-muted-foreground">
            Admin access is restricted to authorized accounts only.
          </p>
          <p className="text-sm text-muted-foreground">
            Logged in as: {user.email}
          </p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
