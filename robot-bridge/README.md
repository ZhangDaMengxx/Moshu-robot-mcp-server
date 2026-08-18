# robot-bridge

灵巧手 / 机械臂的硬件代理。跑在**连着硬件的机器**，对外暴露 HTTP，供 MCP
Server（本地或云端）调用。

260KB，是从 [VLA-HandArm](https://github.com/ZhangDaMengxx/VLA-HandArm) 拆出来的
运行时子集，驱动和标定数据同源。只跑硬件用这个；做仿真或数据管线去那边。

```
[Claude] --MCP--> [MCP Server] --HTTP--> [robot-bridge] --RS485/CAN--> [硬件]
                   本地或云端              这个仓库        插着硬件的机器
```

MCP Server 不碰硬件，只发 HTTP。驱动、技能表、可行域校验全在这里。

## 安装

```bash
git clone https://github.com/ZhangDaMengxx/robot-bridge.git
cd robot-bridge
pip install -r requirements.txt
```

Python 3.10+。真机械臂另需 `pyAgxArm`，不在 PyPI 上，从厂商处获取。

## 运行

```bash
# mock：不连硬件，先跑通链路
python bridge.py --mock --host 127.0.0.1 --port 9000

# 真机 Linux
python bridge.py --hand-port /dev/ttyUSB0 --host 127.0.0.1 --port 9000

# 真机 Windows
python bridge.py --hand-port COM5 --host 127.0.0.1 --port 9000
```

`--hand-port` 不传就读环境变量 `INSPIRE_HAND_PORT`，都没有才用默认
`/dev/ttyUSB0`。`--port` 是 HTTP 端口，别和串口混了。

不加 `--mock` 时连不上硬件会**直接启动失败**，不会静默退到 mock。这是故意的：
早先版本会偷偷降级，结果对着 mock 测了一轮"成功"，真手根本没动。

`/health` 和 `/hand/status` 都带 `mock` 字段，随时能确认当前是真机还是空跑。

### 认证

暴露到本机之外（局域网、隧道、公网）**必须**设 token：

```bash
export BRIDGE_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
python bridge.py --host 127.0.0.1 --port 9000
```

设了之后除 `/health` 外所有请求都要带 `X-Bridge-Token`。不设会放行（本地开发方便），
但这时候别开隧道 —— 拿到 URL 的人能直接驱动你的硬件。

默认绑 `127.0.0.1`。要对局域网开放才改 `--host 0.0.0.0`，改之前先把 token 设上。

## 准备硬件

驱动不区分 WSL 和原生 Ubuntu —— `usbipd attach` 之后 WSL 里看到的也是
`/dev/ttyUSB0`，pyserial 不关心底下是不是转发来的。差别只在启动前的准备步骤。

### 灵巧手（RS485 / USB 串口）

**Linux**

```bash
sudo usermod -a -G dialout $USER   # 串口权限，之后要重新登录
ls /dev/ttyUSB*                     # 确认设备可见
```

**Windows** —— 设备管理器里看 COM 号，或：

```powershell
Get-CimInstance Win32_PnPEntity | Where-Object { $_.Name -like "*COM*" }
```

**WSL** —— 需要先从 Windows 侧转发：

```powershell
usbipd list                        # 找 BUSID
usbipd attach --wsl --busid 1-2
```

`usbipd` 是**独占**转发，不是共享。转发进 WSL 期间 Windows 侧看不到这个设备；
要在 Windows 上直接跑 bridge，得先 `usbipd detach --busid 1-2` 把设备还回去。

设备号不固定（可能是 `/dev/ttyACM0`，插多个设备时枚举顺序还会变）。Linux 上更稳
的做法是用 `/dev/serial/by-id/` 下的符号链接，那个跨重启稳定。

连不上先查：24V 供电、RS485 的 A-B 有没有接反、手的 ID 是不是 1。

### 机械臂（CAN）

**Linux**：
```bash
sudo ip link set can0 up type can bitrate 1000000
```

**Windows**：需要松灵官方的 CAN 适配器和驱动，代码会自动使用 `agx_cando` 接口。

**依赖**：
```bash
# Windows 需要额外安装
pip install python-can
pip install "git+https://github.com/agilexrobotics/python-can-agx-cando.git"
pip install "git+https://github.com/agilexrobotics/pyAgxArm.git"
```

**说明**：
- WSL：使用 SocketCAN（需要内核支持）
- Windows 原生：使用 agx_cando 接口（需要松灵 CAN 适配器）
- bridge 启动时自动检测平台并选择对应接口

**完整的 Windows 部署指南**：见 [WINDOWS_DEPLOY.md](WINDOWS_DEPLOY.md)

## 接口

`GET /health` 不需要 token，其余都要。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 活性 + 是否 mock |
| GET | `/hand/status` | 连接状态、当前六关节角度 |
| POST | `/hand/angles` | 下发六关节弧度，过可行域闸 |
| GET | `/hand/gestures` | 列出可一步到位执行的手势 |
| POST | `/hand/gesture/{name}` | 执行预设手势，id 或中文别名都认 |
| GET | `/arm/status` | 机械臂状态 |
| POST | `/arm/joints` | 下发七关节弧度 |
| POST | `/arm/enable` | 使能机械臂 |
| POST | `/arm/disable` | 下使能机械臂 |
| POST | `/arm/estop` | 进入阻尼急停；无抱闸，机械臂可能下落 |
| POST | `/arm/reset` | 退出急停并重新使能；不会回零 |
| GET | `/skills` | 列出通过预检的联合录制技能 |
| POST | `/skills/execute` | 执行联合录制技能 |

```bash
curl -H "X-Bridge-Token: $BRIDGE_TOKEN" http://localhost:9000/hand/gestures
curl -X POST -H "X-Bridge-Token: $BRIDGE_TOKEN" \
     http://localhost:9000/hand/gesture/hand_open
```

手势 id 从 `/hand/gestures` 拿，别猜。

### LeRobot 录制包

从 `lerobotTest` 导入的原始录制资产放在 `data/gestures/` 和 `data/combos/`；格式、
真机注意事项和轨迹兼容性见 `data/README.md`。联合包可通过 MCP 的 `skill_list` 和
`skill_execute` 调用。执行仍会检查机械臂使能、急停状态、动作互斥和全部帧的安全范围。

### 可行域闸

拇指收进来的时候会挡住食指，食指弯不到底。`/hand/angles` 和 `/hand/gesture/`
两条路都会先查，不可行就回 **409 并说明原因**，不下发。

判据在 `sim/skills/hand_pose.py`，数据是 2026-08-06 在真手上量出来的。命令能
"做出来"是靠堵转，不是姿态安全 —— 这个闸不能绕过。

## 换硬件要动哪里

这套是按 Inspire 六自由度手 + NERO 七自由度臂标定的，换硬件不是改配置的事：

- **驱动**：`sim/inspire_hand.py`（RS485 私有协议、寄存器表、raw 0-1000 量程）、
  `sim/nero_arm.py`（CAN + pyAgxArm）要重写
- **标定数据**：`sim/skills/hand_pose.py` 里的 `RAW_MAP` / `LIMIT_HI` /
  `FEASIBLE` / `THUMB_STATES` 全是实测值，必须在新手上重新量
- **自由度**：目前 6（手）和 7（臂）写死在若干处

同款硬件换台电脑，改 `--hand-port` 就行。

## 连 MCP Server

### 单机（推荐先这么试）

bridge 和 MCP Server 同一台机器，不用隧道、不用云服务器、不用开防火墙：

```bash
# 终端 1
python bridge.py --mock --host 127.0.0.1 --port 9000

# 终端 2（在 VLA-HandArm/mcp_server 目录下）
ROBOT_BRIDGE_URL=http://127.0.0.1:9000 MCP_SECURITY_MODE=lan \
  python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Claude Desktop 的 `mcpServers` 走 stdio，不认 HTTP URL，要用 `mcp-remote` 代理
（需要 Node.js）。配置文件加：

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

重启 Claude Desktop，问它"列出可用的手势"就能验证链路。远端服务器再在 `args`
末尾加 `"--header", "X-API-Key:你的key"` —— 冒号后**不能有空格**。

### 云端 MCP Server 用本地硬件

当前推荐 FRP：Bridge 仍只监听 `127.0.0.1:9000`，frpc 将它转发到云主机的
`127.0.0.1:10005`。该端口不对公网开放，只有云端 MCP Server 能访问。

即使使用回环代理，也必须设置独立 `BRIDGE_TOKEN`。完整流程见仓库根目录的
`frp_deploy.md`。公网客户端只能访问经过 MCP API Key 鉴权的 HTTPS `/mcp`。
