"""Objective templates, plan declaration and argument binding.

A plan is declared before the agent reads any candidate content. Each step carries
per-parameter constraints. ArmorIQ signs the plan; every attempted tool call is then
matched against the signed steps before it may run.
"""

from dataclasses import dataclass
from typing import Any, Callable, Literal, Mapping

from . import domain

ObjectiveType = Literal["screen_application", "phone_screen", "extend_offer"]
Constraint = Mapping[str, Any]
Resolver = Callable[[str], set]
MISSING = object()


class PlanRejected(ValueError):
    pass


@dataclass(frozen=True)
class Objective:
    type: ObjectiveType
    workspace_id: str
    application_id: str
    job_id: str
    salary: int | None = None
    currency: str = "USD"


@dataclass(frozen=True)
class StepSpec:
    key: str
    mcp: str
    action: str
    purpose: str
    required: bool
    constraints: Callable[[Objective], dict]


@dataclass(frozen=True)
class PlanStep:
    key: str
    mcp: str
    action: str
    purpose: str
    constraints: Mapping[str, Constraint]


@dataclass(frozen=True)
class Plan:
    objective_type: str
    goal: str
    steps: tuple[PlanStep, ...]
    planner_fallback: bool = False

    def to_armoriq(self) -> dict:
        return {
            "goal": self.goal,
            "steps": [
                {
                    "action": s.action,
                    "mcp": s.mcp,
                    "params": {k: c["eq"] for k, c in s.constraints.items() if "eq" in c},
                    "constraints": {k: dict(c) for k, c in s.constraints.items()},
                    "purpose": s.purpose,
                }
                for s in self.steps
            ],
        }

    def to_json(self) -> dict:
        return {
            "objective_type": self.objective_type,
            "goal": self.goal,
            "planner_fallback": self.planner_fallback,
            "steps": [
                {"key": s.key, "mcp": s.mcp, "action": s.action, "purpose": s.purpose,
                 "constraints": {k: dict(c) for k, c in s.constraints.items()}}
                for s in self.steps
            ],
        }

    @classmethod
    def from_json(cls, data: dict) -> "Plan":
        steps = tuple(PlanStep(s["key"], s["mcp"], s["action"], s["purpose"], s["constraints"]) for s in data["steps"])
        return cls(data["objective_type"], data["goal"], steps, data.get("planner_fallback", False))


ANY = {"any": True}


def _eq(value: Any) -> dict:
    return {"eq": value}


def _scope(o: Objective) -> dict:
    return {"workspace_id": _eq(o.workspace_id), "application_id": _eq(o.application_id)}


def _job(o: Objective) -> dict:
    return {"workspace_id": _eq(o.workspace_id), "job_id": _eq(o.job_id)}


READ_APP = StepSpec("read_application", "ats", "get_application", "Read the application under review", True, _scope)
READ_JOB = StepSpec("read_job", "ats", "get_job", "Read the job requirements and salary band", False, _job)
NOTE = StepSpec("note", "ats", "add_note", "Record a summary on this application", True, lambda o: {**_scope(o), "body": ANY})

TEMPLATES: dict[str, tuple[StepSpec, ...]] = {
    "screen_application": (
        READ_APP,
        READ_JOB,
        NOTE,
        StepSpec("decide", "ats", "set_stage", "Move this application to phone screen or reject it", True,
                 lambda o: {**_scope(o), "stage": {"in": ["phone_screen", "rejected"]}}),
        StepSpec("notify", "comms", "send_email", "Tell this candidate the outcome", False,
                 lambda o: {**_scope(o), "to": {"bind": "candidate_email"},
                            "template": {"in": ["invite_phone_screen", "rejection"]}, "body": ANY}),
    ),
    "phone_screen": (
        READ_APP,
        READ_JOB,
        NOTE,
        StepSpec("slots", "comms", "list_slots", "Look up open interview slots for this job", False, _job),
        StepSpec("book", "comms", "book_slot", "Book one open slot for this candidate", False,
                 lambda o: {"workspace_id": _eq(o.workspace_id), "slot_id": {"bind": "open_slot"},
                            "application_id": _eq(o.application_id)}),
        StepSpec("advance", "ats", "set_stage", "Advance this candidate to interview or reject", False,
                 lambda o: {**_scope(o), "stage": {"in": ["interview", "rejected"]}}),
        StepSpec("confirm", "comms", "send_email", "Confirm the interview to this candidate", False,
                 lambda o: {**_scope(o), "to": {"bind": "candidate_email"},
                            "template": {"in": ["interview_confirmation"]}, "body": ANY}),
    ),
    "extend_offer": (
        READ_APP,
        StepSpec("offer", "ats", "create_offer", "Create the offer at the salary the recruiter set", True,
                 lambda o: {**_scope(o), "salary": _eq(o.salary), "currency": {"eq": o.currency, "optional": True}}),
        StepSpec("send_offer", "comms", "send_email", "Send the offer letter to this candidate", True,
                 lambda o: {**_scope(o), "to": {"bind": "candidate_email"},
                            "template": {"in": ["offer_letter"]}, "body": ANY}),
    ),
}

