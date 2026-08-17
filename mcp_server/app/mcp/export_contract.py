"""将工具契约输出为 JSON，供文档和 SDK 代码生成使用。"""
import json

from .protocol import PROTOCOL_VERSION, SERVER_INFO
from .registry import registry


def contract() -> dict:
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "serverInfo": SERVER_INFO,
        "tools": registry.list_tools(),
    }


if __name__ == "__main__":
    print(json.dumps(contract(), ensure_ascii=False, indent=2))
