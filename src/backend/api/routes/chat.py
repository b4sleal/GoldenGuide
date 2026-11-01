"""Public chatbot endpoints."""
from uuid import UUID

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query, Request
from starlette.responses import StreamingResponse

from backend.api.auth import require_same_origin
from backend.api.cookies import (
    anonymous_client_id,
    client_id_hash,
    remember_anonymous_client,
)
from backend.api.errors import current_trace_id, request_id_of
from backend.api.middleware.simple_rate_limit import limit_chat
from backend.api.schemas import ChatRequest, FeedbackRequest
from backend.api.streaming import ndjson_stream
from backend.application.use_cases.chatbot.chat_turn import ChatTurn
from backend.application.use_cases.chatbot.conversation_history import (
    ConversationHistory,
)
from backend.core.di.container import AppContainer
from backend.domain.entities.conversations import (
    ChatMessagePublic,
    ChatTurnContext,
    ConversationSummary,
    MessageFeedbackCreate,
)

# Every chat endpoint is rate limited per client before any work (or LLM spend) happens.
router = APIRouter(dependencies=[Depends(limit_chat)])


# Response header naming the stored conversation; the client sends it back to continue the chat.
CONVERSATION_HEADER = "X-Conversation-Id"


@router.post("/stream", response_class=StreamingResponse)
@inject
async def stream_answer(
        request: Request,
        body: ChatRequest,
        chat_turn: ChatTurn = Depends(Provide[AppContainer.services.chat_turn]),
) -> StreamingResponse:
    """Answer a student question as an NDJSON event stream.

    See api/streaming.py for the event types. A complete answer always ends with {"type": "ok"}.
    The turn is stored; the conversation's ID is returned in the X-Conversation-Id header.
    """
    client_id = anonymous_client_id(request)
    conversation_id, answer = await chat_turn.start(body.query, ChatTurnContext(
        conversation_id=body.conversation_id,
        client_id_hash=client_id_hash(client_id),
        request_id=request_id_of(request.scope),
        trace_id=current_trace_id(),
    ))

    # The answer is an async generator: nothing runs until ndjson_stream pulls the first event.
    response = await ndjson_stream(request, answer)
    remember_anonymous_client(request, response, client_id)
    if conversation_id is not None:
        response.headers[CONVERSATION_HEADER] = str(conversation_id)
    return response


# History is scoped to this browser's device cookie; a browser without one simply has no history yet.
def _device(request: Request) -> str:
    return client_id_hash(anonymous_client_id(request))


@router.get("/conversations", response_model=list[ConversationSummary])
@inject
async def list_conversations(
        request: Request,
        limit: int = Query(default=30, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        history: ConversationHistory = Depends(Provide[AppContainer.services.conversation_history]),
) -> list[ConversationSummary]:
    """This browser's conversations, most recently active first."""
    return await history.list_conversations(_device(request), limit, offset)


@router.get("/conversations/{conversation_id}/messages", response_model=list[ChatMessagePublic])
@inject
async def conversation_messages(
        request: Request,
        conversation_id: UUID,
        limit: int = Query(default=200, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
        history: ConversationHistory = Depends(Provide[AppContainer.services.conversation_history]),
) -> list[ChatMessagePublic]:
    """One of this browser's conversations, in order. 404 if it belongs to another browser."""
    return await history.messages(_device(request), conversation_id, limit, offset)


@router.delete("/conversations/{conversation_id}", status_code=204, dependencies=[Depends(require_same_origin)])
@inject
async def delete_conversation(
        request: Request,
        conversation_id: UUID,
        history: ConversationHistory = Depends(Provide[AppContainer.services.conversation_history]),
) -> None:
    """Permanently delete one of this browser's conversations with its messages and feedback."""
    await history.delete(_device(request), conversation_id)


@router.put("/messages/{message_id}/feedback", status_code=204, dependencies=[Depends(require_same_origin)])
@inject
async def submit_feedback(
        request: Request,
        message_id: int,
        feedback: FeedbackRequest,
        history: ConversationHistory = Depends(Provide[AppContainer.services.conversation_history]),
) -> None:
    """Rate one of this browser's answers; a new rating replaces the earlier one."""
    await history.rate(_device(request), MessageFeedbackCreate(message_id=message_id, **feedback.model_dump()))
