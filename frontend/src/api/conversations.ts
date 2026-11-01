/** Server state for stored conversations (this browser's history), via TanStack Query. */
import { skipToken, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type Schemas, unwrap } from "./client";

export const conversationKeys = {
  all: ["conversations"] as const,
  list: () => [...conversationKeys.all, "list"] as const,
  messages: (conversationId: string) => [...conversationKeys.all, conversationId, "messages"] as const,
};

export function useConversations() {
  return useQuery({
    queryKey: conversationKeys.list(),
    queryFn: async () => unwrap(await api.GET("/api/v1/chat/conversations")),
  });
}

export function useConversationMessages(conversationId: string | null) {
  return useQuery({
    queryKey: conversationKeys.messages(conversationId ?? ""),
    queryFn:
      conversationId === null
        ? skipToken
        : async () =>
            unwrap(
              await api.GET("/api/v1/chat/conversations/{conversation_id}/messages", {
                params: { path: { conversation_id: conversationId } },
              }),
            ),
    // A 404 (another browser's or deleted conversation) will not succeed on retry.
    retry: false,
    // Turns asked on this page are shown live after the stored ones; a background refetch would
    // include them and show them twice. Opening the conversation again loads it fresh.
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
}

export function useDeleteConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (conversationId: string) =>
      unwrap(
        await api.DELETE("/api/v1/chat/conversations/{conversation_id}", {
          params: { path: { conversation_id: conversationId } },
        }),
      ),
    onSuccess: (_data, conversationId) => {
      queryClient.removeQueries({ queryKey: conversationKeys.messages(conversationId) });
      return queryClient.invalidateQueries({ queryKey: conversationKeys.list() });
    },
  });
}

export function useSubmitFeedback() {
  return useMutation({
    mutationFn: async ({ messageId, feedback }: { messageId: number; feedback: Schemas["FeedbackRequest"] }) =>
      unwrap(
        await api.PUT("/api/v1/chat/messages/{message_id}/feedback", {
          params: { path: { message_id: messageId } },
          body: feedback,
        }),
      ),
  });
}
