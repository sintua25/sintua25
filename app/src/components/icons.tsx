// Ikon garis tunggal 1.6 px, warna mengikuti teks.
const base = { fill: "none", stroke: "currentColor", strokeWidth: 1.6, strokeLinecap: "round", strokeLinejoin: "round" } as const;

export const FolderIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" {...base}><path d="M3.5 7.5v10a1.5 1.5 0 0 0 1.5 1.5h14a1.5 1.5 0 0 0 1.5-1.5v-8A1.5 1.5 0 0 0 19 8h-7l-2-2.5H5A1.5 1.5 0 0 0 3.5 7Z" /></svg>
);

export const ScanIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" {...base}><path d="M4 8V5.5A1.5 1.5 0 0 1 5.5 4H8M16 4h2.5A1.5 1.5 0 0 1 20 5.5V8M20 16v2.5a1.5 1.5 0 0 1-1.5 1.5H16M8 20H5.5A1.5 1.5 0 0 1 4 18.5V16M7.5 12h9" /></svg>
);

export const ChainIcon = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" {...base}><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" /></svg>
);

export function Tick({ draw = false, size = 18 }: { draw?: boolean; size?: number }) {
  return (
    <svg className={`tick${draw ? " draw" : ""}`} width={size} height={size} viewBox="0 0 24 24" aria-hidden="true"
      fill="none" stroke="var(--tick)" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round">
      <path d="M4.5 12.5l4.5 4.5 10.5-11" />
    </svg>
  );
}
