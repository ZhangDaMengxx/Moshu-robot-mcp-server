# MCP Server 部署入口

当前生产拓扑使用 FRP 将机器人本机 Bridge 转发到云服务器回环地址，公网只开放 HTTPS MCP 入口：

```text
MCP Client -> HTTPS /mcp -> Nginx -> MCP Server :8000
                                      |
                                      v
                              127.0.0.1:10005
                                      |
                                     FRP
                                      |
                              Bridge 127.0.0.1:9000
```

完整安装、systemd、Nginx、防火墙和排障步骤以仓库根目录的
[`frp_deploy.md`](../frp_deploy.md) 为准。

## 云端最小配置

在 `mcp_server/.env` 中配置：

```dotenv
ROBOT_BRIDGE_URL=http://127.0.0.1:10005
ROBOT_BRIDGE_TOKEN=独立的Bridge令牌
ROBOT_HEARTBEAT_INTERVAL=5
ROBOT_HEARTBEAT_TIMEOUT=2
MCP_SECURITY_MODE=public
MCP_API_KEYS=独立的MCP客户端密钥
MCP_CORS_ORIGINS=https://mcp.example.com
```

FRP token、Bridge token 和 MCP API key 是三类不同凭据，不能复用。生产环境使用前应轮换曾出现在聊天、日志或历史配置里的值。

启动重构后的服务需要重新构建镜像，因为 `requirements.txt` 已显式加入 `jsonschema`：

```bash
cd mcp_server
docker compose -f docker-compose.frp.yml up -d --build
docker logs --tail 100 mcp-robot-server
```

不要使用普通 `docker-compose.yml` 做云端 FRP 部署：它不使用 host 网络，无法访问云主机回环地址上的 FRP 代理端口。

## 验证顺序

先验证只读链路，不直接执行运动：

```bash
curl http://127.0.0.1:10005/health
curl http://127.0.0.1:8000/health

curl -X POST http://127.0.0.1:8000/mcp \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: 你的MCP_API_KEY' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

`tools/list` 应返回 3 个联合动作工具。三个工具都会产生真实运动，完成现场安全确认前
不要调用 `tools/call`。

公网客户端连接最终地址：

```json
{
  "mcpServers": {
    "robot": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://mcp.example.com/mcp",
        "--header",
        "X-API-Key:你的MCP_API_KEY"
      ]
    }
  }
}
```

## 公网边界

- 对公网开放：`443`，FRP 控制连接需要的 `7000`，以及证书签发用的 `80`。
- 仅回环监听：Bridge代理端口 `10005` 和 MCP进程端口 `8000`。
- 不允许公网客户端绕过 MCP Server 直接调用 Bridge。
- `MCP_SECURITY_MODE=public` 必须配非空 `MCP_API_KEYS`，否则服务拒绝启动。
