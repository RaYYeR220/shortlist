"use client";
import Link from "next/link";
import { use, useEffect, useState } from "react";
import { Masthead } from "@/components/Masthead";
import { Meta, RunDetail, api } from "@/lib/api";
import { useRunEvents } from "@/lib/events";
import { PlanCard } from "@/components/PlanCard";
import { Timeline } from "@/components/Timeline";

export default function RunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = use(params);
  const events = useRunEvents(runId);
  const [run, setRun] = useState<RunDetail | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);

  useEffect(() => { api.meta().then(setMeta).catch(() => {}); }, []);
  useEffect(() => {
    let alive = true;
    const tick = () => api.run(runId).then((r) => { if (alive) setRun(r); }).catch(() => {});
    tick();
    const id = setInterval(tick, 2000);
    return () => { alive = false; clearInterval(id); };
  }, [runId, events.length]);

  const signed = run?.signed ?? events.find((e) => e.kind === "plan.signed")?.payload ?? null;
  const plan = run?.plan ?? events.find((e) => e.kind === "plan.declared")?.payload?.plan ?? null;
  const messages = events.filter((e) => ["llm.message", "screener.message", "caller.message"].includes(e.kind));

  async function approve(id: string) {
    try { await api.decide(id, "approved"); } catch (e) { alert(e instanceof Error ? e.message : String(e)); }
  }
  async function reject(id: string) {
    try { await api.decide(id, "rejected"); } catch (e) { alert(e instanceof Error ? e.message : String(e)); }
  }

  const holdResolved = new Set(
    events.filter((e) => e.kind === "hold.resolved").map((e) => e.payload.delegation_id as string)
  );
  const pendingApproval: string | null =
    events
      .filter((e) => e.kind === "approval.pending")
      .map((e) => ({ id: e.payload.approval_id as string, del: e.payload.delegation_id as string }))
      .filter((p) => !holdResolved.has(p.del))
      .slice(-1)[0]?.id ?? null;

  return (
    <>
      <Masthead current="desk" />
      <main className="wrap" style={{ paddingTop: 24, paddingBottom: 60 }}>
        <div className="section-hd">
          <h1>Run</h1>
          <span className="pill">{run?.status ?? "…"}</span>
          <span className="tag mono">{runId.slice(0, 12)}</span>
          <span style={{ flex: 1 }} />
          <Link className="btn" href="/desk">← desk</Link>
        </div>

        <div className="twocol">
          <div>
            {plan ? <PlanCard plan={plan} signed={signed} console={meta?.armoriq.console} />
              : <p className="mono" style={{ color: "var(--ink-500)" }}>Declaring the plan…</p>}
            {run?.status === "refused" && <div className="notice">The plan was refused before it was signed: {run.error}</div>}
          </div>
          <div>
            <Timeline events={events} onApprove={approve} />
            {pendingApproval && (
              <div className="toolbar" style={{ marginTop: 12 }}>
                <button className="btn danger" onClick={() => reject(pendingApproval)}>Reject</button>
              </div>
            )}
            {messages.length > 0 && (
              <div style={{ marginTop: 18 }}>
                {messages.map((m) => <div className="msg" key={m.seq}>{m.payload.content ?? m.payload.text}</div>)}
              </div>
            )}
            {run?.summary && <div className="msg" style={{ borderColor: "var(--green)" }}><b>Summary.</b> {run.summary}</div>}
          </div>
        </div>
      </main>
    </>
  );
}
