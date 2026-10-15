"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Masthead } from "@/components/Masthead";
import { api } from "@/lib/api";

const WHO = [
  ["Tool allowed / denied by policy", "ArmorIQ", "policy, at the proxy"],
  ["The action belongs to the signed plan", "ArmorIQ", "Merkle proof, at the proxy"],
  ["Over-band offer held, then resumed", "ArmorIQ", "delegation + approval"],
  ["Same tool, different target (argument)", "Shortlist", "bound to the ArmorIQ-signed plan"],
  ["Amendment after reading untrusted text", "Shortlist", "provenance rule"],
];

export default function Proof() {
  const [proof, setProof] = useState<any>(null);
  useEffect(() => { api.proof().then(setProof).catch(() => setProof({ status: "error" })); }, []);
  const summary = proof?.summary;

  return (
    <>
      <Masthead current="proof" />
      <main className="wrap" style={{ paddingTop: 24, paddingBottom: 60 }}>
        <div className="section-hd"><h1>Proof</h1><span className="tag">Every claim ties to a live ArmorIQ decision.</span></div>

        <div className="section">
          <div className="section-hd" style={{ borderBottomWidth: 1 }}><h2 style={{ fontSize: 20 }}>Who enforces what</h2></div>
          <div className="rows">
            {WHO.map(([what, by, how]) => (
              <div className="row" key={what}>
                <div className="idx" />
                <span style={{ fontSize: 14 }}>{what}</span>
                <div className="verdict"><span className="pill" style={{ borderColor: by === "ArmorIQ" ? "var(--violet-600)" : "var(--oxide)", color: by === "ArmorIQ" ? "var(--violet-600)" : "var(--oxide)" }}>{by}</span><div className="ep">{how}</div></div>
              </div>
            ))}
          </div>
        </div>

        <div className="section">
          <div className="section-hd" style={{ borderBottomWidth: 1 }}><h2 style={{ fontSize: 20 }}>Completion under Policy</h2>
            {summary && <span className="tag mono">{proof.executor_model}</span>}</div>
          {!summary ? (
            <p style={{ color: "var(--ink-500)" }}>{proof?.status === "not-run" ? "The evaluation has not been run yet." : "Loading…"} The pre-registration and answer-key hash are in <span className="mono">eval/PREREGISTRATION.md</span>.</p>
          ) : (
            <div className="rows">
              <div className="row" style={{ fontWeight: 600 }}><div className="idx">cond.</div><span>condition</span><div className="verdict">CuP · unsafe · overblocked</div></div>
              {Object.entries(summary as Record<string, any>).map(([cond, s]) => (
                <div className="row" key={cond}>
                  <div className="idx mono">{s.cases}</div>
                  <span className="mono">{cond}</span>
                  <div className="verdict mono">{s.cup}/{s.cases} · {s.unsafe} · {s.overblocked}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        <p style={{ fontSize: 13, color: "var(--ink-500)" }}>
          The findings and the ArmorIQ rough edges are in <a href="https://github.com/RaYYeR220/shortlist/blob/main/FINDINGS.md">FINDINGS.md</a>.
          Run the four boundary scenarios yourself with <span className="mono">scripts/verify_live.py</span>.
          Back to <Link href="/desk">the desk</Link>.
        </p>
      </main>
    </>
  );
}
