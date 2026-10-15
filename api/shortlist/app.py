from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from mcp.server.transport_security import TransportSecuritySettings

from . import db
from .config import Settings, get_settings
from .mcp_gate import MCP_LOG, McpGate
from .mcp_servers import build_ats, build_comms


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    db.configure(settings.database_url)
    ats, comms = build_ats(), build_comms()
    security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    ats_asgi = ats.streamable_http_app(stateless_http=True, json_response=True, transport_security=security)
    comms_asgi = comms.streamable_http_app(stateless_http=True, json_response=True, transport_security=security)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with ats.session_manager.run(), comms.session_manager.run():
            yield

    app = FastAPI(title="Shortlist", lifespan=lifespan)
    app.state.settings = settings
    app.state.mcp_servers = {"ats": ats, "comms": comms}
    app.mount("/ats", McpGate(ats_asgi, secret=settings.mcp_shared_secret, name="ats"))
    app.mount("/comms", McpGate(comms_asgi, secret=settings.mcp_shared_secret, name="comms"))

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/debug/mcp-log")
    def mcp_log(x_admin_token: str = Header(default="")) -> list[dict]:
        if not settings.admin_token or x_admin_token != settings.admin_token:
            raise HTTPException(status_code=404)
        return list(MCP_LOG)

    return app


app = create_app()
