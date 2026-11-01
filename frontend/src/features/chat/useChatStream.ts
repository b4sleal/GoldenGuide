import { useCallback, useEffect, useReducer, useRef } from "react";

import {
  type Answer,
  applyEvent,
  endWithoutTerminal,
  failBeforeStream,
  isFinished,
  pendingAnswer,
} from "./stream/answer";
import type { StreamEvent } from "./stream/events";
import { type StreamEnd, streamChat } from "./stream/streamChat";

/** A question asked in this page session, with its live answer. */
export interface LiveTurn {
  id: string;
  question: string;
  answer: Answer;
}

interface State {
  conversationId: string | null;
  /** The server created this conversation for a question asked here, so all of it is in `turns`. */
  startedHere: boolean;
  turns: LiveTurn[];
}

const initialState: State = { conversationId: null, startedHere: false, turns: [] };

type Action =
  | { type: "reset"; conversationId: string | null }
  | { type: "ask"; turn: LiveTurn }
  | { type: "retry"; turnId: string }
  | { type: "conversation"; conversationId: string }
  | { type: "event"; turnId: string; event: StreamEvent }
  | { type: "end"; turnId: string; end: StreamEnd };

function finish(answer: Answer, end: StreamEnd): Answer {
  switch (end.kind) {
    case "ended":
      return endWithoutTerminal(answer, false);
    case "aborted":
      return endWithoutTerminal(answer, true);
    case "failed":
      return isFinished(answer) ? answer : failBeforeStream(answer, end.error);
  }
}

function updateTurn(state: State, turnId: string, update: (answer: Answer) => Answer): State {
  return { ...state, turns: state.turns.map((t) => (t.id === turnId ? { ...t, answer: update(t.answer) } : t)) };
}

export function chatReducer(state: State, action: Action): State {
  switch (action.type) {
    case "reset":
      return { ...initialState, conversationId: action.conversationId };
    case "ask":
      return { ...state, turns: [...state.turns, action.turn] };
    case "retry":
      return updateTurn(state, action.turnId, () => pendingAnswer);
    case "conversation":
      return { ...state, conversationId: action.conversationId, startedHere: true };
    case "event":
      return updateTurn(state, action.turnId, (answer) => applyEvent(answer, action.event));
    case "end":
      return updateTurn(state, action.turnId, (answer) => finish(answer, action.end));
  }
}

export interface ChatStreamCallbacks {
  /** The server created a conversation for a new chat (first answer of a new chat). */
  onConversationCreated?: (conversationId: string) => void;
  /** A turn ended in any way; stored history and the conversation list may have changed. */
  onTurnSettled?: (conversationId: string | null) => void;
}

/**
 * Ask questions and stream their answers. One answer streams at a time; `stop` aborts it.
 * State survives route changes because the owner (ChatSessionProvider) sits above the router outlet.
 */
export function useChatStream(callbacks: ChatStreamCallbacks = {}) {
  const [state, dispatch] = useReducer(chatReducer, initialState);
  const controller = useRef<AbortController | null>(null);
  // Updated synchronously (not on render): navigation to a new conversation's URL can render before
  // the reducer state does, and `reset` must recognize the conversation it just created.
  const conversationRef = useRef<string | null>(null);
  // Read through a ref so async stream code always sees the latest values without re-subscribing.
  const latest = useRef({ state, callbacks });
  useEffect(() => {
    latest.current = { state, callbacks };
  });

  const run = useCallback(async (turnId: string, question: string) => {
    // Set synchronously, so a second click before the next render is ignored by `send`.
    const abort = new AbortController();
    controller.current = abort;
    let conversationId = conversationRef.current;

    const end = await streamChat(
      { query: question, conversation_id: conversationId },
      {
        onConversation: (id) => {
          // An aborted request may belong to a conversation the student already left.
          if (id === conversationId || abort.signal.aborted) return;
          conversationId = id;
          conversationRef.current = id;
          dispatch({ type: "conversation", conversationId: id });
          latest.current.callbacks.onConversationCreated?.(id);
        },
        onEvent: (event) => dispatch({ type: "event", turnId, event }),
      },
      abort.signal,
    );

    dispatch({ type: "end", turnId, end });
    if (controller.current === abort) controller.current = null;
    latest.current.callbacks.onTurnSettled?.(conversationId);
  }, []);

  const isStreaming = state.turns.some((turn) => !isFinished(turn.answer));

  const send = useCallback(
    (question: string) => {
      const trimmed = question.trim();
      if (!trimmed || controller.current) return;
      const turn: LiveTurn = { id: crypto.randomUUID(), question: trimmed, answer: pendingAnswer };
      dispatch({ type: "ask", turn });
      void run(turn.id, trimmed);
    },
    [run],
  );

  /** Ask the last question again, replacing its unfinished answer. */
  const retry = useCallback(
    (turnId: string) => {
      const turn = latest.current.state.turns.find((t) => t.id === turnId);
      if (!turn || controller.current) return;
      dispatch({ type: "retry", turnId });
      void run(turnId, turn.question);
    },
    [run],
  );

  const stop = useCallback(() => controller.current?.abort(), []);

  /** Switch to another conversation (or a new chat); any running answer is stopped. */
  const reset = useCallback((conversationId: string | null) => {
    if (conversationId === conversationRef.current) return;
    controller.current?.abort();
    controller.current = null;
    conversationRef.current = conversationId;
    dispatch({ type: "reset", conversationId });
  }, []);

  useEffect(() => () => controller.current?.abort(), []);

  return { ...state, isStreaming, send, retry, stop, reset };
}

export type ChatStream = ReturnType<typeof useChatStream>;
