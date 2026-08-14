# 使用 FRP 连接云端 MCP Server 与 WSL Bridge

本文适用于以下固定拓扑：

```text
AI 客户端
    | HTTPS :443
    v
云服务器 Nginx -> MCP Server :8000
                         |
                         | HTTP 127.0.0.1:19000
                         v
                    frps :7000 <========== frpc（WSL）
                                                   |
                                                   | HTTP 127.0.0.1:9000
                                                   v
                                                Bridge -> 硬件
```

关键安全约束：

- 云端 `19000` 只监听 `127.0.0.1`，不向公网开放。
- MCP Server 容器使用 host 网络，才能访问云主机的 `127.0.0.1:19000`。
- 公网只开放 FRP 控制端口 `7000`、HTTPS `443`，以及签发证书/跳转用的 `80`。
- FRP token、Bridge token、MCP API key 必须使用三个不同的随机值。

## 1. 准备三个密钥

分别执行三次，不要复用输出：

```bash
openssl rand -hex 32
```

记为：

```text
FRP_TOKEN       frpc 连接 frps 使用
BRIDGE_TOKEN    MCP Server 调用 Bridge 使用
MCP_API_KEY     AI 客户端调用 MCP Server 使用
```

仓库中曾出现过的旧 token 和简单管理密码不再使用。

## 2. 云服务器安装并配置 frps

以下示例固定使用 FRP `v0.61.1`、Linux x86-64。先执行 `uname -m`，输出应为
`x86_64`；ARM 服务器需要下载对应的 `linux_arm64` 包。

```bash
cd /tmp
wget https://github.com/fatedier/frp/releases/download/v0.61.1/frp_0.61.1_linux_amd64.tar.gz
tar xzf frp_0.61.1_linux_amd64.tar.gz
sudo install -m 755 frp_0.61.1_linux_amd64/frps /usr/local/bin/frps
sudo mkdir -p /etc/frp
```

在仓库根目录从模板生成实际配置。`frps.toml` 已被 `.gitignore` 忽略：

```bash
cp frps.toml.example frps.toml
nano frps.toml
```

替换这一项：

```toml
auth.token = "你的新 FRP_TOKEN"
```

将生成的 `frps.toml` 上传到云服务器，然后安装：

```bash
sudo install -m 600 frps.toml /etc/frp/frps.toml
```

最终必须保留以下限制：

```toml
proxyBindAddr = "127.0.0.1"
allowPorts = [{ start = 19000, end = 19000 }]
transport.tls.force = true
```

安装完 FRP 后先让 frps 校验配置：

```bash
sudo /usr/local/bin/frps verify -c /etc/frp/frps.toml
```

创建 systemd 服务：

```bash
sudo tee /etc/systemd/system/frps.service >/dev/null <<'EOF'
[Unit]
Description=FRP server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/frps -c /etc/frp/frps.toml
Restart=on-failure
RestartSec=5s
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now frps
sudo systemctl status frps --no-pager
```

此时还没有 frpc 接入，所以 `19000` 暂时不会监听，这是正常现象。

## 3. WSL 启动 Bridge

在 WSL 的项目目录执行。真机模式不要加 `--mock`：

```bash
cd /home/zhang123/ros2_ws/robot-mcp-server/robot-bridge
export BRIDGE_TOKEN='你的新 BRIDGE_TOKEN'
~/miniconda3/envs/lerobot/bin/python bridge.py \
  --host 127.0.0.1 \
  --port 9000 \
  --hand-port /dev/ttyUSB0
```

另开一个 WSL 终端验证：

```bash
curl http://127.0.0.1:9000/health
curl -H "X-Bridge-Token: 你的新 BRIDGE_TOKEN" \
  http://127.0.0.1:9000/hand/status
```

`/health` 不检查 Bridge token，因此第二条命令才是鉴权验证。先以前台方式确认硬件连接正常，再考虑用 systemd 或其他进程管理器托管 Bridge。

## 4. WSL 安装并启动 frpc

WSL 同样使用 `v0.61.1`：

```bash
cd /tmp
wget https://github.com/fatedier/frp/releases/download/v0.61.1/frp_0.61.1_linux_amd64.tar.gz
tar xzf frp_0.61.1_linux_amd64.tar.gz
sudo install -m 755 frp_0.61.1_linux_amd64/frpc /usr/local/bin/frpc
sudo mkdir -p /etc/frp
```

在 WSL 的仓库根目录从模板生成实际配置：

```bash
cp frpc.toml.example frpc.toml
nano frpc.toml
```

替换：

```toml
serverAddr = "云服务器公网 IP"
auth.token = "与 frps 完全相同的 FRP_TOKEN"
```

安装配置并先以前台方式验证：

```bash
sudo install -m 600 frpc.toml /etc/frp/frpc.toml
sudo /usr/local/bin/frpc verify -c /etc/frp/frpc.toml
sudo /usr/local/bin/frpc -c /etc/frp/frpc.toml
```

看到 `start proxy success` 后按 `Ctrl+C`，再创建服务：

```bash
sudo tee /etc/systemd/system/frpc.service >/dev/null <<'EOF'
[Unit]
Description=FRP client for robot Bridge
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/frpc -c /etc/frp/frpc.toml
Restart=always
RestartSec=5s
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now frpc
sudo systemctl status frpc --no-pager
```

如果 WSL 尚未启用 systemd，在 Windows 用户目录的 `.wslconfig` 里不处理；应在
WSL 内编辑 `/etc/wsl.conf`：

```ini
[boot]
systemd=true
```

然后在 PowerShell 执行 `wsl --shutdown`，重新进入 WSL。

## 5. 在云服务器验证 FRP 隧道

