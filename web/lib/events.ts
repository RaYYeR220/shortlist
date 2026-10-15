"use client";
import { useEffect, useState } from "react";
import { API, RunEvent } from "./api";

export const KINDS = [
  "run.planning", "plan.declared", "plan.signed", "plan.resigned", "attempt", "verdict", "decision",
  "attempt.suppressed", "amendment.decided", "hold.opened", "approval.pending", "hold.resolved",
  "llm.message", "caller.message", "screener.message", "run.finished", "run.failed", "run.refused",
];
const TERMINAL = new Set(["run.finished", "run.failed", "run.refused"]);

export function useRunEvents(runId: string | null) {
  const [events, setEvents] = useState<RunEvent[]>([]);
  useEffect(() => {
    if (!runId) return;
    setEvents([]);
    const source = new EventSource(`${API}/api/runs/${runId}/events`);
    const seen = new Set<number>();
    const onEvent = (message: MessageEvent) => {
      const item = JSON.parse(message.data) as RunEvent;
      if (seen.has(item.seq)) return;
      seen.add(item.seq);
      setEvents((prev) => [...prev, item].sort((a, b) => a.seq - b.seq));
      if (TERMINAL.has(item.kind)) source.close();
    };
    KINDS.forEach((kind) => source.addEventListener(kind, onEvent as EventListener));
    return () => source.close();
  }, [runId]);
  return events;
}