DEFAULT_GOALS = {
    "screen_application": "Screen application {app} and record the outcome.",
    "phone_screen": "Run a phone screen with the candidate on application {app}.",
    "extend_offer": "Extend an offer of {salary} {currency} on application {app}.",
}


def default_goal(o: Objective) -> str:
    return DEFAULT_GOALS[o.type].format(app=o.application_id, salary=o.salary, currency=o.currency)


def canonical_keys(objective_type: str) -> list[str]:
    return [s.key for s in TEMPLATES[objective_type]]


def build_plan(objective: Objective, step_keys, goal: str = "", *, fallback: bool = False) -> Plan:
    if objective.type not in TEMPLATES:
        raise PlanRejected(f"unknown objective {objective.type!r}")
    specs = {s.key: s for s in TEMPLATES[objective.type]}
    keys = list(step_keys)
    unknown = [k for k in keys if k not in specs]
    if unknown:
        raise PlanRejected(f"steps outside the {objective.type} template: {unknown}")
    if len(set(keys)) != len(keys):
        raise PlanRejected("a step is declared twice")
    missing = [k for k, s in specs.items() if s.required and k not in keys]
    if missing:
        raise PlanRejected(f"required steps missing: {missing}")
    if objective.type == "extend_offer" and not objective.salary:
        raise PlanRejected("an offer needs a salary")
    steps = tuple(PlanStep(s.key, s.mcp, s.action, s.purpose, s.constraints(objective)) for s in (specs[k] for k in keys))
    return Plan(objective.type, (goal or "").strip()[:300] or default_goal(objective), steps, fallback)


@dataclass(frozen=True)
class Drift:
    param: str
    declared: dict
    attempted: Any

    def to_json(self) -> dict:
        return {"param": self.param, "declared": self.declared, "attempted": self.attempted}


@dataclass(frozen=True)
class StepMatch:
    status: Literal["match", "not_in_plan", "drift"]
    step_index: int | None = None
    drift: tuple[Drift, ...] = ()


def _norm(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        try:
            return float(text)
        except ValueError:
            return text.lower() if "@" in text else text
    return value


def check_constraints(constraints: Mapping[str, Constraint], args: Mapping[str, Any], resolve: Resolver) -> tuple[Drift, ...]:
    drifts: list[Drift] = []
    for param, c in constraints.items():
        value = args.get(param, MISSING)
        if value is MISSING:
            if not c.get("optional"):
                drifts.append(Drift(param, dict(c), None))
            continue
        if "eq" in c:
            ok = _norm(value) == _norm(c["eq"])
        elif "in" in c:
            ok = _norm(value) in {_norm(x) for x in c["in"]}
        elif "bind" in c:
            ok = _norm(value) in {_norm(x) for x in resolve(c["bind"])}
        else:
            ok = bool(c.get("any"))
        if not ok:
            drifts.append(Drift(param, dict(c), value))
    for param, value in args.items():
        if param not in constraints:
            drifts.append(Drift(param, {"absent": True}, value))
    return tuple(drifts)


def match_call(plan: Plan, mcp: str, action: str, args: Mapping[str, Any], resolve: Resolver) -> StepMatch:
    best: tuple[int, tuple[Drift, ...]] | None = None
    for index, step in enumerate(plan.steps):
        if step.mcp != mcp or step.action != action:
            continue
        drift = check_constraints(step.constraints, args, resolve)
        if not drift:
            return StepMatch("match", index)
        if best is None or len(drift) < len(best[1]):
            best = (index, drift)
    if best is None:
        return StepMatch("not_in_plan")
    return StepMatch("drift", best[0], best[1])


class DbResolver:
    """Resolves `bind` constraints from the trusted record, never from the model."""

    def __init__(self, workspace_id: str, application_id: str, job_id: str):
        self.workspace_id, self.application_id, self.job_id = workspace_id, application_id, job_id

    def __call__(self, ref: str) -> set:
        try:
            if ref == "candidate_email":
                return {domain.application_email(self.workspace_id, self.application_id).lower()}
            if ref == "open_slot":
                return {s["id"] for s in domain.list_slots(self.workspace_id, self.job_id)}
        except domain.DomainError:
            return set()
        return set()
