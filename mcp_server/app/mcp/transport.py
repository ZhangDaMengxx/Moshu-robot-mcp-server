"""MCP Streamable HTTP 传输。"""
import asyncio
import json
import logging
import secrets

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from .protocol import MCPProtocol, MethodNotFound


logger = logging.getLogger(__name__)
router = APIRouter()
protocol: MCPProtocol | None = None
_sessions: set[str] = set()


def bind(robot) -> None:
    global protocol
    protocol = MCPProtocol(robot)


def _ok(request_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id, code: int, message: str, data: str | None = None) -> dict:
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def _respond(request: Request, payload: dict, headers: dict[str, str]) -> Response:
    accept = request.headers.get("accept", "")
    if "text/event-stream" in accept and "application/json" not in accept:
        body = f"event: message\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
        return Response(body, media_type="text/event-stream", headers={**headers, "Cache-Control": "no-cache"})
    return JSONResponse(payload, headers=headers)


@router.post("/mcp")
async def mcp_post(request: Request):
    try:
        body = await request.json()
    except Exception as error:
        return JSONResponse(_error(None, -32700, "Parse error", str(error)), status_code=400)
    if not isinstance(body, dict):
        return JSONResponse(_error(None, -32600, "Invalid Request", "不支持批量请求，请单条发送"), status_code=400)

    method = body.get("method")
    request_id = body.get("id")
    params = body.get("params") or {}
    if not method:
        return JSONResponse(_error(request_id, -32600, "Invalid Request", "缺少 method"), status_code=400)
    if request_id is None:
        if method == "notifications/initialized":
            logger.info("MCP 握手完成")
        return Response(status_code=202)
    if protocol is None:
        return JSONResponse(_error(request_id, -32603, "MCP protocol not initialized"), status_code=500)

    headers: dict[str, str] = {}
    try:
        result = await protocol.dispatch(method, params)
        if method == "initialize":
            session_id = secrets.token_urlsafe(16)
            _sessions.add(session_id)
            headers["Mcp-Session-Id"] = session_id
    except MethodNotFound:
        return JSONResponse(_error(request_id, -32601, f"Method not found: {method}"))
    except Exception as error:
        logger.exception("处理 %s 时出错", method)
        return JSONResponse(_error(request_id, -32603, "Internal error", str(error)))
    return _respond(request, _ok(request_id, result), headers)


@router.get("/mcp")
async def mcp_get(request: Request):
    if "text/event-stream" not in request.headers.get("accept", ""):
        return JSONResponse({"detail": "此端点仅支持 text/event-stream"}, status_code=406)

    async def keepalive():
        yield ": connected\n\n"
        while not await request.is_disconnected():
            await asyncio.sleep(15)
            yield ": keepalive\n\n"

    return StreamingResponse(keepalive(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.delete("/mcp")
async def mcp_delete(request: Request):
    session_id = request.headers.get("mcp-session-id")
    if session_id:
        _sessions.discard(session_id)
    return Response(status_code=204)
