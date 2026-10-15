"""Every attempted tool call passes here, in a fixed order:

1. Plan binding (ours): the call must be a declared step, and its arguments must
   satisfy that step's constraints in the ArmorIQ-signed plan. A call that is not a
   declared step, or whose arguments drift, is refused here and never reaches the
   proxy — because the proxy does not compare arguments to the plan, binding has to
   happen before the tool can run. (A policy-denied tool attempted off-plan is the one
   exception: it is sent to the proxy so ArmorIQ's own policy block is shown, which is
   safe precisely because the policy denies it.)
2. `invoke()` through the ArmorIQ proxy, which executes on the MCP server and returns
   ArmorIQ's verdict: allow, block (policy) or hold.
3. Hold: open an ArmorIQ delegation, wait for a human, then resume by re-invoking.

Any error at any stage fails closed.
"""

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal, Protocol

from .armor import ArmorGate, SignedPlan
from .plans import Plan, match_call
from .taint import Taint

DRIFT_POINT = "ours:plan-binding"
NOT_IN_PLAN_POINT = "ours:plan-binding"
AMOUNT_FIELDS = ("salary", "amount")
# Tools the ArmorIQ policy denies. Attempted off-plan, they are sent to the proxy so
# ArmorIQ's own block is demonstrated (safe: the policy refuses them).
POLICY_DENIED = {"export_candidates", "delete_application", "send_bulk", "forward_file"}


@dataclass
class Outcome:
    kind: Literal["allowed", "blocked", "held", "failed"]
    label: str
    point: str
    reason: str
    result: Any = None
    drift: list[dict] = field(default_factory=list)
    delegation_id: str | None = None

    def for_model(self) -> str:
        if self.kind == "allowed":
            return json.dumps(self.result, default=str)
        return (f"REFUSED by the enforcement boundary ({self.label}): {self.reason}. "
                "This action did not run. Do not retry it; continue with the declared plan or finish.")

    def to_json(self) -> dict:
        return {"kind": self.kind, "label": self.label, "point": self.point, "reason": self.reason,
                "drift": self.drift, "delegation_id": self.delegation_id}


class EventSink(Protocol):
    def emit(self, run_id: str, kind: str, payload: dict) -> None: ...


class HoldWaiter(Protocol):
    async def wait(self, run_id: str, delegation_id: str, *, mcp: str, action: str, args: dict,
                   amount: float | None, reason: str) -> Literal["approved", "rejected", "expired"]: ...


@dataclass
class RunContext:
    run_id: str
    workspace_id: str
    plan: Plan
    signed: SignedPlan
    resolve: Callable[[str], set]
    taint: Taint
    resign: Callable[[], Awaitable[SignedPlan]] | None


def _amount(args: dict) -> float | None:
    for key in AMOUNT_FIELDS:
        try:
            return float(args[key])
        except (KeyError, TypeError, ValueError):
            continue
    return None


def _drift_reason(drift: list[dict], plan_id: str) -> str:
    parts = []
    for d in drift:
        if d["declared"].get("absent"):
            parts.append(f"`{d['param']}` is not a parameter of this step")
        else:
            parts.append(f"`{d['param']}`={d['attempted']!r} is outside the signed constraint {d['declared']}")
    return f"same tool, different arguments than plan {plan_id} allows: " + "; ".join(parts)


