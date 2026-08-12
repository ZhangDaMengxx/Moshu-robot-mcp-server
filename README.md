# robot-mcp-server

机器人 MCP 服务完整部署包，包含 **bridge**（硬件代理）和 **MCP Server**（云端服务）。

```
[Claude] --MCP--> [MCP Server] --HTTP--> [bridge] --RS485/CAN--> [硬件]
                   云端或本机             本机连硬件
```

## 目录结构

```
robot-mcp-server/
├── robot-bridge/    # 硬件代理（用户本机，连着硬件）
│   ├── bridge.py
│   ├── sim/         # 驱动（inspire_hand.py, nero_arm.py）
│   └── README.md    # 详细使用说明
└── mcp_server/      # MCP Server（云端或本机）
    ├── app/
    ├── Dockerfile
    └── README.md    # 部署说明
```

## 快速开始

### 1. 启动 bridge（本机）

```bash
cd robot-bridge
pip install -r requirements.txt

# mock 模式（不连硬件）
python bridge.py --mock --host 127.0.0.1 --port 9000

# 真机 Linux
python bridge.py --hand-port /dev/ttyUSB0 --host 127.0.0.1 --port 9000

# 真机 Windows
python bridge.py --hand-port COM5 --host 127.0.0.1 --port 9000
```

详见 [robot-bridge/README.md](robot-bridge/README.md)。

### 2. 启动 MCP Server

**单机验证**（bridge 和 MCP Server 同一台机器）：

```bash
cd mcp_server
export ROBOT_BRIDGE_URL=http://127.0.0.1:9000
export MCP_SECURITY_MODE=lan
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**云端部署**（Docker）：

```bash
cd mcp_server
docker compose up -d
```

详见 [mcp_server/DEPLOY.md](mcp_server/DEPLOY.md) 和 [mcp_server/SERVER_DEPLOY.md](mcp_server/SERVER_DEPLOY.md)。

### 3. 配置 Claude Desktop

`mcpServers` 走 stdio，需要 mcp-remote 代理（需要 Node.js）：

```json
{
  "mcpServers": {
    "robot": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://127.0.0.1:8000/mcp"]
    }
  }
}
```

远端服务器在 `args` 末尾加 `"--header", "X-API-Key:你的key"`。

重启 Claude Desktop，问它"列出可用的手势"验证链路。

## 文档

| 文档 | 说明 |
|------|------|
| [robot-bridge/README.md](robot-bridge/README.md) | bridge 完整说明（硬件准备、接口、认证） |
| [robot-bridge/WINDOWS_DEPLOY.md](robot-bridge/WINDOWS_DEPLOY.md) | **Windows 完整部署指南**（灵巧手 + 机械臂） |
| [mcp_server/DEPLOY.md](mcp_server/DEPLOY.md) | 用户部署指南（本地 + 隧道） |
| [mcp_server/SERVER_DEPLOY.md](mcp_server/SERVER_DEPLOY.md) | 云端 MCP Server 部署 |
| [mcp_server/DOCKER_BUILD.md](mcp_server/DOCKER_BUILD.md) | Docker 构建问题排查 |

## 平台支持

### Windows 完整支持 ✅

- **灵巧手**：RS485 串口（`--hand-port COM5`）
- **机械臂**：松灵 CAN 适配器（agx_cando 接口，自动检测）
- **单机部署**：bridge + MCP Server 同一台 Windows 机器
- **详细指南**：[robot-bridge/WINDOWS_DEPLOY.md](robot-bridge/WINDOWS_DEPLOY.md)

### Linux / WSL

- **灵巧手**：RS485 串口（`--hand-port /dev/ttyUSB0`）
- **机械臂**：SocketCAN（需要 `ip link set can0 up`）
- **WSL 注意**：通过 usbipd 转发 USB 设备（转发期间 Windows 侧不可用）

## 已修复的跨平台问题

- ✅ Windows UTF-8 编码（config.yaml 加 `encoding="utf-8"`）
- ✅ 串口路径跨平台（`--hand-port` 参数，Linux `/dev/ttyUSB0` / Windows `COM5`）
- ✅ 机械臂 Windows 支持（agx_cando 接口，自动平台检测）
- ✅ MCP 协议合规（通知处理、JSON 序列化、会话管理、SSE）
- ✅ 单机部署无需云服务器（本机验证通过）

---

完整开发仓库：https://github.com/ZhangDaMengxx/VLA-HandArm
