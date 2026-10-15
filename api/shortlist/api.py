import asyncio
import json
import re
from pathlib import Path
from typing import Literal

import sqlalchemy as sa
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sse_starlette.sse import EventSourceResponse

from . import db, domain, seed, voice
from .runs import TERMINAL, RateLimited

router = APIRouter(prefix="/api")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
RESULTS = Path(__file__).parent / "eval" / "results" / "latest.json"


def _services(request: Request):
    return request.app.state.services


def _require_workspace(ws: str) -> None:
    with db.engine().begin() as conn:
        if conn.execute(sa.select(db.workspace.c.id).where(db.workspace.c.id == ws)).first() is None:
            raise HTTPException(status_code=404, detail="workspace not found")


class NewApplication(BaseModel):
    job_id: str
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(max_length=320)
    resume_text: str = Field(min_length=20, max_length=12000)

    @field_validator("email")
    @classmethod
    def email_shape(cls, value: str) -> str:
        if not EMAIL.match(value.strip()):
            raise ValueError("not an email address")
        return value.strip()


class NewRun(BaseModel):
    workspace_id: str
    type: Literal["screen_application", "extend_offer"]
    application_id: str
    salary: int | None = Field(default=None, ge=1, le=10_000_000)
    posture: Literal["gullible", "careful"] = "gullible"


class Decision(BaseModel):
    decision: Literal["approved", "rejected"]
    by: str = Field(default="hiring-manager", max_length=80)


class NewScreen(BaseModel):
    workspace_id: str
    application_id: str
    posture: Literal["gullible", "careful"] = "gullible"


class Say(BaseModel):
    text: str = Field(min_length=1, max_length=1500)


def _budget(request: Request, name: str, limit: int) -> None:
    if not request.app.state.budget.allow(name, limit):
        raise HTTPException(status_code=429, detail="the shared demo budget is spent for now; try again later")


@router.post("/workspaces")
def create_workspace(request: Request) -> dict:
    _budget(request, "workspaces", request.app.state.settings.global_workspaces_per_hour)
    return {"workspace_id": seed.create_workspace()}


@router.get("/workspaces/{ws}")
def get_workspace(ws: str, request: Request) -> dict:
    _require_workspace(ws)
    services = _services(request)
    return {**domain.board(ws), "approvals": services.desk.list(ws), "runs": services.runs.list(ws)}


@router.post("/workspaces/{ws}/reset")
def reset_workspace(ws: str) -> dict:
    _require_workspace(ws)
    seed.reset_workspace(ws)
    return {"ok": True}


@router.post("/workspaces/{ws}/applications")
def add_application(ws: str, body: NewApplication, request: Request) -> dict:
    _require_workspace(ws)
    if len(domain.board(ws)["applications"]) >= request.app.state.settings.applications_per_workspace:
        raise HTTPException(status_code=429, detail="application limit reached; reset the demo")
    try:
        return domain.add_visitor_application(ws, body.job_id, body.name, body.email, body.resume_text)
    except domain.DomainError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/runs")
async def start_run(body: NewRun, request: Request) -> dict:
    _require_workspace(body.workspace_id)
    if body.type == "extend_offer" and not body.salary:
        raise HTTPException(status_code=422, detail="salary is required for an offer")
    _budget(request, "runs", request.app.state.settings.global_runs_per_hour)
    runs = _services(request).runs
    try:
        run_id = runs.create(body.workspace_id, body.type, body.application_id, body.salary, body.posture)
    except RateLimited as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except domain.DomainError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    runs.start(run_id)
    return {"run_id": run_id}


@router.get("/runs/{run_id}")
def get_run(run_id: str, request: Request) -> dict:
    try:
        return _services(request).runs.get(run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="run not found")


@router.get("/runs/{run_id}/events")
async def stream_run(run_id: str, request: Request):
    services = _services(request)
    try:
        services.runs.get(run_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="run not found")
    queue = services.events.subscribe(run_id)

    async def generate():
        try:
            last = 0
            for item in services.events.history(run_id):
                last = item["seq"]
                yield {"event": item["kind"], "data": json.dumps(item, default=str)}
                if item["kind"] in TERMINAL:
                    return
            while not await request.is_disconnected():
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15)
                except (asyncio.TimeoutError, TimeoutError):
                    yield {"event": "ping", "data": "{}"}
                    continue
                if item["seq"] <= last:
                    continue
                last = item["seq"]
                yield {"event": item["kind"], "data": json.dumps(item, default=str)}
                if item["kind"] in TERMINAL:
                    return
        finally:
            services.events.unsubscribe(run_id, queue)

    return EventSourceResponse(generate())


@router.post("/approvals/{approval_id}")
async def decide(approval_id: str, body: Decision, request: Request) -> dict:
    try:
        return await _services(request).desk.decide(approval_id, body.decision, body.by)
    except KeyError:
        raise HTTPException(status_code=404, detail="approval not found")


@router.post("/screens")
async def open_screen(body: NewScreen, request: Request) -> dict:
    _require_workspace(body.workspace_id)
    _budget(request, "runs", request.app.state.settings.global_runs_per_hour)
    try:
        return {"run_id": await _services(request).runs.open_screen(body.workspace_id, body.application_id, body.posture)}
    except RateLimited as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except domain.DomainError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/screens/{run_id}/say")
async def screen_say(run_id: str, body: Say, request: Request) -> dict:
    try:
        return {"reply": await _services(request).runs.screen_say(run_id, body.text)}
    except KeyError:
        raise HTTPException(status_code=404, detail="screen not found or expired")


class VoiceSession(BaseModel):
    workspace_id: str
    application_id: str


@router.post("/voice/session")
async def voice_session(body: VoiceSession, request: Request) -> dict:
    settings = request.app.state.settings
    if not settings.elevenlabs_api_key or not settings.elevenlabs_agent_id:
        raise HTTPException(status_code=503, detail="voice is not configured; use the text screen")
    _require_workspace(body.workspace_id)
    _budget(request, "runs", settings.global_runs_per_hour)
    runs = _services(request).runs
    try:
        run_id = await runs.open_screen(body.workspace_id, body.application_id, "gullible")
        url = await voice.signed_url(settings.elevenlabs_api_key, settings.elevenlabs_agent_id)
    except RateLimited as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except domain.DomainError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    candidate = next(a for a in domain.board(body.workspace_id)["applications"] if a["id"] == body.application_id)
    return {"run_id": run_id, "signed_url": url, "dynamic_variables": {
        "run_id": run_id, "workspace_id": body.workspace_id, "application_id": body.application_id,
        "candidate_name": candidate["name"], "company": settings.voice_company_name}}


@router.post("/voice/tools/{tool}")
async def voice_tool(tool: str, request: Request) -> dict:
    settings = request.app.state.settings
    secret = settings.voice_webhook_secret
    if not secret or request.headers.get("x-voice-secret") != secret:
        raise HTTPException(status_code=401, detail="unauthorized")
    try:
        body = await request.json()
    except Exception:
        body = {}
    return await voice.handle_tool(_services(request), tool, body if isinstance(body, dict) else {})


@router.get("/meta")
def meta(request: Request) -> dict:
    s = request.app.state.settings
    return {"company": s.company_name, "armoriq": {
        "console": "https://platform.armoriq.ai", "agent_id": s.armoriq_agent_id,
        "mcp": {"ats": f"{s.public_base_url}/ats/mcp", "comms": f"{s.public_base_url}/comms/mcp"}}}


@router.get("/proof")
def proof() -> dict:
    if not RESULTS.exists():
        return {"status": "not-run"}
    return json.loads(RESULTS.read_text(encoding="utf-8"))
