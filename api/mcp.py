from mcp.server.sse import SseServerTransport
from fastapi import APIRouter
from starlette.requests import Request

from core.mcp_tools import mcp_server

router = APIRouter()
_sse = SseServerTransport("/mcp/messages/")


@router.get("/mcp/sse")
async def mcp_sse(request: Request):
    async with _sse.connect_sse(request.scope, request.receive, request._send) as streams:
        await mcp_server.run(
            streams[0],
            streams[1],
            mcp_server.create_initialization_options(),
        )


@router.post("/mcp/messages/")
async def mcp_messages(request: Request):
    await _sse.handle_post_message(request.scope, request.receive, request._send)
