import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


MCP_SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MCP_SERVER_DIR))

from app.mcp.protocol import MCPProtocol, PROTOCOL_VERSION  # noqa: E402
from app.mcp.registry import registry  # noqa: E402


EXPECTED_TOOLS = {
    "combo_wave", "combo_reach", "combo_thumbs_up",
}


class FakeRobot:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        async def call(*arguments):
            self.calls.append((name, arguments))
            return {"method": name, "arguments": arguments, "mock": True}
        return call


class MCPContractTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.robot = FakeRobot()

    def test_tool_names_and_schemas_are_stable(self):
        tools = registry.list_tools()
        self.assertEqual(EXPECTED_TOOLS, {tool["name"] for tool in tools})
        self.assertEqual(len(EXPECTED_TOOLS), len(tools))
        for tool in tools:
            Draft202012Validator.check_schema(tool["inputSchema"])
            self.assertIn("readOnlyHint", tool["annotations"])
            self.assertIn("destructiveHint", tool["annotations"])

    async def test_registry_rejects_unknown_tools_before_calling_hardware(self):
        result = await registry.call(self.robot, "arm_set_joints", {"joints": [0.0] * 7})
        self.assertTrue(result["isError"])
        self.assertEqual([], self.robot.calls)

    async def test_flat_combo_tool_dispatches_fixed_skill(self):
        result = await registry.call(self.robot, "combo_wave", {})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual("skill_execute", payload["method"])
        self.assertEqual([("skill_execute", ("挥手",))], self.robot.calls)

    async def test_protocol_exposes_current_contract(self):
        protocol = MCPProtocol(self.robot)
        initialized = await protocol.dispatch("initialize", {
            "protocolVersion": "2025-06-18",
            "clientInfo": {"name": "contract-test", "version": "1"},
        })
        self.assertEqual(PROTOCOL_VERSION, initialized["protocolVersion"])
        self.assertEqual("robot-mcp-server", initialized["serverInfo"]["name"])
        listed = await protocol.dispatch("tools/list", {})
        self.assertEqual(EXPECTED_TOOLS, {tool["name"] for tool in listed["tools"]})

    async def test_protocol_keeps_legacy_client_compatibility(self):
        protocol = MCPProtocol(self.robot)
        initialized = await protocol.dispatch("initialize", {
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "legacy-client", "version": "1"},
        })
        self.assertEqual("2024-11-05", initialized["protocolVersion"])


if __name__ == "__main__":
    unittest.main()
