# Robot MCP Server

通过标准 MCP Streamable HTTP 协议向 Agent 暴露机械臂与灵巧手能力。公网客户端只应连接 MCP Server，不应直接访问 Robot Bridge。

```text
MCP Client -- JSON-RPC /mcp --> MCP Server -- HTTP --> Robot Bridge --> Hardware
```

## 目录职责

```text
app/
├── main.py                 FastAPI 装配、生命周期、健康检查
├── auth.py                 MCP API Key 中间件
├── config.py               YAML 与环境变量配置
├── mcp/
│   ├── registry.py         工具契约、参数校验、处理器注册（单一真源）
│   ├── protocol.py         initialize、ping、tools/list、tools/call
│   ├── transport.py        POST/GET/DELETE /mcp 与 SSE
│   ├── export_contract.py  导出 SDK/文档使用的工具契约
│   ├── server.py           已废弃 REST MCP 兼容层
│   ├── tools.py            旧工具导入路径兼容层
│   └── jsonrpc_mcp.py      旧协议模块导入路径兼容层
├── robot/controller.py     Bridge HTTP 客户端、心跳、硬件业务方法
└── api/v1/                 旧 REST 硬件接口
```

## 启动

```bash
cd mcp_server
ROBOT_BRIDGE_URL=http://127.0.0.1:9000 \
MCP_SECURITY_MODE=lan \
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

公网部署必须使用 `MCP_SECURITY_MODE=public` 并设置 `MCP_API_KEYS`。Bridge 应只允许 MCP Server 访问。

## 标准 MCP 调用

所有 MCP 方法都通过同一个 `/mcp` 地址发送。以下示例省略公网所需的 `X-API-Key`；公网调用时给每条请求增加：

```bash
-H 'X-API-Key: your-key'
```

### 1. 初始化

```bash
curl -i -X POST http://127.0.0.1:8000/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{
    "jsonrpc":"2.0",
    "id":1,
    "method":"initialize",
    "params":{
      "protocolVersion":"2025-06-18",
      "capabilities":{},
      "clientInfo":{"name":"curl-test","version":"1.0.0"}
    }
  }'
```

响应头会包含 `Mcp-Session-Id`。随后发送初始化完成通知：

```bash
curl -X POST http://127.0.0.1:8000/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}'
```

### 2. 查看工具

```bash
curl -X POST http://127.0.0.1:8000/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
```

### 3. 调用只读工具

```bash
curl -X POST http://127.0.0.1:8000/mcp \
  -H 'Content-Type: application/json' \
  -d '{
    "jsonrpc":"2.0",
    "id":3,
    "method":"tools/call",
    "params":{"name":"arm_status","arguments":{}}
  }'
```

真实运动工具会立即作用于硬件。调用前必须确认人员、机械臂和工作空间安全：

```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "tools/call",
  "params": {
    "name": "hand_gesture",
    "arguments": {"name": "hand_five"}
  }
}
```

## MCP 客户端配置

```json
{
  "mcpServers": {
    "moshu-robot": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://mcp.example.com/mcp",
        "--header",
        "X-API-Key:your-key"
      ]
    }
  }
}
```

## 当前工具

| 工具 | 类型 | 作用 |
|---|---|---|
| `hand_list_gestures` | 只读 | 列出手势 |
| `hand_status` | 只读 | 查询灵巧手状态 |
| `hand_gesture` | 运动 | 执行预设手势 |
| `hand_set_angles` | 运动 | 设置6个手关节角度 |
| `arm_status` | 只读 | 查询机械臂状态 |
| `arm_set_joints` | 运动 | 设置7个机械臂关节角度 |
| `arm_enable` | 状态变更 | 使能机械臂 |
| `arm_disable` | 状态变更 | 下使能机械臂 |
| `arm_estop` | 紧急操作 | 进入阻尼急停 |
| `arm_reset` | 状态变更 | 退出急停并重新使能，不回零 |
| `skill_list` | 只读 | 列出通过预检的联合录制技能 |
| `skill_execute` | 运动 | 执行联合录制技能，要求显式确认 |

### 平铺动作工具

这些工具会直接出现在 MCP `tools/list` 中，不需要先调用 `hand_list_gestures` 或
`skill_list`：

| 工具 | 作用 |
|---|---|
| `hand_open` / `hand_release` / `hand_pinch` | 张手、松手、对捏 |
| `hand_one` / `hand_two` / `hand_three` / `hand_four` / `hand_five` | 比数字 1–5 |
| `hand_ok` / `hand_point` | 仅灵巧手 OK、指向 |
| `combo_wave` / `combo_reach` | 联合挥手、伸手 |
| `combo_thumbs_up` / `combo_three_finger_grasp` | 联合点赞、三指抓握 |

联合动作工具需要参数 `{"confirm": true}`；灵巧手平铺工具无参数。原有
`hand_gesture`、`skill_execute` 继续保留为动态兼容入口。

## 契约与测试

```bash
cd mcp_server
python -m app.mcp.export_contract > contracts/tools.json
python -m unittest discover -s tests -v
```

导出的契约用于后续生成 Python SDK 类型和文档。不要手工维护另一份工具列表。

## 兼容接口

- `POST/GET/DELETE /mcp`：正式 MCP 接口。
- `/mcp_rest/*`：历史 REST MCP 接口，已废弃。
- `/api/v1/*`：历史硬件 REST 接口，不作为新 SDK 的调用入口。
- `GET /health`：服务和 Bridge 健康状态。
- `GET /docs`：FastAPI 辅助 REST 文档，不等同于 MCP 工具清单。
