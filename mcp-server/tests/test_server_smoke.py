"""End-to-end: start server.py over stdio with the CSV backend and call tools as an MCP client."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = Path(__file__).resolve().parents[1] / "server.py"


async def _run():
    params = StdioServerParameters(
        command=sys.executable, args=[str(SERVER)], env={**os.environ, "FDP_BACKEND": "csv"}
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name for t in (await session.list_tools()).tools}
            search = await session.call_tool("search_facilities", {"city": "Berlin", "limit": 3})
            nearest = await session.call_tool("find_nearest", {"postal_code": "13407", "radius_km": 3})
            return tools, json.loads(search.content[0].text), json.loads(nearest.content[0].text)


def test_server_tools_over_stdio():
    tools, search, nearest = asyncio.run(_run())
    assert {"search_facilities", "get_facility", "find_nearest"} <= tools
    assert search["count"] == 3
    distances = [f["distance_km"] for f in nearest["facilities"]]
    assert distances and distances == sorted(distances)
