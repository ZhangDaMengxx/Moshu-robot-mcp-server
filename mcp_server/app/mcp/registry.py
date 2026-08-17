"""MCP 工具契约与调用注册表。"""
from dataclasses import dataclass
import json
import logging
from typing import Any, Awaitable, Callable

from jsonschema import Draft202012Validator, ValidationError


logger = logging.getLogger(__name__)

ToolHandler = Callable[[Any, dict[str, Any]], Awaitable[Any]]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler
    read_only: bool = False
    destructive: bool = False

    def as_mcp_tool(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "annotations": {
                "readOnlyHint": self.read_only,
                "destructiveHint": self.destructive,
            },
        }


def _no_input() -> dict[str, Any]:
    return {"type": "object", "properties": {}, "additionalProperties": False}


async def _hand_list_gestures(robot, arguments):
    return await robot.hand_list_gestures()


async def _hand_gesture(robot, arguments):
    return await robot.hand_gesture(arguments["name"])


async def _hand_set_angles(robot, arguments):
    return await robot.hand_set_angles(arguments["angles"])


async def _hand_status(robot, arguments):
    return await robot.hand_status()


async def _arm_status(robot, arguments):
    return await robot.arm_status()


async def _arm_set_joints(robot, arguments):
    return await robot.arm_set_joints(arguments["joints"])


async def _arm_enable(robot, arguments):
    return await robot.arm_enable()


async def _arm_disable(robot, arguments):
    return await robot.arm_disable()


async def _arm_estop(robot, arguments):
    return await robot.arm_estop()


async def _arm_reset(robot, arguments):
    return await robot.arm_reset()


TOOL_DEFINITIONS = (
    ToolDefinition(
        name="hand_list_gestures",
        description="列出可用的灵巧手手势及其含义。调 hand_gesture 前先用这个拿准确的 id，不要凭猜测填 id。",
        input_schema=_no_input(),
        handler=_hand_list_gestures,
        read_only=True,
    ),
    ToolDefinition(
        name="hand_gesture",
        description="执行灵巧手预设手势。id 必须来自 hand_list_gestures。会先做拇指-食指可行域检查，会导致手指互顶的姿态被拒绝并说明原因。返回里的 mock 字段为 true 时表示空跑，硬件没有真实运动。",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "minLength": 1, "description": "手势 id，从 hand_list_gestures 获取"}
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        handler=_hand_gesture,
    ),
    ToolDefinition(
        name="hand_set_angles",
        description="设置灵巧手 6 个关节角度（弧度，0=张开）。会做拇指-食指可行域检查；优先使用 hand_gesture。",
        input_schema={
            "type": "object",
            "properties": {
                "angles": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 6,
                    "maxItems": 6,
                    "description": "[thumb_yaw, thumb_pitch, index, middle, ring, pinky]",
                }
            },
            "required": ["angles"],
            "additionalProperties": False,
        },
        handler=_hand_set_angles,
    ),
    ToolDefinition(
        name="hand_status",
        description="查询灵巧手当前状态（连接状态、关节角度）。mock=true 表示空跑模式。",
        input_schema=_no_input(),
        handler=_hand_status,
        read_only=True,
    ),
    ToolDefinition(
        name="arm_status",
        description="查询机械臂当前状态（连接、使能、急停、关节角度）。enabled=true 表示可运动；frozen=true 表示急停中。",
        input_schema=_no_input(),
        handler=_arm_status,
        read_only=True,
    ),
    ToolDefinition(
        name="arm_set_joints",
        description="设置机械臂 7 个关节角度（弧度）。机械臂必须已使能且未急停；输入会由 Bridge 按安全范围处理。",
        input_schema={
            "type": "object",
            "properties": {
                "joints": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 7,
                    "maxItems": 7,
                    "description": "7 个机械臂关节角度（rad）",
                }
            },
            "required": ["joints"],
            "additionalProperties": False,
        },
        handler=_arm_set_joints,
    ),
    ToolDefinition(
        name="arm_enable",
        description="使能机械臂电机。确认环境安全后调用，使能后机械臂才能执行运动指令。",
        input_schema=_no_input(),
        handler=_arm_enable,
    ),
    ToolDefinition(
        name="arm_disable",
        description="下使能机械臂电机，进入安全状态。完成工作后或需要手动移动机械臂时调用。",
        input_schema=_no_input(),
        handler=_arm_disable,
    ),
    ToolDefinition(
        name="arm_estop",
        description="机械臂急停：立即进入关节阻尼模式并失能。无抱闸，机械臂可能缓慢下落。",
        input_schema=_no_input(),
        handler=_arm_estop,
        destructive=True,
    ),
    ToolDefinition(
        name="arm_reset",
        description="退出急停阻尼模式并重新使能机械臂；这不会把机械臂移动到零位。",
        input_schema=_no_input(),
        handler=_arm_reset,
    ),
)


class ToolRegistry:
    def __init__(self, definitions=TOOL_DEFINITIONS):
        self._tools = {tool.name: tool for tool in definitions}
        if len(self._tools) != len(definitions):
            raise ValueError("MCP 工具名不能重复")

    def list_tools(self) -> list[dict[str, Any]]:
        return [tool.as_mcp_tool() for tool in self._tools.values()]

    async def call(self, robot, name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
        tool = self._tools.get(name)
        if tool is None:
            return self._text_result(f"未知工具: {name}", is_error=True)

        values = arguments or {}
        try:
            Draft202012Validator(tool.input_schema).validate(values)
        except ValidationError as error:
            location = ".".join(str(part) for part in error.absolute_path)
            prefix = f"参数 {location}: " if location else "参数错误: "
            return self._text_result(prefix + error.message, is_error=True)

        try:
            result = await tool.handler(robot, values)
        except ValueError as error:
            return self._text_result(str(error), is_error=True)
        except Exception as error:
            logger.warning("工具 %s 执行失败: %s", name, error)
            return self._text_result(f"执行失败: {error}", is_error=True)
        return self._text_result(result)

    @staticmethod
    def _text_result(payload, is_error: bool = False) -> dict[str, Any]:
        text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        result: dict[str, Any] = {"content": [{"type": "text", "text": text}]}
        if is_error:
            result["isError"] = True
        return result


registry = ToolRegistry()
