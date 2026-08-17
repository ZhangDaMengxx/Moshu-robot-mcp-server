"""MCP 协议实现（简化版）

参考: https://modelcontextprotocol.io/specification/2026-07-28
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any

router = APIRouter()
robot = None  # 注入


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any]


# ============================================================================
# 工具定义 —— 从 tools.py 读,不在这里再存一份
# ============================================================================
from .registry import registry  # noqa: E402


# ============================================================================
# MCP 端点
# ============================================================================
@router.post("/tools/list")
async def list_tools():
    """列出可用工具"""
    return {"tools": registry.list_tools()}


@router.post("/tools/call")
async def call_tool(call: ToolCall):
    """调用工具"""
    return await registry.call(robot, call.name, call.arguments)
