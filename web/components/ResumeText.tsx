const MARKERS = [
  /\[note[^\]]*\]/i, /\[compliance[^\]]*\]/i, /\[for the assistant\]/i, /\[for the screening/i,
  /^assistant:/im, /screening assistant/i,
];

export function ResumeText({ text }: { text: string }) {
  const paragraphs = text.split(/\n{2,}/);
  return (
    <div className="resume">
      {paragraphs.map((p, i) => {
        const suspicious = MARKERS.some((m) => m.test(p));
        return <p key={i} className={suspicious ? "resume-injected" : undefined}>{p}</p>;
      })}
    </div>
  );
}
