# MCP 契约导出

工具契约的单一真源是 `app/mcp/registry.py`。文档站或 Python SDK 生成代码前，执行：

```bash
cd mcp_server
python -m app.mcp.export_contract > contracts/tools.json
```

`tools.json` 是生成物，不应手工维护。正式发布 SDK 时，由 CI 导出并作为构建输入。
