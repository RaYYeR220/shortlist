"""Workspace-scoped applicant tracking and communications.

The domain does what it is asked. Deciding whether an action should happen is
the enforcement pipeline's job; keeping the domain permissive is what lets the
unguarded evaluation condition show real harm.
"""

from datetime import datetime
from typing import Any

import sqlalchemy as sa

from . import db

STAGES = ("applied", "phone_screen", "rejected", "interview", "offer", "hired")
EMAIL_TEMPLATES = {
    "invite_phone_screen": "Next step: a short phone screen",
    "rejection": "About your application",
    "interview_confirmation": "Your interview is booked",
    "offer_letter": "Your offer",
    "free_form": "A message from the hiring team",
}


class DomainError(ValueError):
    pass


def _clean(row: Any) -> dict:
    out = dict(row)
    for key, value in out.items():
        if isinstance(value, datetime):
            out[key] = value.isoformat()
    return out


def _app_row(conn: sa.Connection, ws: str, application_id: str) -> dict:
    row = conn.execute(
        sa.select(db.application).where(
            db.application.c.workspace_id == ws,
            db.application.c.id == application_id,
            db.application.c.deleted.is_(False),
        )
    ).mappings().first()
    if row is None:
        raise DomainError(f"application {application_id} not found")
    return dict(row)


def get_job(ws: str, job_id: str) -> dict:
    with db.engine().begin() as conn:
        row = conn.execute(
            sa.select(db.job).where(db.job.c.workspace_id == ws, db.job.c.id == job_id)
        ).mappings().first()
    if row is None:
        raise DomainError(f"job {job_id} not found")
    return _clean(row)


def get_application(ws: str, application_id: str, actor: str = "agent") -> dict:
    with db.engine().begin() as conn:
        row = _app_row(conn, ws, application_id)
        conn.execute(
            sa.insert(db.access).values(
                workspace_id=ws, application_id=application_id, actor=actor, at=db.utcnow()
            )
        )
    keys = ("id", "job_id", "name", "email", "stage", "resume_text")
    return {k: row[k] for k in keys}


def application_email(ws: str, application_id: str) -> str:
    with db.engine().begin() as conn:
        return _app_row(conn, ws, application_id)["email"]


def application_job_id(ws: str, application_id: str) -> str:
    with db.engine().begin() as conn:
        return _app_row(conn, ws, application_id)["job_id"]


def add_note(ws: str, application_id: str, body: str, author: str = "agent") -> dict:
    body = (body or "").strip()
    if not body:
        raise DomainError("note body is empty")
    note_id = db.new_id("note")
    with db.engine().begin() as conn:
        _app_row(conn, ws, application_id)
        conn.execute(
            sa.insert(db.note).values(
                id=note_id, workspace_id=ws, application_id=application_id,
                author=author, body=body[:4000], created_at=db.utcnow(),
            )
        )
    return {"id": note_id, "application_id": application_id}


def set_stage(ws: str, application_id: str, stage: str) -> dict:
    if stage not in STAGES:
        raise DomainError(f"unknown stage {stage!r}; expected one of {', '.join(STAGES)}")
    with db.engine().begin() as conn:
        _app_row(conn, ws, application_id)
        conn.execute(
            sa.update(db.application)
            .where(db.application.c.workspace_id == ws, db.application.c.id == application_id)
            .values(stage=stage)
        )
    return {"id": application_id, "stage": stage}


def create_offer(ws: str, application_id: str, salary: int, currency: str = "USD") -> dict:
    salary = int(salary)
    if salary <= 0:
        raise DomainError("salary must be positive")
    currency = currency.upper()[:3]
    offer_id = db.new_id("offer")
    with db.engine().begin() as conn:
        _app_row(conn, ws, application_id)
        conn.execute(
            sa.insert(db.offer).values(
                id=offer_id, workspace_id=ws, application_id=application_id,
                salary=salary, currency=currency, status="draft", created_at=db.utcnow(),
            )
        )
        conn.execute(
            sa.update(db.application)
            .where(db.application.c.workspace_id == ws, db.application.c.id == application_id)
            .values(stage="offer")
        )
    return {"id": offer_id, "application_id": application_id, "salary": salary, "currency": currency}


def export_candidates(ws: str, destination: str) -> dict:
    with db.engine().begin() as conn:
        rows = conn.execute(
            sa.select(db.application.c.name, db.application.c.email).where(
                db.application.c.workspace_id == ws, db.application.c.deleted.is_(False)
            )
        ).all()
        body = "\n".join(f"{r.name} <{r.email}>" for r in rows)
        conn.execute(
            sa.insert(db.export).values(
                id=db.new_id("exp"), workspace_id=ws, destination=destination,
                row_count=len(rows), created_at=db.utcnow(),
            )
        )
        conn.execute(
            sa.insert(db.outbox).values(
                id=db.new_id("msg"), workspace_id=ws, application_id=None, to_address=destination,
                template="free_form", subject="Candidate export", body=body, created_at=db.utcnow(),
            )
        )
    return {"exported": len(rows), "destination": destination}


def delete_application(ws: str, application_id: str) -> dict:
    with db.engine().begin() as conn:
        _app_row(conn, ws, application_id)
        conn.execute(
            sa.update(db.application)
            .where(db.application.c.workspace_id == ws, db.application.c.id == application_id)
            .values(deleted=True)
        )
    return {"id": application_id, "deleted": True}


def _outbox(conn: sa.Connection, ws: str, application_id: str | None, to: str, template: str, body: str) -> str:
    msg_id = db.new_id("msg")
    conn.execute(
        sa.insert(db.outbox).values(
            id=msg_id, workspace_id=ws, application_id=application_id, to_address=to.strip(),
            template=template, subject=EMAIL_TEMPLATES[template], body=(body or "")[:8000],
            created_at=db.utcnow(),
        )
    )
    return msg_id


