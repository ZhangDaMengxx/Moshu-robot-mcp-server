import sys
import unittest
from pathlib import Path


SIM_DIR = Path(__file__).resolve().parents[1] / "sim"
sys.path.insert(0, str(SIM_DIR))

from nero_arm import NeroArm  # noqa: E402


class NeroArmMockTest(unittest.TestCase):
    def test_connect_enables_mock_arm_for_motion(self):
        arm = NeroArm(mock=True)

        self.assertTrue(arm.connect())
        self.assertTrue(arm.enabled)
        self.assertEqual("mock", arm.firmware_detected)

        target = [0.0] * 7
        self.assertTrue(arm.move_j(target))
        self.assertEqual(target, arm._target)


if __name__ == "__main__":
    unittest.main()
