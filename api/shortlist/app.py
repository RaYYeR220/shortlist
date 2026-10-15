from fastapi import FastAPI

from . import db
from .config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    db.configure(settings.database_url)
    app = FastAPI(title="Shortlist")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    return app