class Pipeline:
    def __init__(self, gate: ArmorGate, events: EventSink, holds: HoldWaiter | None, policy_denied: set | None = None):
        self.gate, self.events, self.holds = gate, events, holds
        self.policy_denied = POLICY_DENIED if policy_denied is None else policy_denied

    def _emit_verdict(self, ctx: RunContext, mcp: str, action: str, verdict) -> None:
        self.events.emit(ctx.run_id, "verdict", {"mcp": mcp, "action": action, **verdict.to_json()})

    def _decide(self, ctx: RunContext, mcp: str, action: str, args: dict, outcome: Outcome) -> Outcome:
        self.events.emit(ctx.run_id, "decision", {"mcp": mcp, "action": action, "args": args, **outcome.to_json()})
        return outcome

    async def attempt(self, ctx: RunContext, mcp: str, action: str, args: dict) -> Outcome:
        self.events.emit(ctx.run_id, "attempt", {"mcp": mcp, "action": action, "args": args})
        match = match_call(ctx.plan, mcp, action, args, ctx.resolve)
        if match.status == "not_in_plan":
            if action in self.policy_denied:
                return await self._invoke(ctx, mcp, action, args, off_plan=True)
            reason = f"{mcp}.{action} is not a step of signed plan {ctx.signed.plan_id}"
            return self._decide(ctx, mcp, action, args, Outcome("blocked", "BLOCKED · not in plan", NOT_IN_PLAN_POINT, reason))
        if match.status == "drift":
            drift = [d.to_json() for d in match.drift]
            return self._decide(ctx, mcp, action, args, Outcome(
                "blocked", "BLOCKED · argument drift", DRIFT_POINT, _drift_reason(drift, ctx.signed.plan_id), drift=drift))
        return await self._invoke(ctx, mcp, action, args)

    async def _invoke(self, ctx: RunContext, mcp: str, action: str, args: dict, *,
                      off_plan: bool = False, delegation_id: str | None = None) -> Outcome:
        out = await asyncio.to_thread(self.gate.invoke, ctx.signed, mcp, action, args, resume_delegation_id=delegation_id)
        if out.verdict.action == "error" and out.verdict.reason == "token-expired" and ctx.resign is not None:
            ctx.signed = await ctx.resign()
            self.events.emit(ctx.run_id, "plan.resigned", ctx.signed.summary())
            out = await asyncio.to_thread(self.gate.invoke, ctx.signed, mcp, action, args, resume_delegation_id=delegation_id)
        verdict = out.verdict
        self._emit_verdict(ctx, mcp, action, verdict)
        if verdict.action == "allow":
            ctx.taint.observe(mcp, action)
            if delegation_id:
                await asyncio.to_thread(self.gate.mark_executed, delegation_id, ctx.signed.plan_id)
            label = "HELD → APPROVED" if delegation_id else "ALLOWED"
            return self._decide(ctx, mcp, action, args, Outcome("allowed", label, verdict.point, verdict.reason,
                                                                result=out.result, delegation_id=delegation_id))
        if verdict.action == "block":
            label = "BLOCKED · not in plan" if "not in the signed plan" in verdict.reason else "BLOCKED · policy"
            return self._decide(ctx, mcp, action, args, Outcome("blocked", label, verdict.point, verdict.reason))
        if verdict.action == "hold" and not delegation_id and self.holds is not None:
            return await self._hold(ctx, mcp, action, args, verdict.reason)
        reason = "the proxy held a call after approval" if verdict.action == "hold" else verdict.reason
        return self._decide(ctx, mcp, action, args, Outcome("failed", "FAILED CLOSED", verdict.point, reason))

    async def _hold(self, ctx: RunContext, mcp: str, action: str, args: dict, reason: str) -> Outcome:
        amount = _amount(args)
        hold = await asyncio.to_thread(self.gate.open_hold, ctx.signed, mcp, action, args, amount=amount, reason=reason)
        self._emit_verdict(ctx, mcp, action, hold)
        if hold.action == "allow":
            return await self._invoke(ctx, mcp, action, args, delegation_id=hold.delegation_id)
        if hold.action != "hold" or not hold.delegation_id:
            return self._decide(ctx, mcp, action, args, Outcome("failed", "FAILED CLOSED", hold.point, hold.reason))
        self.events.emit(ctx.run_id, "hold.opened", {"delegation_id": hold.delegation_id, "mcp": mcp, "action": action,
                                                      "args": args, "amount": amount, "reason": reason})
        status = await self.holds.wait(ctx.run_id, hold.delegation_id, mcp=mcp, action=action, args=args, amount=amount, reason=reason)
        self.events.emit(ctx.run_id, "hold.resolved", {"delegation_id": hold.delegation_id, "status": status})
        if status != "approved":
            label = "HELD → REJECTED" if status == "rejected" else "HELD → EXPIRED"
            return self._decide(ctx, mcp, action, args, Outcome(
                "blocked", label, "armoriq:delegation", f"the hiring manager did not approve ({status})",
                delegation_id=hold.delegation_id))
        return await self._invoke(ctx, mcp, action, args, delegation_id=hold.delegation_id)
