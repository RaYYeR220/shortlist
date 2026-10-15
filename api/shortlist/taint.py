from dataclasses import dataclass, field
from typing import Literal

TAINTING_ACTIONS = {("ats", "get_application")}


@dataclass
class Taint:
    sources: list[str] = field(default_factory=list)

    @property
    def tainted(self) -> bool:
        return bool(self.sources)

    def mark(self, source: str) -> None:
        if source not in self.sources:
            self.sources.append(source)

    def observe(self, mcp: str, action: str) -> None:
        if (mcp, action) in TAINTING_ACTIONS:
            self.mark(f"{mcp}.{action}")


@dataclass(frozen=True)
class AmendmentDecision:
    accepted: bool
    label: str
    reason: str


def decide_amendment(taint: Taint, requested_by: Literal["executor", "recruiter"]) -> AmendmentDecision:
    if requested_by == "recruiter":
        return AmendmentDecision(True, "AMENDMENT · re-sign", "requested by the recruiter")
    if taint.tainted:
        return AmendmentDecision(
            False,
            "REFUSED · untrusted amendment",
            f"requested after reading untrusted content ({', '.join(taint.sources)}); "
            "context can shape the plan, it cannot mint permission",
        )
    return AmendmentDecision(False, "REFUSED · amendment needs a human", "the agent cannot extend its own plan; the recruiter can")
