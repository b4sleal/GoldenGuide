import { useEffect, useRef } from "react";

import { ApiError } from "@/api/client";
import { useConversationMessages } from "@/api/conversations";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { useChatSession } from "../chatSessionContext";
import { STORED_STATUS_NOTICES, SUGGESTED_QUESTIONS } from "../labels";
import { storedAnswerContent } from "../stream/history";
import { AnswerActions } from "./AnswerActions";
import { AnswerBlocks } from "./AnswerBlocks";
import { AnswerView } from "./AnswerView";
import { Composer } from "./Composer";
import { Notice } from "./Notice";
import { SourceList } from "./SourceList";

function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <p className="max-w-[85%] rounded-2xl rounded-br-md bg-primary px-4 py-2 whitespace-pre-wrap text-primary-foreground">
        {text}
      </p>
    </div>
  );
}

function StoredHistory({ conversationId }: { conversationId: string }) {
  const messages = useConversationMessages(conversationId);

  if (messages.isPending) {
    return (
      <div aria-label="Loading conversation" className="space-y-6">
        {[0, 1].map((key) => (
          <div key={key} className="space-y-3">
            <div className="animate-gg-pulse ml-auto h-9 w-1/2 rounded-2xl bg-muted" />
            <div className="animate-gg-pulse h-20 rounded-lg bg-muted" />
          </div>
        ))}
      </div>
    );
  }
  if (messages.isError) {
    const missing = messages.error instanceof ApiError && messages.error.status === 404;
    return (
      <Notice
        message={missing ? "This chat doesn't exist on this device. It may have been deleted." : "This chat could not be loaded."}
        onRetry={missing ? undefined : () => void messages.refetch()}
      />
    );
  }

  return messages.data.map((message) => {
    if (message.role === "user") return <UserBubble key={message.id} text={message.content} />;
    const notice = STORED_STATUS_NOTICES[message.status];
    const answer = storedAnswerContent(message);
    return (
      <article key={message.id} aria-label="GoldenGuide answer" className="space-y-3">
        {answer.blocks.length > 0 && (
          <div className="answer-prose">
            <AnswerBlocks blocks={answer.blocks} />
          </div>
        )}
        {notice && <Notice message={notice} />}
        <SourceList sources={answer.sources} />
        <AnswerActions messageId={message.id} blocks={answer.blocks} sources={answer.sources} />
      </article>
    );
  });
}

function EmptyState() {
  return (
    <div className="flex flex-1 flex-col items-center justify-end gap-4 text-center">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold">What can I help you find?</h1>
        <p className="text-muted-foreground">Answers come from official Laurier sources, with links to check them.</p>
      </div>
    </div>
  );
}

function SuggestedQuestions({ onAsk }: { onAsk: (question: string) => void }) {
  return (
    <ul className="mx-auto grid w-full max-w-xl gap-2 px-4 pb-4 sm:grid-cols-2">
      {SUGGESTED_QUESTIONS.map((question) => (
        <li key={question}>
          <Button variant="outline" className="h-auto w-full justify-start py-2.5 text-left whitespace-normal" onClick={() => onAsk(question)}>
            {question}
          </Button>
        </li>
      ))}
    </ul>
  );
}

/** One conversation (or a new chat when `conversationId` is null): stored history, then live turns. */
export function ChatPage({ conversationId }: { conversationId: string | null }) {
  const chat = useChatSession();
  const { reset, turns } = chat;
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => reset(conversationId), [conversationId, reset]);

  // Keep the newest content in view while it streams.
  const lastAnswer = turns.at(-1)?.answer;
  useEffect(() => {
    const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
    end.current?.scrollIntoView({ block: "end", behavior: reducedMotion ? "instant" : "smooth" });
  }, [turns.length, lastAnswer]);

  // A conversation started on this page has no history beyond its live turns: loading it would
  // show the first question twice.
  const showStored = conversationId !== null && !(chat.conversationId === conversationId && chat.startedHere);
  const empty = conversationId === null && turns.length === 0;

  return (
    <div className={cn("chat-layout h-full", empty && "chat-layout-empty")}>
      <div className="min-h-0 overflow-y-auto">
        <div className="mx-auto flex min-h-full max-w-3xl flex-col gap-6 px-4 py-6">
          {empty ? (
            <EmptyState />
          ) : (
            <>
              {showStored && <StoredHistory conversationId={conversationId} />}
              {turns.map((turn, index) => (
                <div key={turn.id} className="animate-in fade-in space-y-4">
                  <UserBubble text={turn.question} />
                  <article aria-label="GoldenGuide answer">
                    <AnswerView
                      answer={turn.answer}
                      onRetry={index === turns.length - 1 && !chat.isStreaming ? () => chat.retry(turn.id) : undefined}
                    />
                  </article>
                </div>
              ))}
            </>
          )}
          <div ref={end} />
        </div>
      </div>
      <div className="mx-auto w-full max-w-3xl px-4 pb-4">
        <Composer
          streaming={chat.isStreaming}
          onSend={chat.send}
          onStop={chat.stop}
          conversationId={chat.conversationId}
          preserveDraft={chat.startedHere}
        />
        <p className="mt-2 text-center text-xs text-muted-foreground">
          GoldenGuide can make mistakes. Check important details on the linked Laurier pages.
        </p>
      </div>
      {/* Suggestions sit below the centered input, leaving room for the welcome text on small screens. */}
      <div className="min-h-0 overflow-y-auto">
        {empty && <SuggestedQuestions onAsk={chat.send} />}
      </div>
    </div>
  );
}
