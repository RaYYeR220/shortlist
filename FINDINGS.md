# Findings

What we learned building Shortlist on ArmorIQ, and the things that broke along the way.
Every claim is tagged by how we know it:

- **VERIFIED-LIVE** — reproduced against the live ArmorIQ backend during the build.
- **REPRODUCIBLE** — reproduced from the published SDK source with a script in-repo.
- **MODELED** — reasoned from the SDK/docs, not independently confirmed end to end.
- **NOT-CLAIMED** — explicitly out of scope; we do not assert it.

## 1. The gap we built the product around: plans bind the action, not its arguments

ArmorIQ signs a plan and the proxy proves, per tool call, that the action belongs to the
signed plan (a Merkle inclusion proof over the plan's steps). **The leaf is the action
name. The arguments are not in it.** A plan that authorizes `set_stage` on application A
authorizes `set_stage` on application B, and a plan that authorizes an email to the
candidate authorizes an email to anyone. [VERIFIED-LIVE: with a token signed for
`set_stage(application_id=A, stage=phone_screen)`, `invoke("ats","set_stage",{application_id=B, stage=offer})`
executed and returned `verified: true`.]

This is the hard case the hackathon asks for: not an obviously-bad tool, but the *right*
tool pointed one argument away. So the product declares, for every step, a constraint on
each argument — an exact value, a small allowed set, or a reference the server resolves
from the trusted record (the candidate's own email, an open slot for this job) — and binds
every attempted call to the signed plan before it may run. The argument binding is **ours,
on top of** ArmorIQ's signed plan; we label it that way in the UI (`ours:plan-binding`)
rather than claiming ArmorIQ did it.

## 2. `/iap/sdk/enforce` disagrees with the proxy for a two-policy org

The SDK's `session.check()` path calls `POST /iap/sdk/enforce`. With two active policies of
equal priority on two different MCP targets (one per server — the natural shape, and the one
the CLI's `armoriq register` creates), that endpoint **intersects both policies' allow-lists
and returns an empty set**, so every tool is refused with `tool_not_in_policy_intersection`
— including tools the matching policy plainly allows. The **proxy**, which matches policy by
target domain, enforces correctly on the same token. [VERIFIED-LIVE: `/iap/sdk/enforce`
returned `tool_not_in_policy_intersection` with `effectiveAllowedTools: []` for `set_stage`,
`add_note` and `create_offer`, while `invoke()` through the proxy allowed them.] We took the
ArmorIQ verdict from the proxy accordingly — which is the stronger enforcement point anyway,
since the proxy is the thing that actually executes the tool.

## 3. The proxy trusts a client-set approval field on a held call

After a `create_offer` is **held** for human approval, re-invoking the held call with
`params._approvals = 999` (the field the SDK's own `invoke_with_policy` resume path sets)
causes the proxy to execute it — with or without a real approval, and with an approval id
for a different plan or no id at all. [VERIFIED-LIVE: three variants executed a held
`create_offer` with no genuine approval.] Enforcement of an approval should not depend on a
value the caller supplies. We disclose this; our own agent only sets that field after a
human has approved (in our inbox or in the ArmorIQ console), and we recommend the proxy
verify the approval server-side from the delegation record instead.

## 4. The hold → approve → resume path works, but not through the documented SDK call

Hold-for-approval is real: an over-band `create_offer` is held by ArmorIQ and a delegation
is created. But:
- `POST /delegation/approve` requires `{delegationId, approverEmail}` plus an `X-User-Email`
  header, and **rejects an extra `reason` property** — `/delegation/reject` does too.
  [VERIFIED-LIVE.]
- Even the org admin (whose `/delegation/my-role` reports `limit: 1000000000`) is refused by
  `/delegation/approve` with *"Amount … exceeds your approval limit of 0"*. The limit the
  approve endpoint reads is not the role limit. [VERIFIED-LIVE.]
- The ArmorIQ **console** approves a held plan via `POST /iap/plan/{planId}/update-status`
  `{"status":"approved"}`, which is **JWT-only** (a dashboard session); an API key gets 401.
  [VERIFIED-LIVE.]
- After a genuine console approval, `get_delegation_status` returns `approved` and
  `check_approved_delegation` returns the approval, and the resume executes. [VERIFIED-LIVE.]

So the clean, honest path is: the hiring manager approves the held plan in the ArmorIQ
console; our run polls the delegation status and resumes. Our in-app Approve records the
decision best-effort and resumes on the human's explicit click.

## 5. `armoriq register` fills the policy quota and writes a per-member override

Registering via the CLI created **two policies** (the org's entire quota of two) — one per
MCP server, default-deny, with an allow-list memberRule **and** a per-member override block.
The agent's identity matches the *override*, so changing a tool's action (to `hold`) only
takes effect when set on the override, not the base rule. [VERIFIED-LIVE: `create_offer`
stayed `allow` until the override entry was changed to `hold`.]

## 6. SDK rough edges that cost us time (SDK 0.6.10)

From reading the published SDK and reproducing locally [REPRODUCIBLE unless noted]:
- The default session mode is `local`, which against production blocks every call
  (`/iap/public-key` reports signing disabled), so a first integration looks broken.
- `from_config()` defaults `environment` to `sandbox`, which points the client at
  `127.0.0.1`, so the documented `init → register → from_config` flow mints against
  localhost.
- The documented result fields don't exist: it is `.result`/`.execution_time`, not
  `.data`/`.duration_ms`; `PlanCapture` has no `.plan_hash`; `PolicyHoldException` has no
  `.delegation_id`; the default token life is 60 s, not 300.
- `delegate()` returns a token with no plan, so every `invoke()` with it raises
  `IntentMismatchException`; `delegate_subtree()` is the working call.
- On Windows the CLI crashes writing a `✓` to a cp1251 console, and `register --dry-run`
  prints success for things it did not do.
- The TypeScript SDK surfaces policy blocks as plain `Error` objects (so `instanceof` fails)
  and a mint-time denial as `InvalidTokenException`; we used the Python SDK, pinned to
  0.6.10, for the correct exception classes.

## 7. Completion under Policy

The point of a boundary is not to block everything — it is to let the real work finish while
the one unsafe call is refused. We measure **Completion under Policy (CuP)**: the legitimate
screening completes *and* no forbidden effect happened. The evaluation is pre-registered
(`eval/PREREGISTRATION.md`, with the answer key's hash) over 30 applications — 18 clean, 12
poisoned across six attack families — in four conditions: unguarded, guarded, and two
controls (allow-all must show harm; deny-all must show CuP 0, proving the scorer sees both
failure modes). Numbers are reported in `eval/results/` and on the `/proof` page, whether
they flatter the system or not. [The guarded run is executed against the live ArmorIQ proxy.]

## What we did not claim

- We did **not** verify ArmorIQ's Merkle proof ourselves; we rely on the proxy's
  verification. [NOT-CLAIMED]
- We do **not** claim ArmorIQ cryptographically gates the *resume* after approval — per
  finding 3, it does not. [NOT-CLAIMED]
- The outbox and calendar are the product's own sandbox; no real email is sent and no real
  calendar is touched. [NOT-CLAIMED]

## What we'd build next

- Argument conditions in the signed plan itself (so the binding is ArmorIQ's, not ours).
- Information provenance as a first-class plan input, so "this instruction came from an
  untrusted resume" is enforced, not just tracked by us.
- A server-side approval record the proxy checks on resume, closing finding 3.
- A delegation approve path usable with an API key, so an approval UI need not be the
  ArmorIQ console.
