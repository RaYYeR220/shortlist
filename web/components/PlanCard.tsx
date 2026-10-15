import { PlanDoc, SignedSummary } from "@/lib/api";
import { Seal } from "./Seal";

function constraintText(c: Record<string, Record<string, unknown>>): string {
  const parts: string[] = [];
  for (const [k, v] of Object.entries(c)) {
    if ("eq" in v) parts.push(`${k}=${(v as any).eq}`);
    else if ("in" in v) parts.push(`${k} ∈ {${((v as any).in as unknown[]).join(", ")}}`);
    else if ("bind" in v) parts.push(`${k}:bound`);
  }
  return parts.join(", ");
}

export function PlanCard({ plan, signed, console }: { plan: PlanDoc; signed: SignedSummary | null; console?: string }) {
  return (
    <div className="sheet formwrap">
      <div className="sheet-hd"><span>Form SL-1 · Signed Action Plan</span><span className="mono">{plan.objective_type}</span></div>
      <div className="sheet-bd">
        <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: 18 }}>
          <div>
            {plan.steps.map((s, i) => (
              <div className="field" key={s.key}>
                <div className="n mono">{i + 1}</div>
                <div>
                  <div className="lab">{s.action}</div>
                  <div className="val">{constraintText(s.constraints) || s.purpose}</div>
                </div>
              </div>
            ))}
          </div>
          {signed && <Seal hash={signed.plan_hash} />}
        </div>
        {signed && (
          <div className="mono" style={{ fontSize: 12, color: "var(--ink-500)", marginTop: 14, borderTop: "1px dotted var(--rule)", paddingTop: 10 }}>
            SIGNED ArmorIQ · plan {signed.plan_id.slice(0, 8)} · merkle {(signed.merkle_root ?? "").slice(0, 10)}
            {console && <> · <a href={`${console}/dashboard/plans/${signed.plan_id}`} target="_blank" rel="noreferrer">open in ArmorIQ →</a></>}
            {plan.planner_fallback && <span style={{ color: "var(--amber)" }}> · template fallback</span>}
          </div>
        )}
      </div>
    </div>
  );
}
