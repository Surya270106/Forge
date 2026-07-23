import sys

import pytest

from packages.sdk.mcp import MCPClient


@pytest.mark.asyncio
async def test_mcp_client_stdio(tmp_path):
    # Create a fake MCP server script
    server_script = tmp_path / "fake_mcp.py"
    server_script.write_text("""
import sys
import json

for line in sys.stdin:
    req = json.loads(line)
    if req["method"] == "tools/list":
        resp = {
            "jsonrpc": "2.0",
            "id": req["id"],
            "result": {
                "tools": [{"name": "fake_tool", "description": "Fake tool"}]
            }
        }
    elif req["method"] == "tools/call":
        resp = {
            "jsonrpc": "2.0",
            "id": req["id"],
            "result": {
                "content": [{"type": "text", "text": "Fake success"}]
            }
        }
    sys.stdout.write(json.dumps(resp) + "\\n")
    sys.stdout.flush()
    """)

    client = MCPClient([sys.executable, str(server_script)])

    tools = await client.list_tools()
    assert len(tools) == 1
    assert tools[0]["name"] == "fake_tool"

    result = await client.invoke_tool("fake_tool", {})
    assert result["content"][0]["text"] == "Fake success"

    await client.close()
