// A guilloche-style intent seal whose rosette geometry is derived from the plan hash,
// so every signed plan carries a visibly unique seal.
export function Seal({ hash, size = 132 }: { hash: string; size?: number }) {
  const bytes = (hash.match(/.{1,2}/g) ?? ["3f"]).map((h) => parseInt(h, 16) || 0);
  const at = (i: number) => bytes[i % bytes.length];
  const petals = 7 + (at(0) % 8);
  const r1 = 40, r2 = 20 + (at(1) % 14);
  const turns = petals;
  const cx = size / 2, cy = size / 2;
  const pts: string[] = [];
  const steps = 360;
  for (let i = 0; i <= steps; i++) {
    const t = (i / steps) * Math.PI * 2;
    const r = r1 + r2 * Math.cos(turns * t + (at(2) % 7));
    pts.push(`${(cx + r * Math.cos(t)).toFixed(1)},${(cy + r * Math.sin(t)).toFixed(1)}`);
  }
  const ring = (rad: number) => <circle cx={cx} cy={cy} r={rad} fill="none" stroke="var(--violet-600)" strokeWidth="0.8" />;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="ArmorIQ intent seal">
      {ring(62)}{ring(58)}
      <polyline points={pts.join(" ")} fill="none" stroke="var(--violet-600)" strokeWidth="0.7" opacity="0.9" />
      <polyline points={pts.join(" ")} fill="none" stroke="var(--violet-400)" strokeWidth="0.5"
        transform={`rotate(${at(3) % 30} ${cx} ${cy})`} opacity="0.6" />
      <text x={cx} y={cy - 4} textAnchor="middle" fontFamily="Archivo" fontSize="11" fontWeight="600"
        fill="var(--violet-600)" letterSpacing="1.5">INTENT</text>
      <text x={cx} y={cy + 10} textAnchor="middle" fontFamily="Courier Prime, monospace" fontSize="8"
        fill="var(--violet-400)">{hash.slice(0, 8)}</text>
    </svg>
  );
}
