import hmac
from contextlib import asynccontextmanager
from types import SimpleNamespace
from urllib.parse import urlsplit

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.transport_security import TransportSecuritySettings

from . import db
from .api import router
from .armor import ArmorGate
from .budget import Budget
from .catalog import build_catalog
from .config import Settings, get_settings
from .llm import LLM
from .mcp_gate import MCP_LOG, McpGate
from .mcp_servers import build_ats, build_comms
from .runs import ApprovalDesk, EventStore, RunService


def _transport_security(settings: Settings) -> TransportSecuritySettings:
    """MCP endpoints answer only to our own public host (and local development)."""
    public = urlsplit(settings.public_base_url)
    hosts = {public.netloc, "localhost:*", "127.0.0.1:*", "testserver"}
    origins = {f"{public.scheme}://{public.netloc}", settings.web_origin}
    return TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=sorted(hosts),
                                     allowed_origins=sorted(origins))


def _admin(settings: Settings, token: str) -> None:
    if not settings.admin_token or not hmac.compare_digest(token.encode(), settings.admin_token.encode()):
        raise HTTPException(status_code=404)


def create_app(settings: Settings | None = None, *, gate=None, llm=None) -> FastAPI:
    settings = settings or get_settings()
    db.configure(settings.database_url)
    ats, comms = build_ats(), build_comms()
    security = _transport_security(settings)
    ats_asgi = ats.streamable_http_app(stateless_http=True, json_response=True, transport_security=security)
    comms_asgi = comms.streamable_http_app(stateless_http=True, json_response=True, transport_security=security)
    gate = gate or ArmorGate(
        api_key=settings.armoriq_api_key, backend=settings.armoriq_backend, proxy=settings.armoriq_proxy,
        agent_id=settings.armoriq_agent_id, user_email=settings.agent_user_email,
        approver_email=settings.approver_email, mcp_token=settings.mcp_shared_secret,
        validity_seconds=settings.token_validity_seconds,
    )
    llm = llm or LLM(settings.llm_base_url, settings.llm_api_key)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        catalog = await build_catalog({"ats": ats, "comms": comms})
        events = EventStore()
        desk = ApprovalDesk(gate, events)
        runs = RunService(gate=gate, llm=llm, settings=settings, catalog=catalog, events=events, desk=desk)
        app.state.services = SimpleNamespace(events=events, desk=desk, runs=runs, gate=gate)
        async with ats.session_manager.run(), comms.session_manager.run():
            yield

    app = FastAPI(title="Shortlist", lifespan=lifespan)
    app.state.settings = settings
    app.state.budget = Budget()
    # No auth cookies are used (the workspace id lives in the URL), so any origin may call
    # the API — this is what lets the live demo be opened from anywhere.
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
                       allow_credentials=False)
    app.mount("/ats", McpGate(ats_asgi, secret=settings.mcp_shared_secret, name="ats"))
    app.mount("/comms", McpGate(comms_asgi, secret=settings.mcp_shared_secret, name="comms"))
    app.include_router(router)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/debug/mcp-log")
    def mcp_log(x_admin_token: str = Header(default="")) -> list[dict]:
        _admin(settings, x_admin_token)
        return list(MCP_LOG)

    return app


app = create_app()
