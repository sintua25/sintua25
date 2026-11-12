import { useEffect, useRef, useState } from "react";
import type { PageDetail, PageState } from "../api/types";
import { polygonPoints } from "../lib/geometry";
import { baseName } from "../lib/paths";

interface Props {
  page: PageState;
  detail: PageDetail | null;
  imageUrl: string;
  selectedField: number | null;
  onSelectField: (id: number) => void;
}

export function PhotoView({ page, detail, imageUrl, selectedField, onSelectField }: Props) {
  const desk = useRef<HTMLDivElement>(null);
  const [avail, setAvail] = useState({ w: 800, h: 600 });
  const [fit, setFit] = useState(true);
  const [allLines, setAllLines] = useState(false);
  const [imgFailed, setImgFailed] = useState(false);

  useEffect(() => {
    const el = desk.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => e && setAvail({ w: e.contentRect.width, h: e.contentRect.height }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  useEffect(() => setImgFailed(false), [imageUrl]);

  const [w, h] = detail?.size ?? [0, 0];
  const width = !w ? undefined : fit ? Math.min(avail.w, (avail.h * w) / h) : w;

  // Baris sumber tiap nilai -> warna kotak.
  const lineFields = new Map<number, { ids: number[]; doubt: boolean }>();
  for (const f of page.fields) {
    if (f.line === null) continue;
    const entry = lineFields.get(f.line) ?? { ids: [], doubt: false };
    entry.ids.push(f.id);
    entry.doubt ||= f.flags.length > 0;
    lineFields.set(f.line, entry);
  }
  const activeLine = page.fields.find((f) => f.id === selectedField)?.line ?? null;
  const file = page.files[0] ?? "";

  return (
    <section className="pane" aria-label="Foto">
      <div className="viewer-bar">
        <span className="title" title={file}>{baseName(file)}</span>
        <label className="toggle">
          <input type="checkbox" checked={allLines} onChange={(e) => setAllLines(e.target.checked)} />
          Semua baris teks
        </label>
        <button className="btn" onClick={() => setFit(!fit)}>{fit ? "Ukuran asli" : "Pas layar"}</button>
      </div>
      <div className="desk" ref={desk}>
        {imgFailed ? (
          <div className="note note-error">
            Foto tidak bisa ditampilkan.
            <span className="hint">Mungkin file dipindah atau diganti nama setelah diproses. Pilih ulang folder sumbernya.</span>
          </div>
        ) : (
          <div className="sheet" style={{ width }}>
            <img src={imageUrl} alt={`Foto ${baseName(file)}`} onError={() => setImgFailed(true)} draggable={false} />
            {detail && (
              <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" role="img" aria-label="Kotak hasil OCR">
                {detail.lines.map((line, i) => {
                  const fields = lineFields.get(i);
                  if (!fields && !allLines) return null;
                  const cls = ["box-line", fields && "box-field", fields?.doubt && "box-doubt", i === activeLine && "box-active"]
                    .filter(Boolean)
                    .join(" ");
                  return (
                    <polygon key={i} className={cls} points={polygonPoints(line.box)}
                      onClick={fields ? () => onSelectField(fields.ids[0]!) : undefined}>
                      <title>{line.text}</title>
                    </polygon>
                  );
                })}
              </svg>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
