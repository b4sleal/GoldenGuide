"""Public chatbot endpoints."""
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.responses import StreamingResponse

from backend.api.middleware.simple_rate_limit import limit_chat
from backend.api.schemas import ChatRequest, FeedbackRequest
from backend.api.streaming import ndjson_stream
from backend.application.use_cases.chatbot.rag_chatbot import RagChatbot
from backend.core.di.container import AppContainer

# Every chat endpoint is rate limited per client before any work (or LLM spend) happens.
router = APIRouter(dependencies=[Depends(limit_chat)])


@router.post("/stream", response_class=StreamingResponse)
@inject
async def stream_answer(
        request: Request,
        body: ChatRequest,
        chatbot: RagChatbot = Depends(Provide[AppContainer.services.rag_chatbot]),
) -> StreamingResponse:
    """Answer a student question as an NDJSON event stream.

    See api/streaming.py for the event types. A complete answer always ends with {"type": "ok"}.
    """
    # chatbot.ask() is an async generator: nothing runs until ndjson_stream pulls the first event.
    return await ndjson_stream(request, chatbot.ask(body.query))


@router.post("/feedback", status_code=501)
async def submit_feedback(feedback: FeedbackRequest) -> None:
    """Placeholder that says honestly it is not implemented; feedback persistence is a planned feature."""
    raise HTTPException(501, "Feedback persistence is not implemented")
