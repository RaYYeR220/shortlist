import sqlalchemy as sa
from sqlalchemy.pool import StaticPool

metadata = sa.MetaData()
_engine: sa.Engine | None = None


def configure(url: str) -> sa.Engine:
    global _engine
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
    _engine = sa.create_engine(url, **kwargs)
    metadata.create_all(_engine)
    return _engine
