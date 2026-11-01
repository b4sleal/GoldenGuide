import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { MessageSquarePlusIcon, Trash2Icon } from "lucide-react";
import { useState } from "react";

import { useConversations, useDeleteConversation } from "@/api/conversations";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const UNTITLED = "Untitled chat";

/** This browser's conversations, newest activity first, with "new chat" and delete. */
export function HistorySidebar({ onNavigate }: { onNavigate?: () => void }) {
  const conversations = useConversations();
  const remove = useDeleteConversation();
  const navigate = useNavigate();
  const { conversationId: activeId } = useParams({ strict: false });
  // Delete takes two clicks: the first arms it, so a stray click cannot erase a conversation.
  const [armed, setArmed] = useState<string | null>(null);

  function confirmDelete(conversationId: string) {
    remove.mutate(conversationId, {
      onSuccess: () => {
        setArmed(null);
        if (conversationId === activeId) void navigate({ to: "/" });
      },
    });
  }

  return (
    <nav aria-label="Chat history" className="flex h-full flex-col gap-3 p-3">
      <Button asChild variant="outline" className="justify-start">
        <Link to="/" onClick={onNavigate}>
          <MessageSquarePlusIcon /> New chat
        </Link>
      </Button>

      <h2 className="px-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">Recent</h2>

      <div className="-mx-1 min-h-0 flex-1 overflow-y-auto px-1">
        {conversations.isPending ? (
          <ul aria-label="Loading chats" className="space-y-2">
            {Array.from({ length: 6 }, (_, index) => (
              <li key={index} className="animate-gg-pulse h-8 rounded-md bg-muted" />
            ))}
          </ul>
        ) : conversations.isError ? (
          <p className="px-2 text-sm text-muted-foreground">Chat history could not be loaded.</p>
        ) : conversations.data.length === 0 ? (
          <p className="px-2 text-sm text-muted-foreground">Your chats on this device will appear here.</p>
        ) : (
          <ul className="space-y-0.5">
            {conversations.data.map((conversation) => {
              const title = conversation.title ?? UNTITLED;
              return (
                <li key={conversation.id} className="group relative">
                  <Link
                    to="/c/$conversationId"
                    params={{ conversationId: conversation.id }}
                    onClick={onNavigate}
                    className={cn(
                      "block truncate rounded-md py-1.5 pr-9 pl-2 text-sm hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                      conversation.id === activeId && "bg-secondary font-medium text-secondary-foreground",
                    )}
                    title={title}
                  >
                    {title}
                  </Link>
                  <Button
                    size="icon-sm"
                    variant={armed === conversation.id ? "destructive" : "ghost"}
                    aria-label={armed === conversation.id ? `Confirm delete "${title}"` : `Delete "${title}"`}
                    disabled={remove.isPending}
                    onClick={() => (armed === conversation.id ? confirmDelete(conversation.id) : setArmed(conversation.id))}
                    onBlur={() => setArmed((current) => (current === conversation.id ? null : current))}
                    className={cn(
                      "absolute top-0.5 right-0.5 size-7 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 [@media(hover:none)]:opacity-100",
                      armed === conversation.id && "opacity-100",
                    )}
                  >
                    <Trash2Icon />
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      {remove.isError && (
        <p role="alert" className="px-2 text-sm text-destructive">
          The chat could not be deleted.
        </p>
      )}
    </nav>
  );
}
