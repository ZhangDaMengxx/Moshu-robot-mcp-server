"""与 HTTP 传输无关的 MCP JSON-RPC 方法处理。"""
import logging

from .registry import registry


logger = logging.getLogger(__name__)
PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_PROTOCOL_VERSIONS = {"2024-11-05", "2025-03-26", PROTOCOL_VERSION}
SERVER_INFO = {"name": "robot-mcp-server", "version": "1.1.0"}


class MethodNotFound(Exception):
    pass


class MCPProtocol:
    def __init__(self, robot):
        self.robot = robot

    async def dispatch(self, method: str, params: dict) -> dict:
        if method == "initialize":
            client = (params.get("clientInfo") or {}).get("name", "unknown")
            requested_version = params.get("protocolVersion")
            negotiated_version = (
                requested_version
                if requested_version in SUPPORTED_PROTOCOL_VERSIONS
                else PROTOCOL_VERSION
            )
            logger.info("MCP initialize ← %s (请求 %s，协商 %s)", client,
                        requested_version or "未报", negotiated_version)
            return {
                "protocolVersion": negotiated_version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": registry.list_tools()}
        if method == "tools/call":
            return await registry.call(self.robot, params.get("name"), params.get("arguments"))
        raise MethodNotFound(method)
