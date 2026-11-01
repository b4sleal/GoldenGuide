import { createContext, use } from "react";

import type { ChatStream } from "./useChatStream";

export const ChatSessionContext = createContext<ChatStream | null>(null);

/** The live chat owned by ChatSessionProvider. */
export function useChatSession(): ChatStream {
  const chat = use(ChatSessionContext);
  if (!chat) throw new Error("useChatSession must be used inside ChatSessionProvider");
  return chat;
}
