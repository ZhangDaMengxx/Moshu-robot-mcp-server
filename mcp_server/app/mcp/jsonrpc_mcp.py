"""旧模块名兼容层；新代码使用 transport.py 和 protocol.py。"""

from .protocol import PROTOCOL_VERSION
from .transport import bind, router


__all__ = ["PROTOCOL_VERSION", "bind", "router"]
