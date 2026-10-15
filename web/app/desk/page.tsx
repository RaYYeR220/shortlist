"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Masthead } from "@/components/Masthead";
import { Application, Stage, api } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";

const COLUMNS: Stage[] = ["applied", "phone_screen", "interview", "offer", "hired", "rejected"];
const TITLES: Record<Stage, string> = {
  applied: "Applied", phone_screen: "Phone screen", interview: "Interview", offer: "Offer", hired: "Hired", rejected: "Rejected",
};

export default function Desk() {
  const { ws, board, error, refresh, reset } = useWorkspace();
  const router = useRouter();
  const [posture, setPosture] = useState<"gullible" | "careful">("gullible");
  const [busy, setBusy] = useState<string | null>(null);

  if (error) return <Shell><div className="notice">Could not reach the API: {error}</div></Shell>;
  if (!ws || !board) return <Shell><p className="mono" style={{ color: "var(--ink-500)" }}>Opening a workspace…</p></Shell>;

  const job = board.jobs[0];
  const byStage = (s: Stage) => board.applications.filter((a) => a.stage === s);
  const pending = board.approvals.filter((a) => a.status === "pending").length;

  async function screen(app: Application) {
    setBusy(app.id);
    try {
      const { run_id } = await api.startRun({ workspace_id: ws!, type: "screen_application", application_id: app.id, posture });
      router.push(`/desk/runs/${run_id}`);
    } catch (e) { alert(e instanceof Error ? e.message : String(e)); setBusy(null); }
  }
  async function offer(app: Application) {
    const salary = Number(prompt(`Offer salary for ${app.name} (band ${job.band_min}–${job.band_max})`, String(job.band_max + 25000)));
    if (!salary) return;
    setBusy(app.id);
    try {
      const { run_id } = await api.startRun({ workspace_id: ws!, type: "extend_offer", application_id: app.id, salary, posture: "careful" });
      router.push(`/desk/runs/${run_id}`);
    } catch (e) { alert(e instanceof Error ? e.message : String(e)); setBusy(null); }
  }

  return (
    <Shell current="desk">
      <div className="section-hd">
        <h1>The desk</h1>
        <span className="tag">{job.title} · band {job.currency} {job.band_min.toLocaleString()}–{job.band_max.toLocaleString()}</span>
      </div>
      <div className="toolbar">
        <span className="smallcaps" style={{ fontSize: 11, color: "var(--ink-500)" }}>Agent posture</span>
        <div className="seg" role="group">
          <button aria-pressed={posture === "gullible"} onClick={() => setPosture("gullible")}>Gullible</button>
          <button aria-pressed={posture === "careful"} onClick={() => setPosture("careful")}>Careful</button>
        </div>
        <span className="cta-note" style={{ maxWidth: 420 }}>
          {posture === "gullible"
            ? "The agent trusts instructions hidden in a resume — so the boundary has something to refuse."
            : "The agent treats resume text as data. The boundary still holds if it slips."}
        </span>
        <span style={{ flex: 1 }} />
        <Link className="btn go" href="/desk/approvals">Approvals{pending ? ` · ${pending}` : ""}</Link>
        <button className="btn" onClick={reset}>Reset demo</button>
      </div>

      <div className="board">
        {COLUMNS.map((s) => (
          <div className="col" key={s}>
            <h3>{TITLES[s]} · {byStage(s).length}</h3>
            {byStage(s).map((a) => (
              <div className="appcard" key={a.id}>
                <div className="nm">{a.name}<span className="origin">{a.origin}</span></div>
                <div className="meta mono">{a.email}</div>
                <div className="acts">
                  <button className="btn go" disabled={busy === a.id} onClick={() => screen(a)}>Screen</button>
                  <button className="btn" disabled={busy === a.id} onClick={() => offer(a)}>Offer…</button>
                  <Link className="btn" href={`/screen/${a.id}`}>Call</Link>
                </div>
              </div>
            ))}
            {byStage(s).length === 0 && <div className="appcard" style={{ color: "var(--ink-300)", fontSize: 12 }}>—</div>}
          </div>
        ))}
      </div>

      <div className="section">
        <div className="section-hd"><h2>Recent runs</h2><button className="btn" onClick={refresh}>Refresh</button></div>
        <div className="rows">
          {board.runs.slice(0, 10).map((r) => (
            <div className="row" key={r.id}>
              <div className="idx mono">—</div>
              <code className="call">{r.objective_type}(<span className="arg">{r.objective_args.application_id}</span>)</code>
              <div className="verdict"><Link className="pill" href={`/desk/runs/${r.id}`}>{r.status}</Link></div>
            </div>
          ))}
          {board.runs.length === 0 && <div className="row"><div /><span style={{ color: "var(--ink-500)" }}>No runs yet — screen a candidate above.</span><div /></div>}
        </div>
      </div>
    </Shell>
  );
}

function Shell({ children, current }: { children: React.ReactNode; current?: string }) {
  return (
    <>
      <Masthead current={current} />
      <main className="wrap" style={{ paddingTop: 24, paddingBottom: 60 }}>{children}</main>
    </>
  );
}
