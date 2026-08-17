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
    "hand_list_gestures", "hand_gesture", "hand_set_angles", "hand_status",
    "arm_status", "arm_set_joints", "arm_enable", "arm_disable", "arm_estop", "arm_reset",
    "skill_list", "skill_execute",
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

    async def test_registry_validates_before_calling_hardware(self):
        result = await registry.call(self.robot, "arm_set_joints", {"joints": [0.0] * 6})
        self.assertTrue(result["isError"])
        self.assertEqual([], self.robot.calls)

    async def test_registry_dispatches_valid_call(self):
        result = await registry.call(self.robot, "hand_gesture", {"name": "hand_five"})
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual("hand_gesture", payload["method"])
        self.assertEqual([("hand_gesture", ("hand_five",))], self.robot.calls)

    async def test_skill_execute_forwards_both_confirmations(self):
        result = await registry.call(self.robot, "skill_execute", {
            "name": "挥手",
            "confirm": True,
            "allow_mock_recording": True,
        })
        payload = json.loads(result["content"][0]["text"])
        self.assertEqual("skill_execute", payload["method"])
        self.assertEqual(
            [("skill_execute", ("挥手", True, True))],
            self.robot.calls,
        )

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
