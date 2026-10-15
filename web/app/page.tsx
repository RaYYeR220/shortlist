import Link from "next/link";
import { Masthead } from "@/components/Masthead";
import { Stamp } from "@/components/Stamp";

const FORM_SVG = `
<svg viewBox="0 0 880 624" role="img" aria-label="Form SL-1, Candidate Action Plan, signed by ArmorIQ with one refused amendment">
  <defs>
    <filter id="stampink" x="-20%" y="-20%" width="140%" height="140%">
      <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" result="n"/>
      <feDisplacementMap in="SourceGraphic" in2="n" scale="2.6"/>
    </filter>
  </defs>
  <rect x="6" y="6" width="868" height="612" fill="#efe9db" stroke="#1c1915" stroke-width="1.5"/>
  <line x1="70" y1="56" x2="70" y2="612" stroke="#5236a0" stroke-opacity=".3" stroke-width="1"/>
  <line x1="74" y1="56" x2="74" y2="612" stroke="#5236a0" stroke-opacity=".3" stroke-width="1"/>
  <rect x="6" y="6" width="868" height="42" fill="#1c1915"/>
  <text x="22" y="33" fill="#f6f2e8" font-family="Archivo" font-weight="600" font-size="16" letter-spacing="1.4">FORM SL-1 · CANDIDATE ACTION PLAN</text>
  <text x="858" y="33" text-anchor="end" fill="#d6c8a8" font-family="Archivo" font-weight="600" font-size="12" letter-spacing="1.6">REV. 10-26</text>
  <text x="40" y="84" fill="#a39a88" font-family="Courier Prime" font-size="12">1</text>
  <text x="90" y="80" fill="#6e6658" font-family="Archivo" font-weight="600" font-size="11.5" letter-spacing="1.2">OBJECTIVE</text>
  <text x="90" y="106" fill="#1c1915" font-family="Courier Prime" font-size="18">screen_application</text>
  <line x1="90" y1="120" x2="840" y2="120" stroke="#1c1915" stroke-opacity=".12"/>
  <text x="40" y="152" fill="#a39a88" font-family="Courier Prime" font-size="12">2</text>
  <text x="90" y="148" fill="#6e6658" font-family="Archivo" font-weight="600" font-size="11.5" letter-spacing="1.2">CANDIDATE</text>
  <text x="90" y="174" fill="#1c1915" font-family="Courier Prime" font-size="18">A-17</text>
  <line x1="90" y1="188" x2="840" y2="188" stroke="#1c1915" stroke-opacity=".12"/>
  <text x="40" y="220" fill="#a39a88" font-family="Courier Prime" font-size="12">3</text>
  <text x="90" y="216" fill="#6e6658" font-family="Archivo" font-weight="600" font-size="11.5" letter-spacing="1.2">PERMITTED ACTIONS</text>
  <text x="90" y="244" fill="#1c1915" font-family="Courier Prime" font-size="15.5">get_application · add_note</text>
  <text x="90" y="268" fill="#1c1915" font-family="Courier Prime" font-size="15.5">set_stage( stage ∈ { phone_screen, rejected } )</text>
  <text x="90" y="292" fill="#1c1915" font-family="Courier Prime" font-size="15.5">send_email( to = candidate_email : A-17 )</text>
  <text x="90" y="336" fill="#a8341f" font-family="Courier Prime" font-size="15.5">set_stage( stage = offer )</text>
  <line x1="90" y1="331" x2="324" y2="331" stroke="#a8341f" stroke-width="1.5"/>
  <text x="340" y="336" fill="#6e6658" font-family="Courier Prime" font-size="12">← attempted amendment</text>
  <rect x="90" y="372" width="430" height="150" fill="none" stroke="#1c1915" stroke-opacity=".5"/>
  <rect x="90" y="372" width="430" height="24" fill="#1c1915"/>
  <text x="102" y="389" fill="#f6f2e8" font-family="Archivo" font-weight="600" font-size="10.5" letter-spacing="1.4">FOR ENFORCEMENT USE ONLY</text>
  <text x="102" y="420" fill="#6e6658" font-family="Courier Prime" font-size="12">verdict ..... REFUSED · argument drift</text>
  <text x="102" y="442" fill="#6e6658" font-family="Courier Prime" font-size="12">reason ...... stage ∉ { phone_screen, rejected }</text>
  <text x="102" y="464" fill="#6e6658" font-family="Courier Prime" font-size="12">point ....... ArmorIQ · proxy</text>
  <text x="102" y="486" fill="#6e6658" font-family="Courier Prime" font-size="12">at .......... 14:03:11</text>
  <g filter="url(#stampink)" opacity="0.92">
    <rect x="250" y="300" width="220" height="74" fill="none" stroke="#a8341f" stroke-width="3" transform="rotate(-5 360 337)"/>
    <rect x="256" y="306" width="208" height="62" fill="none" stroke="#a8341f" stroke-width="1" transform="rotate(-5 360 337)"/>
    <text x="360" y="334" text-anchor="middle" fill="#a8341f" font-family="Archivo" font-weight="600" font-size="30" letter-spacing="2" transform="rotate(-5 360 337)">REFUSED</text>
    <text x="360" y="356" text-anchor="middle" fill="#a8341f" font-family="Archivo" font-weight="600" font-size="11" letter-spacing="2.4" transform="rotate(-5 360 337)">ARGUMENT DRIFT · ArmorIQ</text>
  </g>
  <line x1="90" y1="556" x2="672" y2="556" stroke="#1c1915" stroke-opacity=".2"/>
  <text x="90" y="578" fill="#6e6658" font-family="Courier Prime" font-size="12">SIGNED: ArmorIQ · plan 7f3a…c2 · merkle 0b12…9e</text>
  <text x="90" y="600" fill="#a39a88" font-family="Archivo" font-weight="500" font-size="9.5" letter-spacing="1.2">NSN 7540-SL-001 · SHORTLIST ACTION PLAN · INTENT-ENFORCED</text>
  <circle cx="726" cy="486" r="96" fill="#efe9db"/>
  <circle cx="726" cy="486" r="96" fill="none" stroke="#5236a0" stroke-width="2"/>
  <circle cx="726" cy="486" r="88" fill="none" stroke="#5236a0" stroke-width="1" stroke-opacity=".6"/>
  <circle cx="726" cy="486" r="56" fill="none" stroke="#5236a0" stroke-width="1" stroke-opacity=".5"/>
  <path id="sealArc" d="M 726 406 A 80 80 0 1 1 725.9 406" fill="none"/>
  <text fill="#5236a0" font-family="Archivo" font-weight="600" font-size="11" letter-spacing="3.1"><textPath href="#sealArc" startOffset="2%">SIGNED · ARMORIQ INTENT · PLAN 7f3a…c2 · </textPath></text>
  <text x="726" y="482" text-anchor="middle" fill="#5236a0" font-family="Archivo" font-weight="600" font-size="13" letter-spacing="1">INTENT</text>
  <text x="726" y="500" text-anchor="middle" fill="#5236a0" font-family="Courier Prime" font-size="11">7f3a·c2</text>
</svg>`;

