"""A process-wide sliding-window budget.

The live demo runs unauthenticated, and each run spends model tokens. Per-workspace
limits do not stop a caller who keeps creating fresh workspaces, so these global caps
bound total workspace creation and total runs per hour across the whole process.
(max-instances is 1, so one process is the whole service.)
"""

import time
from collections import defaultdict, deque

WINDOW = 3600.0


class Budget:
    def __init__(self):
        self._events: dict[str, deque] = defaultdict(deque)

    def allow(self, name: str, limit: int, *, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        q = self._events[name]
        while q and q[0] <= now - WINDOW:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True
