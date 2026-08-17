import asyncio
import sys
import unittest
from pathlib import Path

import httpx


MCP_SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MCP_SERVER_DIR))

from app.robot.controller import RobotController  # noqa: E402


class RobotControllerHeartbeatTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.online = True
        self.motion_attempts = 0

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/arm/joints":
                self.motion_attempts += 1
            if not self.online:
                raise httpx.ConnectError("bridge offline", request=request)
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "ok"})
            if request.url.path == "/arm/joints":
                return httpx.Response(200, json={"ok": True})
            if request.url.path == "/skills":
                return httpx.Response(200, json={"skills": [{"name": "挥手"}]})
            if request.url.path == "/skills/execute":
                body = request.content.decode()
                return httpx.Response(200, json={"ok": True, "request": body})
            return httpx.Response(200, json={})

        client = httpx.AsyncClient(
            base_url="http://bridge.test",
            transport=httpx.MockTransport(handler),
        )
        self.controller = RobotController(
            "http://bridge.test",
            heartbeat_interval=0.01,
            heartbeat_timeout=0.01,
            client=client,
        )

    async def asyncTearDown(self):
        await self.controller.disconnect()

    async def test_health_failure_and_recovery_update_status(self):
        self.assertTrue(await self.controller.connect())
        self.assertTrue(self.controller.connection_status()["connected"])

        self.online = False
        self.assertFalse(await self.controller.check_health())
        failed = self.controller.connection_status()
        self.assertFalse(failed["connected"])
        self.assertEqual(1, failed["consecutive_failures"])
        self.assertIsNotNone(failed["last_error"])

        self.online = True
        self.assertTrue(await self.controller.check_health())
        recovered = self.controller.connection_status()
        self.assertTrue(recovered["connected"])
        self.assertEqual(0, recovered["consecutive_failures"])
        self.assertIsNotNone(recovered["last_seen"])
        self.assertIsNone(recovered["last_error"])

    async def test_background_heartbeat_detects_disconnect_and_stops(self):
        self.assertTrue(await self.controller.connect())
        self.controller.start_heartbeat()
        task = self.controller._heartbeat_task
        self.controller.start_heartbeat()
        self.assertIs(task, self.controller._heartbeat_task)

        self.online = False
        await asyncio.sleep(0.03)
        self.assertFalse(self.controller.connection_status()["connected"])

        await self.controller.stop_heartbeat()
        self.assertIsNone(self.controller._heartbeat_task)
        self.assertTrue(task.done())

    async def test_motion_request_is_not_retried_after_disconnect(self):
        self.assertTrue(await self.controller.connect())

        self.online = False
        with self.assertRaises(RuntimeError):
            await self.controller.arm_set_joints([0.0] * 7)

        self.assertEqual(1, self.motion_attempts)
        self.assertFalse(self.controller.connection_status()["connected"])

    async def test_recorded_skill_calls_bridge(self):
        self.assertTrue(await self.controller.connect())
        listed = await self.controller.skill_list()
        self.assertEqual("挥手", listed["skills"][0]["name"])
        played = await self.controller.skill_execute("挥手", True, True)
        self.assertTrue(played["ok"])
        self.assertIn('"allow_mock_recording":true', played["request"].replace(" ", ""))


if __name__ == "__main__":
    unittest.main()
