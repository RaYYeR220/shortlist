"use client";
import Link from "next/link";
import { Masthead } from "@/components/Masthead";
import { Approval, api } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";

export default function Approvals() {
  const { ws, board, refresh } = useWorkspace();
  if (!ws || !board) return <Shell><p className="mono" style={{ color: "var(--ink-500)" }}>Loading…</p></Shell>;

  const pending = board.approvals.filter((a) => a.status === "pending");
  const history = board.approvals.filter((a) => a.status !== "pending");

  async function decide(a: Approval, decision: "approved" | "rejected") {
    try { await api.decide(a.id, decision); await refresh(); } catch (e) { alert(e instanceof Error ? e.message : String(e)); }
  }

  return (
    <Shell>
      <div className="section-hd"><h1>Approvals</h1><span className="tag">Actions ArmorIQ held for a human.</span>
        <span style={{ flex: 1 }} /><button className="btn" onClick={refresh}>Refresh</button></div>

      {pending.length === 0 && <p style={{ color: "var(--ink-500)" }}>Nothing waiting. Offer a candidate above their band and it will land here.</p>}
      {pending.map((a) => (
        <div className="sheet" key={a.id} style={{ marginBottom: 14 }}>
          <div className="sheet-hd"><span>Held · {a.action}</span><span className="mono">delegation {a.delegation_id.slice(0, 8)}</span></div>
          <div className="sheet-bd">
            <code className="call" style={{ fontSize: 14 }}>{a.mcp}.{a.action}({Object.entries(a.args).filter(([k]) => k !== "workspace_id").map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ")})</code>
            <p style={{ color: "var(--ink-500)", fontSize: 13, margin: "8px 0 0" }}>{a.reason}{a.amount ? ` · amount ${a.amount.toLocaleString()}` : ""}</p>
            <div className="toolbar" style={{ marginTop: 14, marginBottom: 0 }}>
              <button className="btn go" onClick={() => decide(a, "approved")}>Approve</button>
              <button className="btn danger" onClick={() => decide(a, "rejected")}>Reject</button>
              <Link className="btn" href={`/desk/runs/${a.run_id}`}>View run</Link>
            </div>
          </div>
        </div>
      ))}

      {history.length > 0 && (
        <div className="section">
          <div className="section-hd"><h2>History</h2></div>
          <div className="rows">
            {history.map((a) => (
              <div className="row" key={a.id}>
                <div className="idx mono">—</div>
                <code className="call">{a.action} · {a.reason}</code>
                <div className="verdict"><span className="pill">{a.status}{a.decided_by ? ` · ${a.decided_by}` : ""}</span></div>
              </div>
            ))}
          </div>
        </div>
      )}
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return <><Masthead current="approvals" /><main className="wrap" style={{ paddingTop: 24, paddingBottom: 60 }}>{children}</main></>;
}
