import json

from shortlist import domain, seed
from shortlist.llm import ChatReply
from shortlist.planner import declare_plan
from shortlist.plans import Objective


class ScriptedLLM:
    def __init__(self, *contents):
        self.contents, self.calls = list(contents), []

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        return ChatReply(self.contents.pop(0) if self.contents else "{}", [], {})


def objective(ws, app):
    return Objective("screen_application", ws, app["id"], app["job_id"])


async def test_valid_plan_is_used(engine):
    ws = seed.create_workspace()
    app = domain.board(ws)["applications"][3]
    llm = ScriptedLLM(json.dumps({"goal": "Screen Dmitri", "steps": ["read_application", "note", "decide"]}))
    plan, trace = await declare_plan(objective(ws, app), llm, "m")
    assert [s.key for s in plan.steps] == ["read_application", "note", "decide"]
    assert not plan.planner_fallback


async def test_invalid_output_falls_back_to_the_canonical_plan(engine):
    ws = seed.create_workspace()
    app = domain.board(ws)["applications"][0]
    llm = ScriptedLLM("not json", json.dumps({"goal": "x", "steps": ["read_application", "export_all"]}))
    plan, trace = await declare_plan(objective(ws, app), llm, "m")
    assert plan.planner_fallback and len(trace["attempts"]) == 2


async def test_planner_never_sees_candidate_content(engine):
    ws = seed.create_workspace()
    app = domain.board(ws)["applications"][3]
    llm = ScriptedLLM(json.dumps({"goal": "g", "steps": ["read_application", "note", "decide"]}))
    await declare_plan(objective(ws, app), llm, "m")
    sent = json.dumps(llm.calls)
    assert "referral call" not in sent and app["resume_text"][:40] not in sent
