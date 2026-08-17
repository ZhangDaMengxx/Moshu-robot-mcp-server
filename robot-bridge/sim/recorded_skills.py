"""录制的机械臂+灵巧手关键帧技能包加载与校验。"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path

from inspire_hand import HAND_JOINTS, HAND_LIMITS
from nero_arm import ARM_JOINTS, NERO_ARM_LIMITS
import hand_pose


SCHEMA = "combo_pack/1"
MAX_FILE_BYTES = 4 << 20
MAX_FRAMES = 200
MAX_DURATION_MS = 120_000
DATA_ROOT = Path(__file__).resolve().parents[1] / "data/combos"


class RecordedSkillError(ValueError):
    pass


@dataclass(frozen=True)
class RecordedFrame:
    arm: list[float]
    hand: list[float]
    hold_ms: int
    arm_speed_percent: int
    hand_speed: int
    hand_force: int


@dataclass(frozen=True)
class RecordedSkill:
    name: str
    path: str
    recorded_from: str
    frames: list[RecordedFrame]

    @property
    def duration_ms(self) -> int:
        return sum(frame.hold_ms for frame in self.frames)

    def public(self) -> dict:
        return {
            "name": self.name,
            "path": self.path,
            "kind": "recorded_combo",
            "recorded_from": self.recorded_from,
            "frames": len(self.frames),
            "duration_ms": self.duration_ms,
            "requires_mock_recording_confirmation": self.recorded_from == "mock",
        }


def skill_root() -> Path:
    configured = os.environ.get("RECORDED_SKILL_DIR")
    return Path(configured).expanduser().resolve() if configured else DATA_ROOT.resolve()


def _number_list(value, count: int, field: str) -> list[float]:
    if not isinstance(value, list) or len(value) != count:
        raise RecordedSkillError(f"{field} 需要 {count} 个数值")
    result = []
    for index, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
            raise RecordedSkillError(f"{field}[{index}] 必须是有限数值")
        result.append(float(item))
    return result


def _bounded_int(value, low: int, high: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RecordedSkillError(f"{field} 必须是数值")
    result = int(value)
    if result < low or result > high:
        raise RecordedSkillError(f"{field} 超出范围 [{low}, {high}]")
    return result


def _parse_frame(value: dict, index: int) -> RecordedFrame:
    if not isinstance(value, dict):
        raise RecordedSkillError(f"第 {index + 1} 帧必须是对象")
    arm = _number_list(value.get("arm_rad"), 7, f"第 {index + 1} 帧 arm_rad")
    hand = _number_list(value.get("hand_rad"), 6, f"第 {index + 1} 帧 hand_rad")
    for joint, angle, limits in zip(ARM_JOINTS, arm, NERO_ARM_LIMITS):
        if not limits[0] - 1e-4 <= angle <= limits[1] + 1e-4:
            raise RecordedSkillError(f"第 {index + 1} 帧 {joint}={angle:.5f} 超限")
    for joint, angle in zip(HAND_JOINTS, hand):
        low, high = HAND_LIMITS[joint]
        if not low - 1e-4 <= angle <= high + 1e-4:
            raise RecordedSkillError(f"第 {index + 1} 帧 {joint}={angle:.5f} 超限")
    infeasible = hand_pose.check_feasible(hand)
    if infeasible:
        raise RecordedSkillError(f"第 {index + 1} 帧手部姿态不可行: {infeasible}")
    return RecordedFrame(
        arm=arm,
        hand=hand,
        hold_ms=_bounded_int(value.get("hold_ms", 600), 0, 60_000, "hold_ms"),
        arm_speed_percent=_bounded_int(value.get("arm_speed_percent", 20), 1, 100,
                                       "arm_speed_percent"),
        hand_speed=_bounded_int(value.get("speed", 500), 0, 1000, "speed"),
        hand_force=_bounded_int(value.get("force", 500), 0, 1000, "force"),
    )


def load_path(path: Path) -> RecordedSkill:
    root = skill_root()
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError as error:
        raise RecordedSkillError("技能包路径越出允许目录") from error
    if resolved.stat().st_size > MAX_FILE_BYTES:
        raise RecordedSkillError("技能包文件过大")
    try:
        document = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RecordedSkillError(f"技能包读取失败: {error}") from error
    if document.get("schema") != SCHEMA:
        raise RecordedSkillError(f"schema 必须是 {SCHEMA}")
    if document.get("mode") != "keyframe":
        raise RecordedSkillError("当前只允许 keyframe 录制包")
    name = document.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 64:
        raise RecordedSkillError("技能名称为空或过长")
    recorded_from = document.get("recorded_from", "real")
    if recorded_from not in ("real", "mock"):
        raise RecordedSkillError("recorded_from 必须是 real 或 mock")
    if document.get("joint_order_arm") != ARM_JOINTS:
        raise RecordedSkillError("机械臂关节顺序不匹配")
    if document.get("joint_order_hand") != HAND_JOINTS:
        raise RecordedSkillError("灵巧手关节顺序不匹配")
    raw_frames = document.get("frames")
    if not isinstance(raw_frames, list) or not raw_frames:
        raise RecordedSkillError("技能包没有帧")
    if len(raw_frames) > MAX_FRAMES:
        raise RecordedSkillError(f"帧数超过上限 {MAX_FRAMES}")
    frames = [_parse_frame(frame, index) for index, frame in enumerate(raw_frames)]
    skill = RecordedSkill(name=name.strip(), path=relative,
                          recorded_from=recorded_from, frames=frames)
    if skill.duration_ms > MAX_DURATION_MS:
        raise RecordedSkillError(f"总时长超过上限 {MAX_DURATION_MS}ms")
    return skill


def list_skills() -> list[dict]:
    root = skill_root()
    if not root.is_dir():
        return []
    result = []
    for path in sorted(root.rglob("*.json")):
        if path.name.startswith("."):
            continue
        try:
            result.append(load_path(path).public())
        except (OSError, RecordedSkillError):
            continue
    return result


def load_skill(name: str) -> RecordedSkill:
    matches = []
    root = skill_root()
    for path in root.rglob("*.json") if root.is_dir() else ():
        if path.name.startswith("."):
            continue
        try:
            skill = load_path(path)
        except (OSError, RecordedSkillError):
            continue
        if skill.name == name or skill.path == name:
            matches.append(skill)
    if not matches:
        available = ", ".join(item["name"] for item in list_skills()) or "无"
        raise RecordedSkillError(f"未找到技能 {name!r}；可用: {available}")
    if len(matches) > 1:
        paths = ", ".join(skill.path for skill in matches)
        raise RecordedSkillError(f"技能名重复，请用路径指定: {paths}")
    return matches[0]
