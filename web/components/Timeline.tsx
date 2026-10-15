"use client";
import { RunEvent } from "@/lib/api";
import { toTimeline } from "@/lib/timeline";
import { DriftDiff } from "./DriftDiff";
import { Stamp } from "./Stamp";

function Call({ mcp, action, args }: { mcp: string; action: string; args: Record<string, unknown> }) {
  const shown = Object.entries(args).filter(([k]) => !["workspace_id"].includes(k));
  return (
    <code className="call">
      <span className="t">{mcp}.</span>{action}(
      {shown.map(([k, v], i) => (
        <span key={k}>{i > 0 ? ", " : ""}{k}=<span className={["stage", "to", "destination", "salary"].includes(k) ? "arg" : undefined}>{JSON.stringify(v)}</span></span>
      ))}
      )
    </code>
  );
}

export function Timeline({ events, onApprove }: { events: RunEvent[]; onApprove?: (approvalId: string) => void }) {
  const rows = toTimeline(events);
  if (!rows.length) return <p className="mono" style={{ color: "var(--ink-500)" }}>Waiting for the agent to act…</p>;
  return (
    <div className="rows">
      {rows.map((r) => (
        <div className={`row${r.status === "pending" ? " pending" : ""}`} key={r.seq}>
          <div className="idx mono">{String(r.seq).padStart(2, "0")}</div>
          <div>
            <Call mcp={r.mcp} action={r.action} args={r.args} />
            {r.reason && r.status === "done" && r.label !== "ALLOWED" && <span className="call reason">{r.reason}</span>}
            {r.label === "BLOCKED · argument drift" && <DriftDiff drift={r.drift} />}
            {r.held?.approval_id && r.status === "done" && onApprove && r.label?.startsWith("HELD") === false && null}
            {r.held?.approval_id && r.status === "pending" && onApprove && (
              <div style={{ marginTop: 8 }}>
                <button className="btn go" onClick={() => onApprove(r.held!.approval_id!)}>Approve</button>
              </div>
            )}
          </div>
          <div className="verdict"><Stamp label={r.label} point={r.point} /></div>
        </div>
      ))}
    </div>
  );
}