const BAND = [
  { call: 'add_note(A-17, "strong portfolio")', label: "ALLOWED", point: "armoriq:proxy" },
  { call: "set_stage(A-17, stage=offer)", label: "BLOCKED · argument drift", point: "ours:plan-binding" },
  { call: "create_offer(A-17, salary=190000)", label: "HELD → APPROVED", point: "armoriq:delegation" },
  { call: "export_candidates(to=outside)", label: "BLOCKED · not in plan", point: "armoriq:proxy" },
];

export default function Landing() {
  return (
    <>
      <Masthead />
      <main className="wrap">
        <section className="hero">
          <div>
            <h1 className="claim display">The résumé can&nbsp;ask.<br /><span className="l2">The plan decides.</span></h1>
            <p className="sub">An AI recruiter that declares every action up front, signs the plan with&nbsp;ArmorIQ, and refuses anything off it&nbsp;— at the proxy, before it runs.</p>
            <div className="cta-row">
              <Link className="cta" href="/desk">Open the desk <span>→</span></Link>
              <span className="cta-note">Signed plan <span className="mono">per run</span> · enforced at <span className="mono">ArmorIQ&nbsp;·&nbsp;proxy</span></span>
            </div>
          </div>
          <div className="formwrap" dangerouslySetInnerHTML={{ __html: FORM_SVG }} />
        </section>

        <section className="band section" style={{ borderTop: "1.5px solid var(--ink-900)" }}>
          <div className="section-hd"><h2 className="smallcaps" style={{ fontSize: 13, color: "var(--ink-500)" }}>The docket</h2><span className="tag" style={{ fontFamily: "Archivo" }}>How a verdict reads in the desk.</span></div>
          <div className="rows">
            {BAND.map((b) => (
              <div className="row" key={b.call}>
                <div className="idx mono">—</div>
                <code className="call">{b.call}</code>
                <div className="verdict"><Stamp label={b.label} point={b.point} /></div>
              </div>
            ))}
          </div>
        </section>
      </main>
      <footer className="wrap foot">
        <span>Shortlist — an intent-enforced hiring desk.</span>
        <span>Built on <b>ArmorIQ</b> · <a href="https://github.com/RaYYeR220/shortlist">source</a> · <Link href="/proof">proof</Link></span>
      </footer>
    </>
  );
}
