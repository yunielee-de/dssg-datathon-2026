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
            report = await session.call_tool("data_quality_report", {"city": "Berlin", "limit": 5})
            locality = await session.call_tool("normalize_locality", {"locality": "Berlin- Mitte"})
            return (tools, json.loads(search.content[0].text), json.loads(nearest.content[0].text),
                    json.loads(report.content[0].text), json.loads(locality.content[0].text))


def test_server_tools_over_stdio():
    tools, search, nearest, report, locality = asyncio.run(_run())
    assert {"search_facilities", "get_facility", "find_nearest", "data_quality_report",
            "normalize_locality", "locality_variants"} <= tools
    assert report["facilities_checked"] > 0 and len(report["records_to_fix_first"]) <= 5
    assert locality["cleaned"] == "Berlin-Mitte"
    assert search["count"] == 3
    distances = [f["distance_km"] for f in nearest["facilities"]]
    assert distances and distances == sorted(distances)
