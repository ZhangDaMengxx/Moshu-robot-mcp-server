import sys
import unittest
from pathlib import Path

import httpx
from fastapi import FastAPI


MCP_SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MCP_SERVER_DIR))

from app.mcp import transport  # noqa: E402


class FakeRobot:
    async def hand_status(self):
        return {"connected": True, "mock": True}


class MCPTransportTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        app = FastAPI()
        transport.bind(FakeRobot())
        app.include_router(transport.router)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://mcp.test")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def request(self, method, params=None, request_id=1):
        return await self.client.post("/mcp", json={
            "jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {},
        })

    async def test_initialize_list_call_and_delete_session(self):
        initialized = await self.request("initialize", {
            "protocolVersion": "2025-06-18",
            "clientInfo": {"name": "transport-test", "version": "1"},
        })
        self.assertEqual(200, initialized.status_code)
        session_id = initialized.headers["mcp-session-id"]
        listed = await self.request("tools/list")
        self.assertEqual(12, len(listed.json()["result"]["tools"]))
        called = await self.request("tools/call", {"name": "hand_status", "arguments": {}})
        self.assertFalse(called.json()["result"].get("isError", False))
        closed = await self.client.delete("/mcp", headers={"Mcp-Session-Id": session_id})
        self.assertEqual(204, closed.status_code)

    async def test_notification_has_no_response_body(self):
        response = await self.client.post("/mcp", json={
            "jsonrpc": "2.0", "method": "notifications/initialized",
        })
        self.assertEqual(202, response.status_code)
        self.assertEqual(b"", response.content)

    async def test_unknown_method_uses_json_rpc_error(self):
        response = await self.request("missing/method")
        self.assertEqual(-32601, response.json()["error"]["code"])


if __name__ == "__main__":
    unittest.main()
