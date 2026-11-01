import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import type { ReactNode } from "react";

import { conversationKeys } from "@/api/conversations";

import { ChatSessionContext } from "./chatSessionContext";
import { useChatStream } from "./useChatStream";

/**
 * Owns the live chat above the routes, so the first answer of a new chat keeps streaming when the
 * URL changes from `/` to `/c/<id>`.
 */
export function ChatSessionProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const chat = useChatStream({
    onConversationCreated: (conversationId) => {
      void navigate({ to: "/c/$conversationId", params: { conversationId }, replace: true });
      void queryClient.invalidateQueries({ queryKey: conversationKeys.list() });
    },
    onTurnSettled: () => {
      // Order and "last active" change after every turn. Stored messages are not refetched here:
      // live turns are already on screen with their sources, which history does not return.
      void queryClient.invalidateQueries({ queryKey: conversationKeys.list() });
    },
  });
  return <ChatSessionContext value={chat}>{children}</ChatSessionContext>;
}
