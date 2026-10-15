export const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export type Stage = "applied" | "phone_screen" | "rejected" | "interview" | "offer" | "hired";
export interface Job { id: string; slug: string; title: string; team: string; location: string; band_min: number; band_max: number; hard_cap: number; currency: string; description: string }
export interface Application { id: string; job_id: string; name: string; email: string; resume_text: string; origin: "seed" | "visitor" | "eval"; stage: Stage; created_at: string }
export interface OutboxMessage { id: string; application_id: string | null; to_address: string; template: string; subject: string; body: string; created_at: string }
export interface Offer { id: string; application_id: string; salary: number; currency: string; status: string }
export interface Note { id: string; application_id: string; body: string; created_at: string }
export interface Approval { id: string; run_id: string; delegation_id: string; mcp: string; action: string; args: Record<string, unknown>; amount: number | null; reason: string; status: "pending" | "approved" | "rejected" | "expired"; decided_by: string | null; created_at: string }
export interface SignedSummary { plan_id: string; plan_hash: string; merkle_root: string | null; intent_reference: string; expires_at: number }
export interface PlanStep { key: string; mcp: string; action: string; purpose: string; constraints: Record<string, Record<string, unknown>> }
export interface PlanDoc { objective_type: string; goal: string; planner_fallback: boolean; steps: PlanStep[] }
export interface RunRow { id: string; objective_type: string; status: string; posture: string; objective_args: { application_id: string; job_id: string; salary: number | null }; plan: PlanDoc | null; signed: SignedSummary | null; summary: string | null; error: string | null; created_at: string }
export interface Board { jobs: Job[]; applications: Application[]; outbox: OutboxMessage[]; offers: Offer[]; notes: Note[]; approvals: Approval[]; runs: RunRow[] }
export interface RunEvent { seq: number; kind: string; payload: any; at: string }
export interface RunDetail extends RunRow { events: RunEvent[] }
export interface Meta { company: string; armoriq: { console: string; agent_id: string; mcp: { ats: string; comms: string } } }

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) } });
  if (!response.ok) {
    let detail: unknown = response.statusText;
    try { detail = (await response.json()).detail ?? detail; } catch { /* keep statusText */ }
    throw new ApiError(response.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return response.json() as Promise<T>;
}

const post = (body?: unknown): RequestInit => ({ method: "POST", body: body === undefined ? "{}" : JSON.stringify(body) });

export const api = {
  createWorkspace: () => call<{ workspace_id: string }>("/api/workspaces", post()),
  board: (ws: string) => call<Board>(`/api/workspaces/${ws}`),
  reset: (ws: string) => call<{ ok: true }>(`/api/workspaces/${ws}/reset`, post()),
  apply: (ws: string, body: { job_id: string; name: string; email: string; resume_text: string }) =>
    call<{ id: string }>(`/api/workspaces/${ws}/applications`, post(body)),
  startRun: (body: { workspace_id: string; type: "screen_application" | "extend_offer"; application_id: string; salary?: number; posture?: "gullible" | "careful" }) =>
    call<{ run_id: string }>("/api/runs", post(body)),
  run: (id: string) => call<RunDetail>(`/api/runs/${id}`),
  decide: (id: string, decision: "approved" | "rejected") => call<Approval>(`/api/approvals/${id}`, post({ decision, by: "hiring-manager" })),
  openScreen: (workspace_id: string, application_id: string, posture: "gullible" | "careful" = "gullible") =>
    call<{ run_id: string }>("/api/screens", post({ workspace_id, application_id, posture })),
  say: (runId: string, text: string) => call<{ reply: string }>(`/api/screens/${runId}/say`, post({ text })),
  voiceSession: (workspace_id: string, application_id: string) =>
    call<{ run_id: string; signed_url: string; dynamic_variables: Record<string, string> }>("/api/voice/session", post({ workspace_id, application_id })),
  meta: () => call<Meta>("/api/meta"),
  proof: () => call<any>("/api/proof"),
};
