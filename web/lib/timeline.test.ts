import { describe, expect, it } from "vitest";
import { toTimeline } from "./timeline";

const ev = (seq: number, kind: string, payload: any) => ({ seq, kind, payload, at: "" });

describe("toTimeline", () => {
  it("folds attempt, verdicts and decision into one row", () => {
    const rows = toTimeline([
      ev(1, "attempt", { mcp: "ats", action: "set_stage", args: { stage: "offer" } }),
      ev(2, "verdict", { mcp: "ats", action: "set_stage", verdict: "allow", point: "armoriq:policy", reason: "ok" }),
      ev(3, "decision", {
        mcp: "ats", action: "set_stage", args: { stage: "offer" }, kind: "blocked", label: "BLOCKED · argument drift",
        point: "ours:plan-binding", reason: "stage outside",
        drift: [{ param: "stage", declared: { in: ["phone_screen", "rejected"] }, attempted: "offer" }],
      }),
    ]);
    expect(rows).toHaveLength(1);
    expect(rows[0].label).toBe("BLOCKED · argument drift");
    expect(rows[0].verdicts).toHaveLength(1);
    expect(rows[0].drift[0].attempted).toBe("offer");
    expect(rows[0].status).toBe("done");
  });

  it("keeps an attempt pending until its decision arrives", () => {
    const rows = toTimeline([ev(1, "attempt", { mcp: "ats", action: "create_offer", args: {} })]);
    expect(rows[0].status).toBe("pending");
  });

  it("captures a hold on the row", () => {
    const rows = toTimeline([
      ev(1, "attempt", { mcp: "ats", action: "create_offer", args: { salary: 190000 } }),
      ev(2, "hold.opened", { delegation_id: "del_1" }),
      ev(3, "approval.pending", { delegation_id: "del_1", approval_id: "apr_1" }),
      ev(4, "decision", { mcp: "ats", action: "create_offer", args: {}, kind: "allowed", label: "HELD → APPROVED", point: "armoriq:proxy", reason: "", delegation_id: "del_1" }),
    ]);
    expect(rows[0].held?.approval_id).toBe("apr_1");
    expect(rows[0].label).toBe("HELD → APPROVED");
  });
});
