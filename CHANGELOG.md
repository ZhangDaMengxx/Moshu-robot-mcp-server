# Changelog

## 2026-08-17

### MCP Server 重构

- 将 MCP 实现拆分为工具注册表、JSON-RPC 协议层和 Streamable HTTP 传输层。
- 保留 `/mcp` 地址、现有10个工具名称、`X-API-Key` 鉴权和旧协议客户端兼容。
- 工具名称、描述、输入 JSON Schema、处理器及安全提示改为单一注册源。
- 增加契约导出入口，为后续 Python SDK 和自动文档生成提供输入。
- 新增契约、参数校验、协议协商、通知、会话和传输回归测试；共11项测试通过。

### 部署与文档

- 将当前 `127.0.0.1:10005` FRP 回环代理设为生产部署基准，公网只开放 HTTPS MCP入口。
- 明确 FRP token、Bridge token、MCP API key 必须相互独立并定期轮换。
- 归档旧 Cloudflare 临时隧道、公开 `8000`、旧 REST MCP 路径和“6个工具”说明。
- 明确 `arm_reset` 只退出急停并重新使能，不执行机械臂回零。

### 下一步

- 在云端重新构建并部署 MCP Server 镜像，完成只读端到端验证。
- 从导出的工具契约建立 `sdk/python`，SDK 只连接 `/mcp`，不直连 Bridge。
