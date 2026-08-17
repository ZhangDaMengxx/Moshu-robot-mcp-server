import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


BRIDGE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BRIDGE_DIR / "sim"))
sys.path.insert(0, str(BRIDGE_DIR / "sim/skills"))
sys.path.insert(0, str(BRIDGE_DIR))

import bridge  # noqa: E402
from inspire_hand import HAND_JOINTS  # noqa: E402
from nero_arm import ARM_JOINTS  # noqa: E402
import recorded_skills  # noqa: E402


class FakeArm:
    enabled = True
    frozen = False

    def __init__(self):
        self.moves = []
        self.speeds = []

    def set_speed_percent(self, value):
        self.speeds.append(value)

    def move_j(self, values):
        self.moves.append(values)
        return True


class FakeHand:
    class Config:
        mock = True

    cfg = Config()

    def __init__(self):
        self.moves = []

    def set_speed(self, value):
        return True

    def set_force(self, value):
        return True

    def set_angles(self, values):
        self.moves.append(values)
        return True


class RecordedSkillsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.previous_root = os.environ.get("RECORDED_SKILL_DIR")
        os.environ["RECORDED_SKILL_DIR"] = self.tempdir.name
        self.pack_path = Path(self.tempdir.name) / "wave.json"
        self.pack_path.write_text(json.dumps({
            "schema": "combo_pack/1",
            "name": "挥手",
            "mode": "keyframe",
            "recorded_from": "mock",
            "joint_order_arm": ARM_JOINTS,
            "joint_order_hand": HAND_JOINTS,
            "frames": [{
                "arm_rad": [0.0] * 7,
                "hand_rad": [0.0] * 6,
                "hold_ms": 1,
                "arm_speed_percent": 20,
                "speed": 100,
                "force": 100,
            }],
        }), encoding="utf-8")
        bridge.arm = FakeArm()
        bridge.hand = FakeHand()

    def tearDown(self):
        bridge.arm = None
        bridge.hand = None
        if self.previous_root is None:
            os.environ.pop("RECORDED_SKILL_DIR", None)
        else:
            os.environ["RECORDED_SKILL_DIR"] = self.previous_root
        self.tempdir.cleanup()

    def test_lists_only_validated_packs(self):
        self.assertEqual(["挥手"], [item["name"] for item in recorded_skills.list_skills()])

    async def test_requires_explicit_confirmation(self):
        with self.assertRaisesRegex(Exception, "confirm=true"):
            await bridge.skill_execute(bridge.SkillExecuteRequest(name="挥手"))
        self.assertEqual([], bridge.arm.moves)

    async def test_mock_recording_requires_extra_confirmation(self):
        request = bridge.SkillExecuteRequest(name="挥手", confirm=True)
        with self.assertRaisesRegex(Exception, "allow_mock_recording=true"):
            await bridge.skill_execute(request)
        self.assertEqual([], bridge.arm.moves)

    async def test_executes_prevalidated_frames(self):
        request = bridge.SkillExecuteRequest(
            name="挥手", confirm=True, allow_mock_recording=True)
        async def run_sync(function, *arguments):
            return function(*arguments)

        with patch.object(bridge.asyncio, "sleep", new=AsyncMock()), \
                patch.object(bridge.asyncio, "to_thread", side_effect=run_sync):
            result = await bridge.skill_execute(request)
        self.assertTrue(result["ok"])
        self.assertEqual([[0.0] * 7], bridge.arm.moves)
        self.assertEqual([[0.0] * 6], bridge.hand.moves)

    async def test_invalid_later_frame_prevents_any_motion(self):
        document = json.loads(self.pack_path.read_text(encoding="utf-8"))
        document["frames"].append({
            "arm_rad": [99.0] * 7,
            "hand_rad": [0.0] * 6,
            "hold_ms": 1,
        })
        self.pack_path.write_text(json.dumps(document), encoding="utf-8")
        request = bridge.SkillExecuteRequest(
            name="挥手", confirm=True, allow_mock_recording=True)
        with self.assertRaisesRegex(Exception, "未找到技能"):
            await bridge.skill_execute(request)
        self.assertEqual([], bridge.arm.moves)


if __name__ == "__main__":
    unittest.main()
