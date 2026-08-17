# Windows 部署指南

在 Windows 上运行 bridge + MCP Server，支持灵巧手和机械臂。

## 硬件要求

- **灵巧手**：Inspire 六自由度手 + RS485 转 USB 串口适配器
- **机械臂**（可选）：松灵 NERO 七自由度臂 + 松灵官方 CAN 适配器

## 软件要求

- Windows 10/11
- Python 3.10+
- Node.js（用于 Claude Desktop 的 mcp-remote 代理）

## 安装步骤

### 1. 安装 Python 依赖

```powershell
# 基础依赖（灵巧手必需）
pip install fastapi uvicorn pyserial pyyaml

# 机械臂依赖（可选，如果要用机械臂才装）
pip install python-can
pip install "git+https://github.com/agilexrobotics/python-can-agx-cando.git"
pip install "git+https://github.com/agilexrobotics/pyAgxArm.git"
```

### 2. 硬件连接

**灵巧手**：
1. RS485 适配器插到 Windows USB 口
2. 设备管理器查看 COM 口号（如 `COM5`）
3. 确认 24V 供电已接通

**机械臂**：
1. 松灵 CAN 适配器插到 Windows USB 口
2. 安装厂商驱动（如果需要）
3. 确认机械臂电源已开启

### 3. 启动 bridge

**只用灵巧手（不用机械臂）**：
```powershell
python bridge.py --hand-port COM5 --host 127.0.0.1 --port 9000
```

**灵巧手 + 机械臂**：
```powershell
python bridge.py --hand-port COM5 --host 127.0.0.1 --port 9000
# 代码会自动检测 Windows 平台，使用 agx_cando 接口
```

**Mock 模式（不连硬件，测试用）**：
```powershell
python bridge.py --mock --host 127.0.0.1 --port 9000
```

成功启动后会看到：
```
✓ 灵巧手已连接真机: COM5 (...)
✓ 机械臂已连接真机: agx_cando / can0 (...)
INFO:     Uvicorn running on http://127.0.0.1:9000
```

### 4. 启动 MCP Server（另一个终端）

```powershell
# 设置环境变量
$env:ROBOT_BRIDGE_URL = "http://127.0.0.1:9000"
$env:MCP_SECURITY_MODE = "lan"

# 进入 mcp_server 目录
cd mcp_server

# 启动
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

成功启动后会看到：
```
硬件代理已连接: http://127.0.0.1:9000
INFO:     Uvicorn running on http://127.0.0.1:8000
```

### 5. 配置 Claude Desktop

编辑配置文件：
- **位置**：`%APPDATA%\Claude\claude_desktop_config.json`
- **如果文件不存在**：创建一个新的

**内容**：
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

保存后**重启 Claude Desktop**。

### 6. 验证

在 Claude Desktop 里问：

```
列出可用的手势
```

应该返回 8 个手势（张开手、松手、1-5、点赞、OK）。

**测试灵巧手**：
```
执行"点赞"手势
```

**测试机械臂**（如果连了）：
```
机械臂回到零位
```

## 常见问题

### 问题 1：找不到 COM 口

**症状**：`FileNotFoundError: [Errno 2] No such file or directory: 'COM5'`

**解决**：
1. 打开设备管理器
2. 展开"端口 (COM 和 LPT)"
3. 找到 USB-Serial 设备，记下 COM 号
4. 用实际 COM 号启动：`--hand-port COM7`

### 问题 2：机械臂连接失败 - ModuleNotFoundError: No module named 'can'

**原因**：没装 CAN 依赖

**解决**：
```powershell
pip install python-can
pip install "git+https://github.com/agilexrobotics/python-can-agx-cando.git"
```

### 问题 3：灵巧手连接成功但读不到 HAND_ID

**可能原因**：
- RS485 A-B 接反了（对调试试）
- 24V 供电未接通
- 手的 ID 不是 1（出厂默认是 1）

### 问题 4：Claude Desktop 看不到工具

**检查**：
1. 配置文件路径对不对（`%APPDATA%\Claude\`）
2. JSON 格式有没有错（用 jsonlint.com 验证）
3. 有没有重启 Claude Desktop
4. 终端里 MCP Server 有没有报错

**手动验证 MCP Server**：
```powershell
curl -X POST http://127.0.0.1:8000/mcp `
  -H "Content-Type: application/json" `
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

应该返回10个工具（4个灵巧手工具 + 6个机械臂工具）。

### 问题 5：usbipd 冲突

如果之前用 usbipd 把设备转发到 WSL 了，Windows 侧看不到设备。

**解决**：
```powershell
# 查看已转发的设备
usbipd list

# 解绑（把 BUSID 换成实际的）
usbipd detach --busid 1-2
```

解绑后设备回到 Windows，才能在 Windows 上直接用。

## 对比：WSL vs Windows 原生

| 项目 | WSL（通过 usbipd） | Windows 原生 |
|------|-------------------|--------------|
| 灵巧手 | ✅ 支持 | ✅ 支持 |
| 机械臂 | ✅ 支持（socketcan） | ✅ 支持（agx_cando）|
| 设备独占 | ⚠️ 转发期间 Windows 看不到 | ✅ Windows 直接访问 |
| 性能 | 轻微开销（USB 转发） | 原生性能 |
| 配置复杂度 | 中等（需要 usbipd） | 低（直接连） |

**推荐**：如果只是测试，用 Windows 原生更简单。生产环境看需求。

## 当前 MCP 能力边界

当前 MCP 暴露 12 个工具：4 个灵巧手工具、6 个机械臂工具，以及用于联合录制包的
`skill_list`、`skill_execute`。联合录制包来自 `data/combos/`，执行必须显式确认。
`sim/skills/registry.yaml` 中的 composite 和 trajectory 技能仍未统一接入该执行入口。

`arm_reset` 只负责退出急停并重新使能，**不会移动到零位**。回零属于真实运动，
需要在现场确认安全后通过 `arm_set_joints` 下发7个目标关节角，不能把 reset 当作回零。

## 下一步

- 验证灵巧手能否执行所有 8 个手势
- 先通过 `arm_status`、`hand_status` 验证只读链路
- 由现场人员验证机械臂运动与灵巧手手势
- 后续若开放技能执行，先设计安全确认、互斥锁和审计契约
