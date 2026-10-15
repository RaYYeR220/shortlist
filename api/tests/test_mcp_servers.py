import pytest

from shortlist import domain, mcp_servers, seed


@pytest.fixture
def ws(engine):
    return seed.create_workspace()


async def test_tool_inventories_match_the_policy_design(engine):
    ats_names = {t.name for t in await mcp_servers.build_ats().list_tools()}
    comms_names = {t.name for t in await mcp_servers.build_comms().list_tools()}
    assert ats_names == set(mcp_servers.TOOLS["ats"])
    assert comms_names == set(mcp_servers.TOOLS["comms"])


async def test_set_stage_tool_changes_the_database(ws):
    app = domain.board(ws)["applications"][0]
    await mcp_servers.build_ats().call_tool(
        "set_stage", {"workspace_id": ws, "application_id": app["id"], "stage": "phone_screen"}
    )
    assert domain.snapshot(ws)["stages"][app["id"]] == "phone_screen"
