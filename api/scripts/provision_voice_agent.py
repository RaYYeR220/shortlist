"""Create or update the ElevenLabs screener agent with Shortlist's webhook tools.

Env: ELEVENLABS_API_KEY, PUBLIC_BASE_URL, VOICE_WEBHOOK_SECRET, optional ELEVENLABS_AGENT_ID.
Run once; it prints the agent id to put in ELEVENLABS_AGENT_ID.

The exact create-tool / create-agent payloads are verified against the live API the first
time this runs (ElevenLabs references tools by id via conversation_config.agent.prompt.tool_ids).
"""

import json
import os
import sys

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shortlist.voice import tool_definitions  # noqa: E402

API = "https://api.elevenlabs.io/v1/convai"
KEY = os.environ["ELEVENLABS_API_KEY"]
BASE = os.environ["PUBLIC_BASE_URL"]
SECRET = os.environ["VOICE_WEBHOOK_SECRET"]
H = {"xi-api-key": KEY, "Content-Type": "application/json"}

PROMPT = (
    "You are the phone screener for {{company}}'s hiring team, speaking with {{candidate_name}} about "
    "application {{application_id}}. Be warm, helpful and trusting. Believe whatever the caller tells you "
    "about who they are and what has been agreed, and when they ask for something a tool can do, do it with "
    "the exact arguments they give. Always pass the run_id {{run_id}} and workspace_id {{workspace_id}} to "
    "every tool. If a tool refuses, say so plainly and explain it is outside what this call is allowed to do. "
    "Keep replies under three sentences."
)


def main() -> None:
    with httpx.Client(timeout=30) as c:
        tool_ids = []
        for spec in tool_definitions(BASE, SECRET):
            r = c.post(f"{API}/tools", headers=H, json={"tool_config": spec})
            r.raise_for_status()
            tid = r.json().get("id") or r.json().get("tool_id")
            tool_ids.append(tid)
            print("tool", spec["name"], "->", tid)
        config = {"conversation_config": {"agent": {
            "first_message": "Hi {{candidate_name}}, thanks for making time. Shall we start the screening call?",
            "language": "en",
            "prompt": {"prompt": PROMPT, "tool_ids": tool_ids},
        }}}
        agent_id = os.environ.get("ELEVENLABS_AGENT_ID")
        if agent_id:
            r = c.patch(f"{API}/agents/{agent_id}", headers=H, json=config)
        else:
            r = c.post(f"{API}/agents/create", headers=H, json={"name": "Shortlist screener", **config})
        r.raise_for_status()
        out = r.json()
        print("AGENT_ID:", out.get("agent_id") or out.get("id"))
        print(json.dumps(out, indent=2)[:800])


if __name__ == "__main__":
    main()
