"""All traffic to ArmorIQ goes through ArmorGate.

The ArmorIQ verdict is read from `invoke()` through the proxy — the proxy is the
enforcement point that actually executes the tool, and it returns allow, or raises
PolicyBlockedException / PolicyHoldException. (The SDK-side `/iap/sdk/enforce`
pre-check is not used: it intersects same-priority policies on different MCP targets
to an empty allowlist and blocks everything, while the proxy enforces correctly.)

Methods return verdicts instead of raising, and every failure maps to `error` so the
pipeline can fail closed.
"""

import logging
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from armoriq_sdk import ArmorIQClient
from armoriq_sdk.exceptions import (
    IntentMismatchException,
    InvalidTokenException,
    MCPInvocationException,
    PolicyBlockedException,
    PolicyHoldException,
    TokenExpiredException,
)
from armoriq_sdk.models import DelegationRequestParams

log = logging.getLogger(__name__)
Action = Literal["allow", "hold", "block", "error"]


@dataclass(frozen=True)
class Verdict:
    action: Action
    reason: str
    point: str
    delegation_id: str | None = None
    matched_policy: str | None = None
    raw: dict | None = None

    def to_json(self) -> dict:
        return {"verdict": self.action, "reason": self.reason, "point": self.point,
                "delegation_id": self.delegation_id, "matched_policy": self.matched_policy}


@dataclass
class SignedPlan:
    plan_id: str
    plan_hash: str
    merkle_root: str | None
    intent_reference: str
    expires_at: float
    token: Any
    plan_doc: dict

    def summary(self) -> dict:
        return {"plan_id": self.plan_id, "plan_hash": self.plan_hash, "merkle_root": self.merkle_root,
                "intent_reference": self.intent_reference, "expires_at": self.expires_at}


class MintRefused(Exception):
    def __init__(self, verdict: Verdict):
        super().__init__(verdict.reason)
        self.verdict = verdict


@dataclass(frozen=True)
class InvokeOutcome:
    verdict: Verdict
    result: Any = None


def _reason(exc: Exception) -> str:
    return getattr(exc, "reason", None) or str(exc) or type(exc).__name__


