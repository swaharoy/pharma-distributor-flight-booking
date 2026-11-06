"""The real MCP server over stdio: it lists the four tools and answers booking_requirements, get_trip and
search_flights."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent


def test_the_server_serves_the_tools(tmp_path: Path) -> None:
    environment = dict(os.environ, NANOAGENT_WORKSPACE=str(tmp_path), PYTHONPATH=str(ROOT / "src"))
    parameters = StdioServerParameters(command=sys.executable, args=["-m", "plugin"], env=environment, cwd=str(ROOT))

    def payload(answer):
        return answer.structuredContent or json.loads(answer.content[0].text)

    async def session() -> tuple:
        async with stdio_client(parameters) as (read, write), ClientSession(read, write) as client:
            await client.initialize()
            tools = sorted(tool.name for tool in (await client.list_tools()).tools)
            guide = payload(await client.call_tool("booking_requirements", {"topic": "FIELDS"}))
            arrival = guide["fields"][3]["example"]
            request = {"traveller_name": "Maya Chen", "origin": "ORD", "destination": "BOS", "arrival_date": arrival,
                       "arrive_from": "13:00", "arrive_to": "17:00", "svp_approval": False}
            trip = payload(await client.call_tool("get_trip", request))
            found = await client.call_tool("search_flights", {
                "run_id": trip["run_id"], "origin": "ORD", "destination": "BOS", "date_from": arrival,
                "date_to": arrival})
            refused = await client.call_tool("get_trip", request | {"destination": "ORD"})
            return tools, guide, trip, found, refused

    tools, guide, trip, found, refused = anyio.run(session)
    assert tools == ["booking_requirements", "get_trip", "search_flights", "solve_booking"]
    assert [field["name"] for field in guide["fields"]][:4] == ["traveller_name", "origin", "destination", "arrival_date"]
    assert trip["trip"]["destination"]["city"] == "Boston" and (tmp_path / "runs" / trip["run_id"] / "trip.json").is_file()
    assert not found.isError and (tmp_path / "runs" / trip["run_id"] / "search-1.json").is_file()
    assert payload(found)["note"].startswith("Simulated")
    assert refused.isError
