import { Link, useLocation } from "react-router-dom";
import { MessageSquare, Shield } from "lucide-react";

import { Button } from "@/components/ui/button";

export function Navbar() {
  const location = useLocation();
  const onChatPage = location.pathname === "/chat";

  return (
    <header className="sticky top-0 z-50 border-b border-border bg-foreground">
      <div className="container flex h-16 items-center justify-between">
        <Link to="/" className="flex items-center gap-2">
          <Shield className="h-7 w-7 text-primary" />
          <span className="text-xl font-bold tracking-tight text-primary-foreground">IKAP</span>
        </Link>

        <nav className="flex items-center gap-3">
          {onChatPage ? (
            <Link to="/">
              <Button
                variant="ghost"
                size="sm"
                className="text-primary-foreground hover:bg-primary-foreground/10"
              >
                Home
              </Button>
            </Link>
          ) : (
            <Link to="/chat">
              <Button
                variant="ghost"
                size="sm"
                className="text-primary-foreground hover:bg-primary-foreground/10"
              >
                <MessageSquare className="mr-1.5 h-4 w-4" />
                Chat
              </Button>
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}
