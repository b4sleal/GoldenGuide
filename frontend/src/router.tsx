import { createRootRoute, createRoute, createRouter, useParams } from "@tanstack/react-router";

import { AppLayout } from "@/components/AppLayout";
import { ChatPage } from "@/features/chat/components/ChatPage";

const rootRoute = createRootRoute({ component: AppLayout });

// Keep the composer mounted when the first response changes / into /c/<id>.
// Only the conversation parameter changes; focus and the layout transition survive navigation.
const chatRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "chat",
  component: function ChatRoute() {
    const { conversationId } = useParams({ strict: false });
    return <ChatPage conversationId={conversationId ?? null} />;
  },
});

const newChatRoute = createRoute({
  getParentRoute: () => chatRoute,
  path: "/",
});

const conversationRoute = createRoute({
  getParentRoute: () => chatRoute,
  path: "/c/$conversationId",
});

export const router = createRouter({
  routeTree: rootRoute.addChildren([chatRoute.addChildren([newChatRoute, conversationRoute])]),
  defaultNotFoundComponent: () => <p className="p-6 text-muted-foreground">Page not found.</p>,
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
