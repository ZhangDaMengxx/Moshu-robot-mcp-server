import sys
import unittest
from pathlib import Path
from unittest.mock import Mock


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

    def test_enable_waits_for_hardware_feedback(self):
        arm = NeroArm(mock=False)
        arm.robot = Mock()
        arm.robot.enable.return_value = True
        arm.robot.get_joint_enable_status.side_effect = [False, True]
        arm.ENABLE_POLL_SEC = 0.0

        self.assertTrue(arm.enable())
        self.assertTrue(arm.enabled)
        self.assertEqual(2, arm.robot.get_joint_enable_status.call_count)

    def test_enable_fails_when_hardware_does_not_confirm(self):
        arm = NeroArm(mock=False)
        arm.robot = Mock()
        arm.robot.enable.return_value = True
        arm.robot.get_joint_enable_status.return_value = False
        arm.ENABLE_CONFIRM_SEC = 0.0

        self.assertFalse(arm.enable())
        self.assertFalse(arm.enabled)
        self.assertIn("未确认硬件使能", arm.last_error)

    def test_disable_waits_for_hardware_feedback(self):
        arm = NeroArm(mock=False)
        arm.robot = Mock()
        arm._enabled = True
        arm.robot.disable.return_value = True
        arm.robot.get_joint_enable_status.side_effect = [True, False]
        arm.ENABLE_POLL_SEC = 0.0

        self.assertTrue(arm.disable())
        self.assertFalse(arm.enabled)
        self.assertEqual(2, arm.robot.get_joint_enable_status.call_count)

    def test_reset_confirms_reenabled_hardware(self):
        arm = NeroArm(mock=False)
        arm.robot = Mock()
        arm._frozen = True
        arm.robot.enable.return_value = True
        arm.robot.get_joint_enable_status.return_value = True

        self.assertTrue(arm.reset())
        self.assertFalse(arm.frozen)
        self.assertTrue(arm.enabled)
        arm.robot.reset.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