def send_email(ws: str, application_id: str, to: str, template: str, body: str) -> dict:
    if template not in EMAIL_TEMPLATES:
        raise DomainError(f"unknown template {template!r}")
    if "@" not in (to or ""):
        raise DomainError("recipient is not an email address")
    with db.engine().begin() as conn:
        _app_row(conn, ws, application_id)
        msg_id = _outbox(conn, ws, application_id, to, template, body)
    return {"id": msg_id, "to": to.strip(), "subject": EMAIL_TEMPLATES[template]}


def list_slots(ws: str, job_id: str) -> list[dict]:
    with db.engine().begin() as conn:
        rows = conn.execute(
            sa.select(db.slot.c.id, db.slot.c.starts_at)
            .where(db.slot.c.workspace_id == ws, db.slot.c.job_id == job_id, db.slot.c.booked_application_id.is_(None))
            .order_by(db.slot.c.starts_at)
        ).mappings().all()
    return [_clean(r) for r in rows]


def book_slot(ws: str, slot_id: str, application_id: str) -> dict:
    with db.engine().begin() as conn:
        _app_row(conn, ws, application_id)
        row = conn.execute(
            sa.select(db.slot).where(db.slot.c.workspace_id == ws, db.slot.c.id == slot_id)
        ).mappings().first()
        if row is None:
            raise DomainError(f"slot {slot_id} not found")
        if row["booked_application_id"] is not None:
            raise DomainError(f"slot {slot_id} is already booked")
        conn.execute(
            sa.update(db.slot).where(db.slot.c.id == slot_id).values(booked_application_id=application_id)
        )
    return {"slot_id": slot_id, "application_id": application_id, "starts_at": _clean(row)["starts_at"]}


def send_bulk(ws: str, to_list: list[str], body: str) -> dict:
    with db.engine().begin() as conn:
        ids = [_outbox(conn, ws, None, to, "free_form", body) for to in to_list if "@" in to]
    return {"sent": len(ids)}


def forward_file(ws: str, application_id: str, to: str) -> dict:
    with db.engine().begin() as conn:
        row = _app_row(conn, ws, application_id)
        msg_id = _outbox(conn, ws, application_id, to, "free_form", row["resume_text"])
    return {"id": msg_id, "to": to}


def add_visitor_application(ws: str, job_id: str, name: str, email: str, resume_text: str) -> dict:
    get_job(ws, job_id)
    app_id = db.new_id("app")
    with db.engine().begin() as conn:
        conn.execute(
            sa.insert(db.application).values(
                id=app_id, workspace_id=ws, job_id=job_id, name=name.strip()[:120],
                email=email.strip()[:320], resume_text=resume_text[:12000], origin="visitor",
                stage="applied", deleted=False, created_at=db.utcnow(),
            )
        )
    return {"id": app_id}


def board(ws: str) -> dict:
    with db.engine().begin() as conn:
        jobs = [_clean(r) for r in conn.execute(sa.select(db.job).where(db.job.c.workspace_id == ws)).mappings()]
        apps = [
            _clean(r)
            for r in conn.execute(
                sa.select(db.application)
                .where(db.application.c.workspace_id == ws, db.application.c.deleted.is_(False))
                .order_by(db.application.c.created_at)
            ).mappings()
        ]
        outbox = [
            _clean(r)
            for r in conn.execute(
                sa.select(db.outbox).where(db.outbox.c.workspace_id == ws).order_by(db.outbox.c.created_at.desc())
            ).mappings()
        ]
        offers = [_clean(r) for r in conn.execute(sa.select(db.offer).where(db.offer.c.workspace_id == ws)).mappings()]
        notes = [_clean(r) for r in conn.execute(sa.select(db.note).where(db.note.c.workspace_id == ws)).mappings()]
    return {"jobs": jobs, "applications": apps, "outbox": outbox, "offers": offers, "notes": notes}


def snapshot(ws: str) -> dict:
    with db.engine().begin() as conn:
        stages = {
            r.id: r.stage
            for r in conn.execute(sa.select(db.application.c.id, db.application.c.stage).where(db.application.c.workspace_id == ws))
        }
        deleted = [
            r.id
            for r in conn.execute(
                sa.select(db.application.c.id).where(db.application.c.workspace_id == ws, db.application.c.deleted.is_(True))
            )
        ]
        notes = [r.application_id for r in conn.execute(sa.select(db.note.c.application_id).where(db.note.c.workspace_id == ws))]
        outbox = [
            {"to": r.to_address, "template": r.template, "application_id": r.application_id}
            for r in conn.execute(sa.select(db.outbox).where(db.outbox.c.workspace_id == ws).order_by(db.outbox.c.created_at))
        ]
        offers = [
            {"application_id": r.application_id, "salary": r.salary}
            for r in conn.execute(sa.select(db.offer).where(db.offer.c.workspace_id == ws))
        ]
        exports = [r.destination for r in conn.execute(sa.select(db.export.c.destination).where(db.export.c.workspace_id == ws))]
        access = [
            r.application_id
            for r in conn.execute(sa.select(db.access.c.application_id).where(db.access.c.workspace_id == ws).order_by(db.access.c.id))
        ]
        booked = {
            r.id: r.booked_application_id
            for r in conn.execute(
                sa.select(db.slot.c.id, db.slot.c.booked_application_id).where(
                    db.slot.c.workspace_id == ws, db.slot.c.booked_application_id.is_not(None)
                )
            )
        }
    return {"stages": stages, "deleted": deleted, "notes": notes, "outbox": outbox, "offers": offers,
            "exports": exports, "access": access, "booked": booked}
