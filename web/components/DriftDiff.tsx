import { TimelineItem } from "@/lib/timeline";

function declared(c: Record<string, unknown>): string {
  if ("eq" in c) return String((c as any).eq);
  if ("in" in c) return `one of ${((c as any).in as unknown[]).join(", ")}`;
  if ("bind" in c) return (c as any).bind === "candidate_email" ? "this candidate's own email" : "an open slot for this job";
  if ("absent" in c) return "(not a parameter of this step)";
  if ("any" in c) return "any";
  return JSON.stringify(c);
}

export function DriftDiff({ drift }: { drift: TimelineItem["drift"] }) {
  if (!drift.length) return null;
  return (
    <table className="drift">
      <thead><tr><th>parameter</th><th>the signed plan allows</th><th>the agent tried</th></tr></thead>
      <tbody>
        {drift.map((d) => (
          <tr key={d.param}>
            <td>{d.param}</td>
            <td>{declared(d.declared)}</td>
            <td className="att">{JSON.stringify(d.attempted)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
