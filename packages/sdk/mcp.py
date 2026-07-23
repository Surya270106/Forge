import asyncio
import json
from typing import Any


class MCPClient:
    """
    Model Context Protocol (MCP) Client Adapter.
    Communicates via JSON-RPC over stdio.
    """

    def __init__(self, target_command: list[str]):
        self.target_command = target_command
        self.process: asyncio.subprocess.Process | None = None
        self._msg_id = 0

    async def connect(self):
        self.process = await asyncio.create_subprocess_exec(
            *self.target_command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        # In a real implementation we would send 'initialize' here.

    async def _send_request(self, method: str, params: dict) -> dict:
        assert self.process and self.process.stdin and self.process.stdout
        self._msg_id += 1
        req = {"jsonrpc": "2.0", "id": self._msg_id, "method": method, "params": params}
        req_bytes = json.dumps(req).encode() + b"\n"
        self.process.stdin.write(req_bytes)
        await self.process.stdin.drain()

        line = await self.process.stdout.readline()
        if not line:
            raise RuntimeError("MCP Server disconnected")
        return json.loads(line.decode().strip())

    async def list_tools(self) -> list[dict[str, Any]]:
        if not self.process:
            await self.connect()
        res = await self._send_request("tools/list", {})
        return res.get("result", {}).get("tools", [])

    async def invoke_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if not self.process:
            await self.connect()
        res = await self._send_request("tools/call", {"name": tool_name, "arguments": arguments})
        return res.get("result", {})

    async def close(self):
        if self.process:
            self.process.terminate()
            await self.process.wait()
