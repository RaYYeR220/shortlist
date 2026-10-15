import hmac
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, Header, HTTPException
from mcp.server.transport_security import TransportSecuritySettings

from . import db
from .config import Settings, get_settings
from .mcp_gate import MCP_LOG, McpGate
from .mcp_servers import build_ats, build_comms


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


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    db.configure(settings.database_url)
    ats, comms = build_ats(), build_comms()
    security = _transport_security(settings)
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
        _admin(settings, x_admin_token)
        return list(MCP_LOG)

    @app.post("/spike/workspace")
    def spike_workspace(x_admin_token: str = Header(default="")) -> dict:
        _admin(settings, x_admin_token)
        from . import domain, seed
        ws = seed.create_workspace()
        b = domain.board(ws)
        return {"id": ws, "job_id": b["jobs"][0]["id"], "applications": [a["id"] for a in b["applications"]]}

    return app


app = create_app()