class ArmorGate:
    def __init__(self, *, api_key: str, backend: str, proxy: str, agent_id: str, user_email: str,
                 approver_email: str, mcp_token: str, validity_seconds: int = 900,
                 client: Any = None, http: httpx.Client | None = None):
        self.api_key, self.backend, self.proxy = api_key, backend.rstrip("/"), proxy.rstrip("/")
        self.agent_id, self.user_email, self.approver_email = agent_id, user_email, approver_email
        self.mcp_token, self.validity = mcp_token, validity_seconds
        self._client = client
        self.http = http or httpx.Client(timeout=15.0)

    @property
    def client(self) -> Any:
        if self._client is None:
            creds = {"ats": {"authType": "bearer", "token": self.mcp_token},
                     "comms": {"authType": "bearer", "token": self.mcp_token}} if self.mcp_token else None
            self._client = ArmorIQClient(api_key=self.api_key, backend_endpoint=self.backend, proxy_endpoint=self.proxy,
                                         user_id=self.user_email, agent_id=self.agent_id, mcp_credentials=creds)
        return self._client

    def sign(self, plan_doc: dict, *, prompt: str, llm: str) -> SignedPlan:
        try:
            capture = self.client.capture_plan(llm=llm, prompt=prompt, plan=plan_doc)
            token = self.client.get_intent_token(capture, validity_seconds=self.validity)
        except PolicyBlockedException as exc:
            raise MintRefused(Verdict("block", _reason(exc), "armoriq:mint", raw=getattr(exc, "metadata", None))) from exc
        except Exception as exc:
            raise MintRefused(Verdict("error", f"mint failed: {exc}", "armoriq:mint")) from exc
        raw = token.raw_token or {}
        return SignedPlan(plan_id=token.plan_id, plan_hash=token.plan_hash, merkle_root=raw.get("merkle_root"),
                          intent_reference=token.token_id, expires_at=float(token.expires_at or 0),
                          token=token, plan_doc=plan_doc)

    def invoke(self, signed: SignedPlan, mcp: str, action: str, args: dict, *, resume_delegation_id: str | None = None) -> InvokeOutcome:
        params = dict(args)
        if resume_delegation_id:
            params["_delegation_id"] = resume_delegation_id
            params["_approvals"] = 999
        try:
            result = self.client.invoke(mcp, action, signed.token, params, user_email=self.user_email)
        except TokenExpiredException:
            return InvokeOutcome(Verdict("error", "token-expired", "armoriq:sdk"))
        except IntentMismatchException as exc:
            return InvokeOutcome(Verdict("block", f"not in the signed plan: {exc}", "armoriq:proxy"))
        except PolicyBlockedException as exc:
            return InvokeOutcome(Verdict("block", _reason(exc), "armoriq:proxy", raw=getattr(exc, "metadata", None)))
        except PolicyHoldException as exc:
            return InvokeOutcome(Verdict("hold", str(exc) or "held for approval", "armoriq:proxy",
                                         raw={"delegation_context": getattr(exc, "delegation_context", None)}))
        except (InvalidTokenException, MCPInvocationException) as exc:
            return InvokeOutcome(Verdict("error", str(exc), "armoriq:proxy"))
        except Exception as exc:
            return InvokeOutcome(Verdict("error", f"invoke failed: {exc}", "armoriq:proxy"))
        return InvokeOutcome(Verdict("allow", "executed through the ArmorIQ proxy", "armoriq:proxy"), result=result.result)

    def open_hold(self, signed: SignedPlan, mcp: str, action: str, args: dict, *, amount: float | None, reason: str) -> Verdict:
        safe_amount = amount if amount and amount >= 0.01 else 0.01
        try:
            approved = self.client.check_approved_delegation(self.user_email, action, safe_amount, signed.plan_id)
        except Exception as exc:
            log.warning("check_approved_delegation failed: %s", exc)
            approved = None
        if approved:
            return Verdict("allow", f"approved delegation {approved.delegation_id}", "armoriq:delegation",
                           delegation_id=approved.delegation_id)
        try:
            created = self.client.create_delegation_request(DelegationRequestParams(
                tool=action, action=action, arguments=args, amount=safe_amount, requester_email=self.user_email,
                requester_role="agent_user", requester_limit=0, domain=mcp, plan_id=signed.plan_id,
                intent_reference=signed.intent_reference, merkle_root=signed.merkle_root, reason=reason,
            ))
        except Exception as exc:
            return Verdict("error", f"delegation request failed: {exc}", "armoriq:delegation")
        if not created.delegation_id:
            return Verdict("error", "delegation request returned no id", "armoriq:delegation")
        return Verdict("hold", reason, "armoriq:delegation", delegation_id=created.delegation_id)

    def delegation_status(self, delegation_id: str) -> str:
        try:
            return self.client.get_delegation_status(delegation_id)
        except Exception as exc:
            log.warning("delegation status failed: %s", exc)
            return "unknown"

    def _decide(self, path: str, delegation_id: str) -> dict:
        response = self.http.post(f"{self.backend}/delegation/{path}",
                                  json={"delegationId": delegation_id, "approverEmail": self.approver_email},
                                  headers={"X-API-Key": self.api_key, "X-User-Email": self.approver_email,
                                           "Content-Type": "application/json"})
        response.raise_for_status()
        return response.json() if response.content else {}

    def approve(self, delegation_id: str) -> dict:
        return self._decide("approve", delegation_id)

    def reject(self, delegation_id: str, reason: str) -> dict:
        # The /delegation/reject DTO rejects an extra `reason` property; we keep the reason in our own record.
        return self._decide("reject", delegation_id)

    def mark_executed(self, delegation_id: str, plan_id: str) -> None:
        try:
            self.client.mark_delegation_executed(self.user_email, delegation_id, plan_id)
        except Exception as exc:
            log.warning("mark-executed failed: %s", exc)

    def revoke(self, signed: SignedPlan, reason: str) -> dict:
        return self.client.revoke(signed.token, reason=reason, cascade=True, plan_id=signed.plan_id,
                                  intent_reference=signed.intent_reference)
