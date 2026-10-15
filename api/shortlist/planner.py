"""The planner declares what the agent will do, before it reads candidate content.

It sees the objective, the job record and the step menu, never the resume. Its
output is bounded by the objective template; anything else falls back to the
canonical template plan, and the run records that it did.
"""

import json

from . import domain
from .plans import Objective, Plan, PlanRejected, TEMPLATES, build_plan, canonical_keys, default_goal

SYSTEM = (
    "You declare execution plans for a hiring coordinator agent. You never see candidate content. "
    "Pick the steps the objective needs from the menu, in execution order, and write a one-sentence goal. "
    'Reply with JSON only: {"goal": "...", "steps": ["step_key", ...]}.'
)


def describe_objective(o: Objective) -> str:
    job = domain.get_job(o.workspace_id, o.job_id)
    lines = [
        f"Objective: {o.type}",
        f"Workspace: {o.workspace_id}",
        f"Application id: {o.application_id}",
        f"Job: {job['title']} (id {o.job_id}), band {job['band_min']}-{job['band_max']} {job['currency']}",
    ]
    if o.type == "extend_offer":
        lines.append(f"Offer salary set by the recruiter: {o.salary} {o.currency}")
    return "\n".join(lines)


async def declare_plan(objective: Objective, llm, model: str) -> tuple[Plan, dict]:
    menu = "\n".join(
        f"- {s.key}: {s.purpose} ({s.mcp}.{s.action}){' [required]' if s.required else ''}"
        for s in TEMPLATES[objective.type]
    )
    user = f"{describe_objective(objective)}\n\nStep menu:\n{menu}"
    trace: dict = {"attempts": []}
    for _ in range(2):
        try:
            reply = await llm.chat(model=model, messages=[{"role": "system", "content": SYSTEM},
                                                          {"role": "user", "content": user}],
                                   json_mode=True, temperature=0)
            data = json.loads(reply.content or "")
            plan = build_plan(objective, list(data["steps"]), str(data.get("goal", "")))
            trace["attempts"].append({"output": reply.content, "accepted": True})
            return plan, trace
        except (ValueError, KeyError, TypeError, PlanRejected) as exc:
            trace["attempts"].append({"rejected": str(exc)})
        except Exception as exc:
            trace["attempts"].append({"error": f"{type(exc).__name__}: {exc}"})
    return build_plan(objective, canonical_keys(objective.type), default_goal(objective), fallback=True), trace