```bash
sudo journalctl -u frps -n 100 --no-pager
sudo ss -tlnp | grep ':19000'
```

正确结果必须是 `127.0.0.1:19000`。如果显示 `0.0.0.0:19000`，立即停止 frps，
检查 `/etc/frp/frps.toml` 中的 `proxyBindAddr`。

验证隧道和 Bridge 鉴权：

```bash
# 只验证隧道连通性
curl http://127.0.0.1:19000/health

# 错误 token 应返回 401
curl -i -H 'X-Bridge-Token: wrong-token' \
  http://127.0.0.1:19000/hand/status

# 正确 token 应返回 200
curl -i -H 'X-Bridge-Token: 你的新 BRIDGE_TOKEN' \
  http://127.0.0.1:19000/hand/status
```

## 6. 云服务器配置 MCP Server

在云服务器的 `mcp_server` 目录创建 `.env`：

```bash
ROBOT_BRIDGE_URL=http://127.0.0.1:19000
ROBOT_BRIDGE_TOKEN=你的新_BRIDGE_TOKEN
ROBOT_HEARTBEAT_INTERVAL=5
ROBOT_HEARTBEAT_TIMEOUT=2
MCP_SECURITY_MODE=public
MCP_API_KEYS=你的新_MCP_API_KEY
MCP_CORS_ORIGINS=https://你的域名
```

仓库已经提供 `mcp_server/docker-compose.frp.yml`。它使用 host 网络，并把 MCP
Server 限制在云主机的 `127.0.0.1:8000`：

```yaml
services:
  mcp-server:
    build: .
    container_name: mcp-robot-server
    network_mode: host
    env_file:
      - .env
    command:
      - uvicorn
      - app.main:app
      - --host
      - 127.0.0.1
      - --port
      - "8000"
    restart: unless-stopped
```

不要使用原来面向本地开发的 `docker-compose.yml`。启动并验证云端配置：

```bash
docker compose -f docker-compose.frp.yml up -d --build
docker logs --tail 100 mcp-robot-server
curl http://127.0.0.1:8000/health
```

必须在日志中看到：

```text
安全模式: public
连接硬件代理: http://127.0.0.1:19000
Bridge 心跳已启动: interval=5.0s timeout=2.0s
```

MCP Server 每 5 秒探测一次 Bridge。`curl http://127.0.0.1:8000/health`
返回中的 `bridge` 字段会给出当前连接状态：

```json
{
  "status": "degraded",
  "bridge": {
    "connected": false,
    "heartbeat_interval_seconds": 5.0,
    "consecutive_failures": 2,
    "last_seen": "2026-08-14T06:20:31+00:00",
    "last_error": "ConnectError: All connection attempts failed"
  }
}
```

Bridge 恢复后，下一次心跳会自动把 `connected` 恢复为 `true`。运动命令遇到
网络错误不会自动重试，避免响应丢失时重复执行动作。

不要依赖 `auto` 模式。容器通常得到私网 IP，`auto` 可能把云端错误判断为无需 API
Key 的 `lan` 模式。

## 7. 使用 Nginx 提供 HTTPS

先把域名 A 记录指向云服务器公网 IP。安装 Nginx：

```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
```

创建 `/etc/nginx/sites-available/robot-mcp`：

```nginx
server {
    listen 80;
    server_name mcp.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_read_timeout 3600s;
    }
}
```

把 `mcp.example.com` 换成真实域名，然后：

```bash
sudo ln -s /etc/nginx/sites-available/robot-mcp /etc/nginx/sites-enabled/robot-mcp
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d mcp.example.com
```

最终 MCP 地址为：

```text
https://mcp.example.com/mcp
```

## 8. 防火墙和云安全组

UFW：

```bash
sudo ufw allow OpenSSH
sudo ufw allow 7000/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

云厂商安全组同样只开放：

| 端口 | 来源 | 用途 |
| --- | --- | --- |
| 22 | 你的管理 IP | SSH |
| 7000 | 尽量限制为本地公网出口 IP | frpc 连接 |
| 80 | `0.0.0.0/0` | 证书签发和 HTTPS 跳转 |
| 443 | `0.0.0.0/0` | MCP HTTPS |

不要开放 `19000` 和 `8000`。

## 9. 最终验证

从外部机器执行：

```bash
curl https://mcp.example.com/health

curl -X POST https://mcp.example.com/mcp \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: 你的新 MCP_API_KEY' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

验证未带 API key 的 MCP 请求返回 `401`：

```bash
curl -i -X POST https://mcp.example.com/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## 10. 常见排障

### frpc 报端口不允许

确认云端配置是：

```toml
allowPorts = [{ start = 19000, end = 19000 }]
```

修改后执行 `sudo systemctl restart frps`。

### 云端没有监听 19000

依次检查：

```bash
# WSL
sudo systemctl status frpc --no-pager
sudo journalctl -u frpc -n 100 --no-pager

# 云服务器
sudo systemctl status frps --no-pager
sudo journalctl -u frps -n 100 --no-pager
```

### MCP 健康检查显示 degraded

在云服务器由近到远测试：

```bash
curl http://127.0.0.1:19000/health
curl -H 'X-Bridge-Token: 你的新 BRIDGE_TOKEN' \
  http://127.0.0.1:19000/hand/status
docker logs --tail 100 mcp-robot-server
```

### WSL 重启后 frpc 没有启动

确认 WSL 已启用 systemd，并检查：

```bash
systemctl is-enabled frpc
systemctl status frpc --no-pager
```

注意：WSL 完全退出后不会像独立 Linux 主机一样永久运行。需要远程控制硬件时，WSL、
Bridge 和 frpc 都必须处于运行状态。
