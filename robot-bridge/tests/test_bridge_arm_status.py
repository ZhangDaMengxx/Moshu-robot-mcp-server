import sys
import unittest
from pathlib import Path


BRIDGE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BRIDGE_DIR))

import bridge  # noqa: E402


class FakeArm:
    enabled = False
    frozen = False

    def __init__(self):
        self.read_enabled_calls = 0

    def read_angles(self):
        return [0.0] * 7

    def read_enabled(self):
        self.read_enabled_calls += 1
        return True


class BridgeArmStatusTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.previous_arm = bridge.arm

    async def asyncTearDown(self):
        bridge.arm = self.previous_arm

    async def test_status_refreshes_enabled_from_hardware(self):
        fake_arm = FakeArm()
        bridge.arm = fake_arm

        result = await bridge.arm_status()

        self.assertTrue(result["enabled"])
        self.assertEqual(1, fake_arm.read_enabled_calls)


if __name__ == "__main__":
    unittest.main()
