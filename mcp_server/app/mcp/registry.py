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


def _recorded_skill_handler(skill_name: str) -> ToolHandler:
    async def handler(robot, arguments):
        return await robot.skill_execute(skill_name)
    return handler


RECORDED_SKILL_TOOLS = (
    ("combo_wave", "挥手", "执行机械臂与灵巧手联合挥手动作"),
    ("combo_reach", "伸手", "执行机械臂与灵巧手联合伸手动作"),
    ("combo_thumbs_up", "点赞", "执行机械臂与灵巧手联合点赞动作"),
)

FLAT_RECORDED_SKILL_DEFINITIONS = tuple(
    ToolDefinition(
        name=tool_name,
        description=f"{description}。会产生真实运动。",
        input_schema=_no_input(),
        handler=_recorded_skill_handler(skill_name),
    )
    for tool_name, skill_name, description in RECORDED_SKILL_TOOLS
)

TOOL_DEFINITIONS = FLAT_RECORDED_SKILL_DEFINITIONS


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
        if isinstance(payload, dict):
            result["structuredContent"] = json.loads(text)
        if is_error:
            result["isError"] = True
        return result


registry = ToolRegistry()
