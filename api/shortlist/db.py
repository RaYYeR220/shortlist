import secrets
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.pool import StaticPool

JSONType = sa.JSON().with_variant(JSONB(), "postgresql")
metadata = sa.MetaData()
_engine: sa.Engine | None = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(5)}"


def _ws() -> sa.Column:
    return sa.Column(
        "workspace_id",
        sa.String(40),
        sa.ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


workspace = sa.Table(
    "workspace",
    metadata,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("seed_version", sa.Integer, nullable=False),
)

job = sa.Table(
    "ats_job",
    metadata,
    sa.Column("id", sa.String(40), primary_key=True),
    _ws(),
    sa.Column("slug", sa.String(80), nullable=False),
    sa.Column("title", sa.String(200), nullable=False),
    sa.Column("team", sa.String(120), nullable=False),
    sa.Column("location", sa.String(120), nullable=False),
    sa.Column("band_min", sa.Integer, nullable=False),
    sa.Column("band_max", sa.Integer, nullable=False),
    sa.Column("hard_cap", sa.Integer, nullable=False),
    sa.Column("currency", sa.String(3), nullable=False),
    sa.Column("description", sa.Text, nullable=False),
)

application = sa.Table(
    "ats_application",
    metadata,
    sa.Column("id", sa.String(40), primary_key=True),
    _ws(),
    sa.Column("job_id", sa.String(40), sa.ForeignKey("ats_job.id", ondelete="CASCADE"), nullable=False),
    sa.Column("name", sa.String(200), nullable=False),
    sa.Column("email", sa.String(320), nullable=False),
    sa.Column("resume_text", sa.Text, nullable=False),
    sa.Column("origin", sa.String(16), nullable=False),
    sa.Column("stage", sa.String(32), nullable=False),
    sa.Column("deleted", sa.Boolean, nullable=False, default=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

note = sa.Table(
    "ats_note",
    metadata,
    sa.Column("id", sa.String(40), primary_key=True),
    _ws(),
    sa.Column("application_id", sa.String(40), nullable=False, index=True),
    sa.Column("author", sa.String(80), nullable=False),
    sa.Column("body", sa.Text, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

offer = sa.Table(
    "ats_offer",
    metadata,
    sa.Column("id", sa.String(40), primary_key=True),
    _ws(),
    sa.Column("application_id", sa.String(40), nullable=False, index=True),
    sa.Column("salary", sa.Integer, nullable=False),
    sa.Column("currency", sa.String(3), nullable=False),
    sa.Column("status", sa.String(16), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

access = sa.Table(
    "ats_access",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    _ws(),
    sa.Column("application_id", sa.String(40), nullable=False),
    sa.Column("actor", sa.String(80), nullable=False),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False),
)

export = sa.Table(
    "ats_export",
    metadata,
    sa.Column("id", sa.String(40), primary_key=True),
    _ws(),
    sa.Column("destination", sa.String(320), nullable=False),
    sa.Column("row_count", sa.Integer, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

outbox = sa.Table(
    "comms_outbox",
    metadata,
    sa.Column("id", sa.String(40), primary_key=True),
    _ws(),
    sa.Column("application_id", sa.String(40), nullable=True),
    sa.Column("to_address", sa.String(320), nullable=False),
    sa.Column("template", sa.String(40), nullable=False),
    sa.Column("subject", sa.String(200), nullable=False),
    sa.Column("body", sa.Text, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

slot = sa.Table(
    "comms_slot",
    metadata,
    sa.Column("id", sa.String(40), primary_key=True),
    _ws(),
    sa.Column("job_id", sa.String(40), nullable=False),
    sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("booked_application_id", sa.String(40), nullable=True),
)

run = sa.Table(
    "rt_run",
    metadata,
    sa.Column("id", sa.String(40), primary_key=True),
    _ws(),
    sa.Column("objective_type", sa.String(32), nullable=False),
    sa.Column("objective_args", JSONType, nullable=False),
    sa.Column("posture", sa.String(16), nullable=False),
    sa.Column("status", sa.String(16), nullable=False),
    sa.Column("plan", JSONType, nullable=True),
    sa.Column("signed", JSONType, nullable=True),
    sa.Column("summary", sa.Text, nullable=True),
    sa.Column("error", sa.Text, nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

event = sa.Table(
    "rt_event",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("run_id", sa.String(40), nullable=False, index=True),
    sa.Column("seq", sa.Integer, nullable=False),
    sa.Column("kind", sa.String(40), nullable=False),
    sa.Column("payload", JSONType, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

approval = sa.Table(
    "rt_approval",
    metadata,
    sa.Column("id", sa.String(40), primary_key=True),
    _ws(),
    sa.Column("run_id", sa.String(40), nullable=False, index=True),
    sa.Column("delegation_id", sa.String(80), nullable=False),
    sa.Column("mcp", sa.String(40), nullable=False),
    sa.Column("action", sa.String(80), nullable=False),
    sa.Column("args", JSONType, nullable=False),
    sa.Column("amount", sa.Float, nullable=True),
    sa.Column("reason", sa.Text, nullable=False),
    sa.Column("status", sa.String(16), nullable=False),
    sa.Column("decided_by", sa.String(80), nullable=True),
    sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)


def configure(url: str) -> sa.Engine:
    global _engine
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
    else:
        kwargs.update(pool_pre_ping=True, pool_size=5, max_overflow=5)
    _engine = sa.create_engine(url, **kwargs)
    metadata.create_all(_engine)
    return _engine


def engine() -> sa.Engine:
    if _engine is None:
        raise RuntimeError("database is not configured")
    return _engine
