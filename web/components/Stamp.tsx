const MAP: Record<string, { cls: string; big: string; small: string }> = {
  "ALLOWED": { cls: "s-allow", big: "ALLOWED", small: "IN PLAN" },
  "BLOCKED · policy": { cls: "s-block", big: "BLOCKED", small: "POLICY" },
  "BLOCKED · not in plan": { cls: "s-notplan", big: "BLOCKED", small: "NOT ON FORM" },
  "BLOCKED · argument drift": { cls: "s-block", big: "BLOCKED", small: "ARGUMENT DRIFT" },
  "HELD → APPROVED": { cls: "s-approved", big: "APPROVED", small: "WAS HELD" },
  "HELD → REJECTED": { cls: "s-block", big: "REJECTED", small: "WAS HELD" },
  "HELD → EXPIRED": { cls: "s-failed", big: "EXPIRED", small: "WAS HELD" },
  "REFUSED · untrusted amendment": { cls: "s-notplan", big: "REFUSED", small: "UNTRUSTED" },
  "REFUSED · amendment needs a human": { cls: "s-notplan", big: "REFUSED", small: "NEEDS A HUMAN" },
  "FAILED CLOSED": { cls: "s-failed", big: "FAILED", small: "CLOSED" },
};

const POINT: Record<string, string> = {
  "armoriq:policy": "ARMORIQ · POLICY",
  "armoriq:proxy": "ARMORIQ · PROXY",
  "armoriq:delegation": "ARMORIQ · DELEGATION",
  "armoriq:sdk": "ARMORIQ · SDK",
  "armoriq:mint": "ARMORIQ · MINT",
  "ours:plan-binding": "OURS · PLAN-BOUND ARGS",
  "ours:provenance": "OURS · PROVENANCE",
};

export function Stamp({ label, point }: { label: string | null; point?: string | null }) {
  if (!label) return <span className="stampchip s-pending"><span className="big">CHECKING</span></span>;
  const m = MAP[label] ?? { cls: "s-failed", big: label.split(" ")[0] ?? "—", small: "" };
  return (
    <div>
      <span className={`stampchip ${m.cls}`}>
        <span className="big">{m.big}</span>
        {m.small && <span className="small">{m.small}</span>}
      </span>
      {point && <div className="ep">{POINT[point] ?? point}</div>}
    </div>
  );
}
