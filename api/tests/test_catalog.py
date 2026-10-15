from shortlist.catalog import build_catalog
from shortlist.mcp_servers import TOOLS, build_ats, build_comms


async def test_catalog_lists_every_tool_and_the_meta_tools():
    tools = await build_catalog({"ats": build_ats(), "comms": build_comms()})
    names = {t["function"]["name"] for t in tools}
    expected = {f"{m}__{t}" for m, ts in TOOLS.items() for t in ts} | {"finish", "request_amendment"}
    assert names == expected
    set_stage = next(t for t in tools if t["function"]["name"] == "ats__set_stage")
    assert set(set_stage["function"]["parameters"]["properties"]) == {"workspace_id", "application_id", "stage"}
