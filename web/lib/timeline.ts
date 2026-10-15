import { RunEvent } from "./api";

export interface TimelineItem {
  seq: number;
  mcp: string;
  action: string;
  args: Record<string, unknown>;
  label: string | null;
  point: string | null;
  reason: string | null;
  drift: { param: string; declared: Record<string, unknown>; attempted: unknown }[];
  verdicts: { point: string; verdict: string; reason: string }[];
  held: { delegation_id?: string; approval_id?: string } | null;
  status: "pending" | "done";
}

export function toTimeline(events: RunEvent[]): TimelineItem[] {
  const rows: TimelineItem[] = [];
  let open: TimelineItem | null = null;
  for (const e of events) {
    if (e.kind === "attempt") {
      open = {
        seq: e.seq, mcp: e.payload.mcp, action: e.payload.action, args: e.payload.args ?? {},
        label: null, point: null, reason: null, drift: [], verdicts: [], held: null, status: "pending",
      };
      rows.push(open);
    } else if (open && e.kind === "verdict") {
      open.verdicts.push({ point: e.payload.point, verdict: e.payload.verdict, reason: e.payload.reason });
    } else if (open && (e.kind === "hold.opened" || e.kind === "approval.pending")) {
      open.held = {
        delegation_id: e.payload.delegation_id ?? open.held?.delegation_id,
        approval_id: e.payload.approval_id ?? open.held?.approval_id,
      };
    } else if (open && e.kind === "decision") {
      Object.assign(open, {
        label: e.payload.label, point: e.payload.point, reason: e.payload.reason,
        drift: e.payload.drift ?? [], status: "done",
      });
      open = null;
    }
  }
  return rows;
}
