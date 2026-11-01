import { Link, Outlet } from "@tanstack/react-router";
import { MenuIcon, MoonIcon, SunIcon } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { ChatSessionProvider } from "@/features/chat/ChatSession";
import { HistorySidebar } from "@/features/chat/components/HistorySidebar";
import { currentTheme, saveTheme, type Theme } from "@/lib/theme";

function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(currentTheme);
  const next = theme === "dark" ? "light" : "dark";
  return (
    <Button
      size="icon-sm"
      variant="ghost"
      aria-label={`Switch to ${next} theme`}
      onClick={() => {
        saveTheme(next);
        setTheme(next);
      }}
    >
      {theme === "dark" ? <SunIcon /> : <MoonIcon />}
    </Button>
  );
}

function Brand() {
  return (
    <Link to="/" className="flex items-center gap-2 rounded-md font-semibold focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none">
      <img src="/logo.png" alt="" className="size-7" />
      GoldenGuide
    </Link>
  );
}

/** Desktop: history sidebar beside the chat. Phone: the sidebar becomes a drawer. */
export function AppLayout() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  return (
    <ChatSessionProvider>
      <a
        href="#main"
        className="sr-only z-50 rounded-md bg-background px-3 py-2 focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:ring-2 focus:ring-ring"
      >
        Skip to chat
      </a>
      <div className="flex h-full">
        <aside className="hidden w-72 shrink-0 flex-col border-r bg-sidebar md:flex">
          <div className="flex h-14 items-center px-4">
            <Brand />
          </div>
          <HistorySidebar />
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-14 shrink-0 items-center gap-2 border-b px-3 md:justify-end md:border-b-0">
            <Sheet open={drawerOpen} onOpenChange={setDrawerOpen}>
              <SheetTrigger asChild>
                <Button size="icon-sm" variant="ghost" className="md:hidden" aria-label="Open chat history">
                  <MenuIcon />
                </Button>
              </SheetTrigger>
              <SheetContent aria-describedby={undefined}>
                <SheetTitle className="sr-only">Chat history</SheetTitle>
                <div className="flex h-14 items-center px-4">
                  <Brand />
                </div>
                <HistorySidebar onNavigate={() => setDrawerOpen(false)} />
              </SheetContent>
            </Sheet>
            <div className="md:hidden">
              <Brand />
            </div>
            <div className="ml-auto">
              <ThemeToggle />
            </div>
          </header>
          <main id="main" className="min-h-0 flex-1">
            <Outlet />
          </main>
        </div>
      </div>
    </ChatSessionProvider>
  );
}
