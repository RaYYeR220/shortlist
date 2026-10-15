import Link from "next/link";

export function Masthead({ current }: { current?: string }) {
  return (
    <header className="wrap masthead">
      <Link href="/" className="brand">Short<b>list</b></Link>
      <nav>
        <Link href="/desk" aria-current={current === "desk" ? "page" : undefined}>The desk</Link>
        <Link href="/desk/approvals" aria-current={current === "approvals" ? "page" : undefined}>Approvals</Link>
        <Link href="/proof" aria-current={current === "proof" ? "page" : undefined}>Proof</Link>
        <Link href="/jobs/senior-backend-engineer" aria-current={current === "jobs" ? "page" : undefined}>Apply</Link>
      </nav>
      <div className="corner smallcaps">Form Approved · OMB <span className="mono">3206-0012</span></div>
    </header>
  );
}
