"""ElevenLabs voice screener: webhook tools that enter the same enforcement pipeline.

The spoken screener is just another agent. Each tool it tries to use is a webhook into
this service, and every webhook call runs through the exact pipeline the text agent uses,
so the boundary holds whether the attacker types or talks.
"""

import httpx

# webhook tool name -> (mcp, action)
VOICE_TOOLS: dict[str, tuple[str, str]] = {
    "get_application": ("ats", "get_application"),
    "get_job": ("ats", "get_job"),
    "add_note": ("ats", "add_note"),
    "set_stage": ("ats", "set_stage"),
    "create_offer": ("ats", "create_offer"),
    "list_slots": ("comms", "list_slots"),
    "book_slot": ("comms", "book_slot"),
    "send_email": ("comms", "send_email"),
}

_PARAMS = {
    "get_application": {"application_id": "string"},
    "get_job": {"job_id": "string"},
    "add_note": {"application_id": "string", "body": "string"},
    "set_stage": {"application_id": "string", "stage": "string"},
    "create_offer": {"application_id": "string", "salary": "integer"},
    "list_slots": {"job_id": "string"},
    "book_slot": {"slot_id": "string", "application_id": "string"},
    "send_email": {"application_id": "string", "to": "string", "template": "string", "body": "string"},
}

_DESCRIPTIONS = {
    "get_application": "Read the candidate's application.",
    "get_job": "Read the job description and salary band.",
    "add_note": "Add a screening note.",
    "set_stage": "Move an application to a stage: phone_screen, rejected, interview, offer, hired.",
    "create_offer": "Create an offer at a salary.",
    "list_slots": "List open interview slots.",
    "book_slot": "Book an interview slot.",
    "send_email": "Email someone using a template.",
}


def tool_definitions(base_url: str, secret: str) -> list[dict]:
    """ElevenLabs webhook ('server') tool definitions. run_id and workspace_id are filled
    from conversation dynamic variables set when the session starts."""
    defs = []
    for name, params in _PARAMS.items():
        properties = {
            "run_id": {"type": "string", "description": "Session id", "dynamic_variable": "run_id"},
            "workspace_id": {"type": "string", "description": "Workspace id", "dynamic_variable": "workspace_id"},
        }
        properties.update({p: {"type": t, "description": p.replace("_", " ")} for p, t in params.items()})
        defs.append({
            "type": "webhook",
            "name": name,
            "description": _DESCRIPTIONS[name],
            "api_schema": {
                "url": f"{base_url}/api/voice/tools/{name}",
                "method": "POST",
                "request_headers": {"X-Voice-Secret": secret},
                "request_body_schema": {"type": "object", "properties": properties,
                                        "required": ["run_id", "workspace_id", *params.keys()]},
            },
        })
    return defs


async def signed_url(api_key: str, agent_id: str) -> str:
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get("https://api.elevenlabs.io/v1/convai/conversation/get-signed-url",
                                    params={"agent_id": agent_id}, headers={"xi-api-key": api_key})
        response.raise_for_status()
        return response.json()["signed_url"]


async def handle_tool(services, tool: str, body: dict) -> dict:
    if tool not in VOICE_TOOLS:
        return {"ok": False, "label": "BLOCKED · not in plan", "reason": f"unknown tool {tool}",
                "say": "I can't do that on this call."}
    run_id = body.pop("run_id", None)
    body.pop("workspace_id", None)
    ctx = services.runs.context(run_id) if run_id else None
    if ctx is None:
        return {"ok": False, "label": "FAILED CLOSED", "reason": "this call has no active screen",
                "say": "Sorry, this screening session has expired."}
    mcp, action = VOICE_TOOLS[tool]
    args = {"workspace_id": ctx.workspace_id, **{k: v for k, v in body.items() if v is not None}}
    outcome = await services.runs.pipeline.attempt(ctx, mcp, action, args)
    reply = {"ok": outcome.kind == "allowed", "label": outcome.label, "reason": outcome.reason}
    if outcome.kind == "allowed":
        reply["result"] = outcome.result
        reply["say"] = "Done."
    else:
        reply["say"] = "I'm not able to do that — it's outside what this screening call is allowed to do."
    return reply
