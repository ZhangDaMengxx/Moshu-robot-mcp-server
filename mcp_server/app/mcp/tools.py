"""旧导入路径兼容层；工具契约的单一真源在 registry.py。"""

from .registry import registry


TOOLS = registry.list_tools()
